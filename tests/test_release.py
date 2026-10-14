"""Release behavior checks. All fixtures are synthetic, not paper judgments."""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import compact
import diagram
import report


def state_fixture():
    state = {
        'schema_version': 1, 'skill_version': '0.5.1', 'mode': 'deep-read',
        'sources': [{'id': 'S1', 'kind': 'external', 'availability': 'missing',
                     'title': '合成测试材料', 'version': 'fixture'}],
        'questions': [{'id': 'Q1', 'text': '合成对象在测试条件下的未知关系是什么？',
                       'basis': 'unresolved', 'source_ids': ['S1'], 'report': {
                           'gap': '合成测试缺口，不代表真实论文。',
                           'author_answer': '合成候选回答尚未核查。',
                           'unanswered': '全部科学判断待判。',
                           'answer_sections': [
                               {'id': 'F1', 'aspect': '候选回答', 'role': 'direct',
                                'text': '合成回答仅用于格式检查，未核实。', 'claim_ids': ['C1']},
                               {'id': 'F2', 'aspect': '适用范围', 'role': 'direct',
                                'text': '合成条件尚未核查，保留待判。', 'claim_ids': ['C2']},
                           ]}}],
        'claims': [], 'evidence': [], 'next': [], 'history': [],
        'coverage': {'text': [], 'visual': []},
        'report': {'title': '合成测试材料', 'paper_source_id': 'S1', 'paper_language': 'zh',
                   'paper_note': '仅验证软件行为，不代表已阅读论文。',
                   'scope_note': '合成状态。', 'research_object': '合成对象',
                   'research_boundary': '合成测试条件',
                   'reading_boundary': [{'label': '未获取', 'text': '真实论文不在本测试中。'}]},
        'presentation': {'report_id': 'synthetic-release', 'layout': 'graph',
                         'questions': [{'question_id': 'Q1', 'display_label': 'Q1', 'claims': [
                             {'claim_id': 'C1', 'display_label': '命题1.1'},
                             {'claim_id': 'C2', 'display_label': '命题1.2'}]}],
                         'graph': {'format': 'compact', 'layout': 'auto',
                                   'question_labels': {'Q1': '合成问题'},
                                   'nodes': [{'section_id': 'F1', 'kind': 'construction', 'summary': '合成候选'},
                                             {'section_id': 'F2', 'kind': 'limit', 'summary': '未核查条件'}],
                                   'relations': [{'id': 'R1', 'from': 'F2', 'to': 'F1', 'kind': 'limit',
                                                  'text': '条件仍待核', 'basis': '合成条件限制候选回答的已知程度。',
                                                  'claim_ids': ['C2']}]}}}
    for i in (1, 2):
        state['claims'].append({
            'id': 'C' + str(i), 'question_id': 'Q1', 'author_claim': '合成命题' + str(i),
            'author_locator': {'source_id': 'S1', 'paragraph': 'synthetic'},
            'verdict': 'pending', 'reason': '本测试不读取论文；科学判断待判。',
            'supported_scope': '', 'evidence_ids': [],
            'report': {'title': '合成命题' + str(i), 'evidence_note': '无真实证据，未核查。',
                       'question_link': {'question_id': 'Q1', 'aspect': '合成侧面', 'role': 'direct',
                                         'relevance': '测试问题与命题链接。', 'impact': '不产生科学结论。'}}})
    report.map_answer_sections(state)
    # A seal is appropriate only for this constructed software fixture.
    report.seal_answers(state)
    return state


def graph_fixture(count=2, relations=True):
    return {
        'format': 'compact', 'layout': 'auto',
        'questions': [{'id': 'Q1', 'label': 'Q1', 'title': '合成诊断问题'}],
        'nodes': [{'id': 'F' + str(i), 'question_id': 'Q1', 'label': 'A' + str(i),
                   'title': '合成侧面' + str(i), 'detail': '限定条件下的合成记录',
                   'refs': ['命题1.' + str(i)], 'kind': 'limit'} for i in range(1, count + 1)],
        'relations': [{'id': 'R' + str(i), 'from': 'F' + str(i), 'to': 'F' + str(i + 1),
                       'kind': 'limit', 'text': '合成条件限定'} for i in range(1, count)] if relations else [],
    }


class ReleaseTests(unittest.TestCase):
    def test_changes_require_review_but_layout_does_not(self):
        state = state_fixture()
        report.validate(state)
        for field in ('claim', 'evidence', 'synthesis', 'edge', 'node'):
            changed = copy.deepcopy(state)
            if field == 'claim':
                changed['claims'][0]['reason'] += ' 新判断'
            elif field == 'evidence':
                changed['sources'][0]['version'] = 'changed-source'
            elif field == 'synthesis':
                changed['questions'][0]['report']['answer_sections'][0]['text'] += ' 新综合'
            elif field == 'edge':
                changed['presentation']['graph']['relations'][0]['text'] += ' 新含义'
            else:
                changed['presentation']['graph']['nodes'][0]['summary'] += ' 新含义'
            with self.subTest(field=field), self.assertRaises(ValueError):
                report.validate(changed)
        state['presentation']['graph']['layout'] = 'indexed'
        report.validate(state)

    def test_unknown_endpoint_is_rejected(self):
        state = state_fixture()
        state['presentation']['graph']['relations'][0]['to'] = 'unknown'
        with self.assertRaises(ValueError):
            report.validate(state)

    def test_missing_font_is_explicit_mermaid_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = diagram.generate(graph_fixture(), Path(tmp) / 'assets', font=Path(tmp) / 'absent.ttf')
            self.assertEqual(result['backend'], 'mermaid')
            self.assertTrue(result['warnings'])
            self.assertIn('-.->', '\n'.join(result['blocks']))

    def test_report_cli_output_and_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file, target = Path(tmp) / 'state.json', Path(tmp) / 'reading.md'
            state_file.write_text(json.dumps(state_fixture(), ensure_ascii=False), encoding='utf-8')
            args = [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'scripts/report.py'), str(state_file),
                    '--out', str(target), '--font', str(Path(tmp) / 'absent.ttf')]
            first = subprocess.run(args, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(json.loads(first.stdout)['backend'], 'mermaid')
            content = target.read_bytes()
            self.assertIn('证据附录', content.decode('utf-8'))
            second = subprocess.run(args, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(second.returncode, 2)
            self.assertEqual(target.read_bytes(), content)
            source_target = [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'scripts/report.py'),
                             str(state_file), '--out', str(state_file), '--overwrite']
            protected = state_file.read_bytes()
            failure = subprocess.run(source_target, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(failure.returncode, 2)
            self.assertEqual(state_file.read_bytes(), protected)

    def check_routes(self, model, folder):
        diagram.generate(model, folder)
        layouts = json.loads((folder / 'layout.json').read_text(encoding='utf-8'))
        drawn = [edge for panel in layouts for edge in panel['edge_routes']]
        expected = {e['id']: e for e in model['relations']}
        self.assertEqual(Counter(e['id'] for e in drawn), Counter(expected.keys()))
        for panel in layouts:
            self.assertEqual(panel['overlap_count'], 0)
            self.assertEqual(panel['overflow_count'], 0)
            boxes = {k: [box] for k, box in panel.get('node_boxes', {}).items()}
            for node in panel.get('node_instances', []):
                boxes.setdefault(node['id'], []).append(node['box'])
            for edge in panel['edge_routes']:
                self.assertTrue(all(edge[k] == expected[edge['id']][k] for k in ('from', 'to', 'kind', 'text')))
                for point, endpoint in [(edge['points'][0], edge['from']), (edge['points'][-1], edge['to'])]:
                    def attached(box):
                        x, y, w, h = box
                        u, v = point
                        return (((abs(u-x) < .1 or abs(u-x-w) < .1) and y-.1 <= v <= y+h+.1)
                                or ((abs(v-y) < .1 or abs(v-y-h) < .1) and x-.1 <= u <= x+w+.1))
                    self.assertTrue(any(attached(b) for b in boxes[endpoint]))
                self.assertFalse(any(compact.line_hits_box(edge['points'], b, 0)
                                     for nid, bs in boxes.items() if nid not in (edge['from'], edge['to']) for b in bs))
        return layouts

    @unittest.skipUnless(importlib.util.find_spec('PIL'), 'Pillow not installed')
    def test_no_construction_node_still_has_connected_arrows(self):
        try:
            diagram._font()
        except diagram.DrawingUnavailable:
            self.skipTest('No system Chinese font; fallback covered separately')
        with tempfile.TemporaryDirectory() as tmp:
            panels = self.check_routes(graph_fixture(), Path(tmp) / 'assets')
            self.assertEqual(len(panels), 1)
            self.assertEqual(panels[0]['layout_kind'], 'connected')

    @unittest.skipUnless(importlib.util.find_spec('PIL'), 'Pillow not installed')
    def test_dense_graph_preserves_all_arrows(self):
        try:
            diagram._font()
        except diagram.DrawingUnavailable:
            self.skipTest('No system Chinese font; fallback covered separately')
        with tempfile.TemporaryDirectory() as tmp:
            panels = self.check_routes(graph_fixture(10), Path(tmp) / 'assets')
            self.assertGreater(len(panels), 1)

    def test_unrelated_nodes_do_not_invent_edges(self):
        output = diagram.mermaid(graph_fixture(relations=False))
        self.assertNotIn('-.->', output)
        self.assertNotIn('-->', output)


if __name__ == '__main__':
    unittest.main()
