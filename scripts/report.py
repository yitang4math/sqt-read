"""Render a reviewed SQT state as a short report with an evidence appendix.

This checks report fields and presentation mappings, not scientific correctness.
PDF/source identity remains the responsibility of paper.py verify-state.
"""
import argparse
import hashlib
import json
import re
import sys
import time
import importlib.util
from pathlib import Path


VERDICTS = {'supported': '支持', 'limited': '受限支持',
            'counter': '反证', 'pending': '待判'}
LINK_ROLES = {'direct', 'indirect', 'reliability'}
EDGE_KINDS = {'construction', 'support', 'limit', 'indirect', 'dependency'}


def compact(state):
    return (state.get('presentation', {}).get('graph') or {}).get('format') == 'compact'


def modern(state):
    match = re.match(r'^(\d+)\.(\d+)', state.get('skill_version', ''))
    return bool(match and tuple(map(int, match.groups())) >= (0, 4))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def section_basis(section):
    return digest({key: section.get(key) for key in ('id', 'aspect', 'role', 'text',
                                                   'claim_ids', 'claim_basis')})


def alphabet(number):
    label = ''
    while number:
        number, remainder = divmod(number - 1, 26)
        label = chr(65 + remainder) + label
    return label


def map_answer_sections(state):
    """Explicitly save display labels for already assigned stable facet IDs."""
    questions = index(state.get('questions'), 'questions')
    for n, group in enumerate(state['presentation']['questions'], 1):
        sections = questions[group['question_id']]['report']['answer_sections']
        group['answer_sections'] = [dict(section_id=text_field(s, 'id', 'section'),
            display_label=alphabet(n)+str(i)) for i, s in enumerate(sections, 1)]
    if state['report'].get('notes') is not None:
        state['presentation']['notes'] = [dict(section_id=text_field(s,'id','note'),display_label=f'N{i}')
                                         for i,s in enumerate(state['report']['notes'],1)]
    return state


def graph_basis(state):
    graph = state['presentation']['graph']
    claims = index(state['claims'], 'claims')
    displayed = {g['question_id'] for g in state['presentation']['questions']}
    qinputs = []
    for q in state['questions']:
        if q['id'] not in displayed:
            continue
        narrative = q['report']
        qinputs.append(dict(id=q['id'], original_form=q.get('original_form'),text=q['text'],
            basis=q['basis'],source_ids=q.get('source_ids'),role=q.get('role'),parent_id=q.get('parent_id'),
            report={key:narrative.get(key) for key in ('gap','author_answer','unanswered','identification_note')},
            facets=[dict(id=s.get('id'),aspect=s['aspect'],role=s['role'],text=s['text'],
                         claim_basis={cid:claim_basis(state,claims[cid]) for cid in s['claim_ids']})
                    for s in narrative['answer_sections']]))
    qinputs.sort(key=lambda q:q['id'])
    relations = [{key:r.get(key) for key in (('id','from','to','kind','text','basis','claim_ids') if compact(state)
                                            else ('id','from','to','text','basis','claim_ids'))}
                 for r in graph.get('relations', [])]
    relations.sort(key=lambda r:r['id'])
    if compact(state):
        for q in qinputs:q['facets'].sort(key=lambda s:s['id'])
    payload=dict(question_labels=graph.get('question_labels'),relations=relations,
        relation_claims={cid:claim_basis(state,claims[cid]) for r in relations for cid in r.get('claim_ids',[])},
        questions=qinputs)
    if compact(state):
        payload['nodes']=sorted([{key:n.get(key) for key in ('section_id','kind','summary')} for n in graph.get('nodes',[])],key=lambda n:n['section_id'])
        payload['notes']=sorted([dict(id=s.get('id'),aspect=s.get('aspect'),text=s.get('text'),
            claim_basis={cid:claim_basis(state,claims[cid]) for cid in s['claim_ids']}) for s in state['report'].get('notes',[])]
            ,key=lambda s:s['id'])
    return digest(payload)


def claim_basis(state, claim):
    """Fingerprint the reviewed inputs; this does not evaluate their meaning."""
    core = {key: claim.get(key) for key in ('id', 'question_id', 'author_claim', 'author_locator',
                                           'verdict', 'supported_scope', 'reason', 'evidence_ids')}
    detail = claim.get('report', {})
    core['report'] = {key: detail.get(key) for key in ('title', 'evidence_note', 'question_link')}
    records = {item['id']: item for item in state.get('evidence', [])}
    checked = [records.get(eid) for eid in sorted(claim.get('evidence_ids', []))]
    qid = (detail.get('question_link') or {}).get('question_id')
    question = next((q for q in state.get('questions', []) if q.get('id') == qid), {})
    question_core = {key: question.get(key) for key in ('id', 'text', 'basis', 'source_ids', 'role',
                                                      'parent_id', 'original_form', 'translation')}
    narrative = question.get('report') or {}
    question_core['report'] = {key: narrative.get(key) for key in ('gap', 'author_answer', 'unanswered')}
    involved = set(question.get('source_ids', []))
    involved.add((claim.get('author_locator') or {}).get('source_id'))
    involved.update(item.get('source_id') for item in checked if isinstance(item, dict))
    sources = [{key: source.get(key) for key in ('id', 'kind', 'availability', 'sha256', 'version')}
               for source in state.get('sources', []) if source.get('id') in involved]
    sources.sort(key=lambda source: source['id'])
    payload = dict(claim=core, evidence=checked, question=question_core, sources=sources)
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def seal_answers(state):
    """Bind already reviewed synthesis to its inputs. Never called by render/load."""
    claims = index(state.get('claims'), 'claims')
    for question in state.get('questions', []):
        for section in (question.get('report') or {}).get('answer_sections', []):
            section['claim_basis'] = {cid: claim_basis(state, claims[cid]) for cid in section['claim_ids']}
            if modern(state):
                section['review_basis'] = section_basis(section)
    for note in state.get('report',{}).get('notes',[]):
        note['claim_basis']={cid:claim_basis(state,claims[cid]) for cid in note['claim_ids']}
        note['review_basis']=section_basis(note)
    if 'graph' in state.get('presentation', {}):
        state['presentation']['graph']['review_basis'] = graph_basis(state)
    return state


def text_field(obj, key, label):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label}.{key}: missing nonempty text')
    return value.strip()


def index(items, label):
    if not isinstance(items, list):
        raise ValueError(f'{label}: expected an array')
    result = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f'{label}: expected objects')
        key = text_field(item, 'id', label)
        if key in result:
            raise ValueError(f'{label}: duplicate ID {key}')
        result[key] = item
    return result


def object_field(obj, key, label):
    value = obj.get(key)
    if not isinstance(value, dict):
        raise ValueError(f'{label}.{key}: missing object; complete the reviewed report fields first')
    return value


def question_locator(loc, question, sources):
    if (not isinstance(loc, dict) or loc.get('source_id') not in sources
            or loc.get('source_id') not in question.get('source_ids', [])
            or not any(loc.get(k) for k in ('page', 'section', 'paragraph', 'url'))):
        raise ValueError(f"{question['id']}: original question needs a question-linked source and specific locator")
    page = loc.get('page')
    source = sources[loc['source_id']]
    if page is not None and (type(page) is not int or page < 1
                            or (source.get('page_count') is not None and page > source['page_count'])):
        raise ValueError(f"{question['id']}: original question page is outside source bounds")


def validate(state):
    if not isinstance(state, dict):
        raise ValueError('state: expected an object')
    if state.get('schema_version') != 1:
        raise ValueError('unsupported schema_version')
    report = object_field(state, 'report', 'state')
    text_field(state, 'skill_version', 'state')
    for key in ('title', 'paper_note', 'scope_note', 'research_object', 'research_boundary'):
        text_field(report, key, 'report')
    boundary = report.get('reading_boundary')
    if not isinstance(boundary, list) or not boundary:
        raise ValueError('report.reading_boundary: expected a nonempty array')
    for item in boundary:
        if not isinstance(item, dict):
            raise ValueError('report.reading_boundary: expected objects')
        for key in ('label', 'text'):
            text_field(item, key, 'reading_boundary')
    questions = index(state.get('questions'), 'questions')
    claims = index(state.get('claims'), 'claims')
    evidence = index(state.get('evidence'), 'evidence')
    sources = index(state.get('sources'), 'sources')
    sid = text_field(report, 'paper_source_id', 'report')
    language = text_field(report, 'paper_language', 'report')
    if not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]+)*', language):
        raise ValueError('report.paper_language: expected a language code such as en or zh')
    if sid not in sources or report['title'] != sources[sid].get('title'):
        raise ValueError('report.title: must match the reviewed original title of paper_source_id')
    for qid in questions:
        seen, current = set(), qid
        while current is not None:
            if current in seen or current not in questions:
                raise ValueError(f'{qid}: cyclic or unknown question parent')
            seen.add(current)
            current = questions[current].get('parent_id')
    presentation = object_field(state, 'presentation', 'state')
    text_field(presentation, 'report_id', 'presentation')
    groups = presentation.get('questions')
    if not isinstance(groups, list) or not groups:
        raise ValueError('presentation.questions: expected a nonempty array')
    if len(groups) > 1 and 'graph' not in presentation:
        text_field(report, 'question_overview', 'report')
    seen_q, seen_c = set(), set()
    for number, group in enumerate(groups, 1):
        if not isinstance(group, dict):
            raise ValueError('presentation.questions: expected objects')
        qid = group.get('question_id')
        if qid not in questions or qid in seen_q:
            raise ValueError('presentation: unknown or repeated question')
        seen_q.add(qid)
        if group.get('display_label') != f'Q{number}':
            raise ValueError('presentation: question labels must follow display order')
        question = questions[qid]
        if question.get('role', 'scientific') != 'scientific':
            raise ValueError(f'{qid}: operational questions belong under a scientific question')
        text_field(question, 'text', qid)
        original = question.get('original_form')
        if original is not None or language.split('-')[0] != 'zh':
            original = object_field(question, 'original_form', qid)
            if text_field(original, 'language', qid + '.original_form') != language:
                raise ValueError(f'{qid}: original question language must match paper_language')
            text_field(original, 'text', qid + '.original_form')
            if original.get('kind') not in ('author_quote', 'reader_reconstruction'):
                raise ValueError(f'{qid}: distinguish author_quote from reader_reconstruction')
            if original.get('derived_from') != 'source_text':
                raise ValueError(f'{qid}: original question must be derived directly from source_text')
            if original['kind'] == 'author_quote':
                loc = object_field(original, 'locator', qid + '.original_form')
                question_locator(loc, question, sources)
            else:
                locs = original.get('source_locators')
                if not isinstance(locs, list) or not locs:
                    raise ValueError(f'{qid}: reconstruction needs original source_locators')
                for loc in locs:
                    question_locator(loc, question, sources)
            translation = object_field(question, 'translation', qid)
            if translation.get('language') != 'zh' or translation.get('derived_from') != 'original_form':
                raise ValueError(f'{qid}: Chinese translation must derive from original_form')
            if text_field(translation, 'text', qid + '.translation') != question['text']:
                raise ValueError(f'{qid}: legacy text must match the Chinese translation')
        if question.get('basis') not in ('source', 'inference', 'unresolved'):
            raise ValueError(f'{qid}: missing identification basis')
        narrative = object_field(question, 'report', qid)
        for key in ('gap', 'author_answer', 'unanswered'):
            text_field(narrative, key, qid + '.report')
        if narrative.get('identification_note') is not None:
            text_field(narrative, 'identification_note', qid + '.report')
        mapped = group.get('claims')
        if not isinstance(mapped, list) or not mapped:
            raise ValueError(f'{qid}: expected at least one reviewed claim')
        for position, mapping in enumerate(mapped, 1):
            if not isinstance(mapping, dict):
                raise ValueError('presentation.claims: expected objects')
            cid = mapping.get('claim_id')
            if cid not in claims or cid in seen_c:
                raise ValueError('presentation: unknown or repeated claim')
            seen_c.add(cid)
            if mapping.get('display_label') != f'命题{number}.{position}':
                raise ValueError('presentation: claim labels must follow display order')
            claim = claims[cid]
            current = claim.get('question_id')
            while current in questions and current != qid:
                current = questions[current].get('parent_id')
            if current != qid:
                raise ValueError(f'{cid}: claim does not belong to this question or its descendants')
            for key in ('author_claim', 'reason'):
                text_field(claim, key, cid)
            if claim.get('verdict') not in VERDICTS:
                raise ValueError(f'{cid}: invalid verdict')
            aloc = claim.get('author_locator')
            if aloc is not None and (not isinstance(aloc, dict) or aloc.get('source_id') not in sources):
                raise ValueError(f'{cid}: invalid author source')
            if claim['verdict'] != 'pending':
                text_field(claim, 'supported_scope', cid)
                if aloc is None:
                    raise ValueError(f'{cid}: decided claim needs an author locator')
            if any(eid not in evidence for eid in claim.get('evidence_ids', [])):
                raise ValueError(f'{cid}: unknown evidence ID')
            detail = object_field(claim, 'report', cid)
            for key in ('title', 'evidence_note'):
                text_field(detail, key, cid + '.report')
            link = object_field(detail, 'question_link', cid + '.report')
            if link.get('question_id') != qid:
                raise ValueError(f'{cid}: question_link must point to the displayed scientific question')
            if link.get('role') not in LINK_ROLES:
                raise ValueError(f'{cid}: invalid question_link role')
            for key in ('aspect', 'relevance', 'impact'):
                text_field(link, key, cid + '.report.question_link')
        sections = narrative.get('answer_sections')
        if not isinstance(sections, list) or not sections:
            raise ValueError(f'{qid}: complete reviewed answer_sections; legacy takeaways are not synthesized automatically')
        allowed = {item['claim_id'] for item in mapped}
        if compact(state):
            allowed = {m['claim_id'] for g in groups for m in g['claims']}
        for section in sections:
            if not isinstance(section, dict):
                raise ValueError(f'{qid}: answer_sections must contain objects')
            for key in ('aspect', 'text'):
                text_field(section, key, qid + '.report.answer_sections')
            if '\n' in section['aspect'] or '\r' in section['aspect']:
                raise ValueError(f'{qid}: aspect is a single-line title, not a report block')
            if section.get('role') not in LINK_ROLES:
                raise ValueError(f'{qid}: invalid answer section role')
            selected = section.get('claim_ids')
            if (not isinstance(selected, list) or not selected
                    or any(not isinstance(cid, str) or cid not in allowed for cid in selected)
                    or len(selected) != len(set(selected))):
                raise ValueError(f'{qid}: each answer section must uniquely reference mapped claims')
            if not any(claims[cid]['report']['question_link']['role'] == section['role']
                       and claims[cid]['report']['question_link']['question_id'] == qid for cid in selected):
                raise ValueError(f'{qid}: answer section needs a claim with its declared reasoning role')
            expected = {cid: claim_basis(state, claims[cid]) for cid in selected}
            if section.get('claim_basis') != expected:
                raise ValueError(f'{qid}: answer inputs changed or unreviewed; review synthesis before sealing its current basis')
            if modern(state) and (not section.get('id') or section.get('review_basis') != section_basis(section)):
                raise ValueError(f'{qid}: synthesis text changed or unreviewed; review before sealing')
        if modern(state):
            stable = [text_field(s, 'id', qid + '.answer_sections') for s in sections]
            if len(set(stable)) != len(stable):
                raise ValueError(f'{qid}: duplicate facet IDs')
            expected_map = [dict(section_id=s['id'], display_label=alphabet(number)+str(i))
                            for i,s in enumerate(sections,1)]
            if group.get('answer_sections') != expected_map:
                raise ValueError(f'{qid}: run map_answer_sections to save the current display mapping')
    notes=report.get('notes',[])
    if not isinstance(notes,list):
        raise ValueError('report.notes: expected array')
    all_sections={s.get('id') for g in groups for s in questions[g['question_id']]['report']['answer_sections']}
    note_ids=set()
    for note in notes:
        nid=text_field(note,'id','note')
        if nid in note_ids or nid in all_sections or nid in seen_q:
            raise ValueError('note: duplicate or conflicting ID')
        note_ids.add(nid)
        for key in ('aspect','text'):text_field(note,key,nid)
        if '\n' in note['aspect'] or '\r' in note['aspect']:
            raise ValueError(f'{nid}: aspect is a single-line title')
        selected=note.get('claim_ids')
        if (not isinstance(selected,list) or not selected or len(selected)!=len(set(selected))
                or any(cid not in seen_c for cid in selected)):
            raise ValueError(f'{nid}: invalid note claims')
        if (note.get('claim_basis')!={cid:claim_basis(state,claims[cid]) for cid in selected}
                or note.get('review_basis')!=section_basis(note)):
            raise ValueError(f'{nid}: note changed or inputs unreviewed')
    if notes and presentation.get('notes')!=[dict(section_id=s['id'],display_label=f'N{i}') for i,s in enumerate(notes,1)]:
        raise ValueError('notes: save display mapping with map_answer_sections')
    if presentation.get('layout') not in (None, 'graph', 'text'):
        raise ValueError('presentation.layout: expected graph or text')
    if modern(state) and presentation.get('layout', 'graph') == 'graph' and 'graph' not in presentation:
        raise ValueError('complete and review graph fields; no automatic reconstruction from old prose')
    if re.match(r'^0\.(?:[5-9]|\d{2,})\.',state['skill_version']) and 'graph' in presentation and not compact(state):
        raise ValueError('0.5+: complete compact graph records; changing only skill_version is not migration')
    if 'graph' in presentation:
        graph = object_field(presentation, 'graph', 'presentation')
        labels = object_field(graph, 'question_labels', 'graph')
        if set(labels) != seen_q or any(not isinstance(v,str) or not v.strip() for v in labels.values()):
            raise ValueError('graph.question_labels: give a short label for each displayed Q')
        facets = [s['id'] for qid in seen_q for s in questions[qid]['report']['answer_sections']]
        if len(facets) != len(set(facets)):
            raise ValueError('facet IDs must be globally unique')
        sections={s['id']:(qid,s) for qid in seen_q for s in questions[qid]['report']['answer_sections']}
        node_ids=set()
        if compact(state):
            if graph.get('layout','auto') not in ('auto','grouped','indexed'):
                raise ValueError('graph.layout: auto/grouped/indexed')
            node_list=graph.get('nodes')
            if not isinstance(node_list,list):raise ValueError('graph.nodes: expected array, possibly empty')
            for node in node_list:
                nid=text_field(node,'section_id','node')
                if nid not in sections or nid in node_ids or nid in seen_q:
                    raise ValueError('graph node: unknown, repeated or conflicting section ID')
                node_ids.add(nid)
                if node.get('kind') not in ('construction','support','limit','indirect'):
                    raise ValueError('graph node: invalid kind')
                text_field(node,'summary',nid)
        relations = graph.get('relations')
        if not isinstance(relations,list):
            raise ValueError('graph.relations: expected array, including empty for unrelated questions')
        seen_r=set()
        for relation in relations:
            if not isinstance(relation,dict):
                raise ValueError('graph.relations: expected objects')
            rid=text_field(relation,'id','relation')
            endpoints=seen_q|node_ids if compact(state) else seen_q
            if rid in seen_r or relation.get('from') not in endpoints or relation.get('to') not in endpoints or relation['from']==relation['to']:
                raise ValueError('relation: repeated ID, unknown endpoint or self relation')
            seen_r.add(rid)
            text_field(relation,'text',rid);text_field(relation,'basis',rid)
            if compact(state) and relation.get('kind') not in EDGE_KINDS:
                raise ValueError('relation: declare construction/support/limit/indirect/dependency')
            selected=relation.get('claim_ids')
            if not isinstance(selected,list) or len(selected)!=len(set(selected)) or any(cid not in seen_c for cid in selected):
                raise ValueError(f'{rid}: invalid relation claim references')
            endpoint_qs={sections[e][0] if e in sections else e for e in (relation['from'],relation['to'])}
            if any(claims[cid]['report']['question_link']['question_id'] not in endpoint_qs
                   and not any(cid in sections[e][1]['claim_ids'] for e in (relation['from'],relation['to']) if e in sections)
                   for cid in selected):
                raise ValueError(f'{rid}: relation claims must belong to its endpoint questions')
        if graph.get('review_basis') != graph_basis(state):
            raise ValueError('graph meaning or inputs changed; review before sealing graph basis')
    if not isinstance(state.get('next'), list):
        raise ValueError('next: expected an array')
    for task in state['next'][:3]:
        if not isinstance(task, dict):
            raise ValueError('next: expected objects')
        for key in ('location', 'action', 'decides'):
            text_field(task, key, 'next')
    return report, groups, questions, claims, sources


def slug(text):
    return re.sub(r'[^\w\s-]', '', text.lower()).replace(' ', '-')


def locator_note(locator):
    if locator is None:
        return '作者回答尚未定位'
    parts = []
    if locator.get('page') is not None:
        parts.append(f"PDF第{locator['page']}页")
    for key in ('section', 'paragraph', 'table', 'figure', 'url'):
        if locator.get(key):
            parts.append(str(locator[key]))
    return '；'.join(parts) or '见接续状态中的原文定位'


def selected_layout(state, layout='auto'):
    if layout not in ('auto','graph','text'):
        raise ValueError('layout must be auto, graph or text')
    return (state['presentation'].get('layout', 'graph' if modern(state) else 'text')
            if layout == 'auto' else layout)


def graph_model(state):
    questions=index(state['questions'],'questions')
    if compact(state):
        graph=state['presentation']['graph']
        refs={m['claim_id']:m['display_label'] for g in state['presentation']['questions'] for m in g['claims']}
        sections={s['id']:(g['question_id'],s) for g in state['presentation']['questions'] for s in questions[g['question_id']]['report']['answer_sections']}
        labels={s['section_id']:s['display_label'] for g in state['presentation']['questions'] for s in g['answer_sections']}
        return dict(format='compact',layout=graph.get('layout','auto'),title='关键回答及证据关系',
            questions=[dict(id=g['question_id'],label=g['display_label'],title=graph['question_labels'][g['question_id']])
                       for g in state['presentation']['questions']],
            nodes=[dict(id=n['section_id'],question_id=sections[n['section_id']][0],label=labels[n['section_id']],
                        title=sections[n['section_id']][1]['aspect'],detail=n['summary'],kind=n['kind'],
                        refs=[refs[cid] for cid in sections[n['section_id']][1]['claim_ids']]) for n in graph['nodes']],
            relations=graph['relations'])
    model=dict(questions=[],relations=state['presentation']['graph']['relations'])
    for group in state['presentation']['questions']:
        q=questions[group['question_id']]
        sections={s['id']:s for s in q['report']['answer_sections']}
        refs={m['claim_id']:m['display_label'] for m in group['claims']}
        model['questions'].append(dict(id=q['id'],label=group['display_label'],
            title=state['presentation']['graph']['question_labels'][q['id']],facets=[
                dict(id=m['section_id'],label=m['display_label'],title=sections[m['section_id']]['aspect'],
                     refs=[refs[cid] for cid in sections[m['section_id']]['claim_ids']])
                for m in group['answer_sections']]))
    return model


def drawing_module():
    spec=importlib.util.spec_from_file_location('sqt_diagram',Path(__file__).with_name('diagram.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def render(state, diagram_blocks=None, layout='auto'):
    report, groups, questions, claims, sources = validate(state)
    graph_mode=selected_layout(state,layout)=='graph'
    if graph_mode and 'graph' not in state['presentation']:
        raise ValueError('requested graph layout lacks reviewed graph fields')
    lines = [f"# {report['title']}（精读）", '', report['paper_note'], '',
             f"技能版本：{state['skill_version']}。{report['scope_note']}", '',
             f"**研究对象**：{report['research_object']}", '',
             f"**研究边界**：{report['research_boundary']}", '']
    if graph_mode:
        lines += ['## '+('关键关系图' if compact(state) else '问题与回答侧面关系图'),'']
        lines += (diagram_blocks if diagram_blocks is not None else
                  ['```mermaid',drawing_module().mermaid(graph_model(state)),'```',''])
        lines += [('图只展示关键关系，Q用简称；条件与未决项在正文和附录保留。连线按标注理解，不自动代表因果。' if compact(state)
                   else '图中Q用简称，正文保留完整双语问题；侧面编号贯通正文与附录。连线含义以标注为准，不自动代表因果证明。'),'']
    elif len(groups) > 1:
        overview=report.get('question_overview')
        if not overview:
            graph=state['presentation'].get('graph',{})
            labels={g['question_id']:g['display_label'] for g in groups}
            overview='' if compact(state) else '；'.join(labels[r['from']]+'→'+labels[r['to']]+'：'+r['text'] for r in graph.get('relations',[]))
            if not overview:overview='、'.join(labels[g['question_id']]+' '+graph['question_labels'][g['question_id']] for g in groups)
        lines += ['## 科学问题概览', '', overview, '']
    for group in groups:
        question = questions[group['question_id']]
        narrative = question['report']
        original = question.get('original_form')
        if original is not None:
            lines += [f"## {group['display_label']} {original['text']}", '']
            if original['kind'] == 'author_quote':
                lines += [f'**作者问题原句**（{locator_note(original["locator"])}）。', '']
            lines += [f"**中文译文**：{question['translation']['text']}", '']
        else:
            lines += [f"## {group['display_label']} {question['text']}", '']
        if narrative.get('identification_note'):
            lines += [f"**识别说明**：{narrative['identification_note']}", '']
        lines += [f"**问题与缺口**：{narrative['gap']}", '',
                  f"**作者的回答**：{narrative['author_answer']}", '']
        lines += ['**证据支持的回答**：', '']
        section_labels={m['section_id']:m['display_label'] for m in group.get('answer_sections',[])}
        for section in narrative['answer_sections']:
            refs = []
            for mapping in [m for g in groups for m in g['claims']]:
                if mapping['claim_id'] not in section['claim_ids']:
                    continue
                title = mapping['display_label'] + ' ' + claims[mapping['claim_id']]['report']['title']
                refs.append(f"[{mapping['display_label']}](#{slug(title)})")
            if graph_mode:
                lines += [f"### {section_labels[section['id']]} {section['aspect']}",'',
                          f"{section['text']}（{'、'.join(refs)}）",'']
            else:
                lines += [f"**{section['aspect']}**：{section['text']}（{'、'.join(refs)}）", '']
        lines += [f"**仍未回答的部分**：{narrative['unanswered']}", '']
    if report.get('notes'):
        lines += ['## 未入总图的边界与核查','']
        for note,mapping in zip(report['notes'],state['presentation']['notes']):
            refs=[]
            for cm in [m for g in groups for m in g['claims']]:
                if cm['claim_id'] in note['claim_ids']:
                    title=cm['display_label']+' '+claims[cm['claim_id']]['report']['title']
                    refs.append(f"[{cm['display_label']}](#{slug(title)})")
            lines += [f"### {mapping['display_label']} {note['aspect']}",'',f"{note['text']}（{'、'.join(refs)}）",'']
    lines += ['## 阅读边界与下一步', '']
    for boundary in report['reading_boundary']:
        lines += [f"**{boundary['label']}**：{boundary['text']}", '']
    if state['next']:
        lines += ['**下一步**：', '']
        for number, task in enumerate(state['next'][:3], 1):
            lines.append(f"{number}. {task['action']}（位置：{task['location']}；将区分：{task['decides']}）")
        lines.append('')
    lines += ['## 证据附录', '']
    for group in groups:
        lines += [f"### {group['display_label']} 的证据", '']
        for mapping in group['claims']:
            claim = claims[mapping['claim_id']]
            detail = claim['report']
            link = detail['question_link']
            correspondence=[]
            if graph_mode:
                for section in questions[group['question_id']]['report']['answer_sections']:
                    if claim['id'] in section['claim_ids']:
                        label=next(m['display_label'] for m in group['answer_sections'] if m['section_id']==section['id'])
                        title=label+' '+section['aspect']
                        correspondence.append(f'[{title}](#{slug(title)})')
                if compact(state):
                    for other in groups:
                        if other['question_id']==group['question_id']:continue
                        for section in questions[other['question_id']]['report']['answer_sections']:
                            if claim['id'] in section['claim_ids']:
                                label=next(m['display_label'] for m in other['answer_sections'] if m['section_id']==section['id'])
                                title=label+' '+section['aspect'];correspondence.append(f'[{title}](#{slug(title)})')
                for note,nm in zip(report.get('notes',[]),state['presentation'].get('notes',[])):
                    if claim['id'] in note['claim_ids']:
                        title=nm['display_label']+' '+note['aspect'];correspondence.append(f'[{title}](#{slug(title)})')
            relation_note=(f"**图文对应**：{'、'.join(correspondence)}／{link['aspect']}。" if correspondence else
                           f"**与{group['display_label']}的关系**：从“{link['aspect']}”侧面，{link['relevance']}")
            lines += [f"#### {mapping['display_label']} {detail['title']}", '', relation_note, '',
                      f"**作者命题与出处**：{claim['author_claim']}（{locator_note(claim['author_locator'])}）", '']
            if detail['evidence_note'].lstrip().startswith('|'):
                lines += ['**证据与核查**：','',detail['evidence_note'],'']
            else:
                lines += [f"**证据与核查**：{detail['evidence_note']}", '']
            verdict = VERDICTS[claim['verdict']]
            scope = (claim.get('supported_scope') or '').strip()
            explanation = ''.join([scope, claim['reason']])
            lines += [f"**判断与边界**：**{verdict}**。{explanation}{link['impact']}", '']
    local_sources = [s for s in sources.values() if s.get('kind') == 'pdf' and s.get('path')]
    if local_sources:
        lines += ['**原文来源**：' + '；'.join(
            f"[{s['title']}](<{str(s['path']).replace(chr(92), '/')}>)" for s in local_sources), '']
    return '\n'.join(lines)


def write_report(state, target, overwrite=False, layout='auto', font=None, protected=()):
    """One entry point: validate, draw, then render. Never reseal inputs."""
    start=time.perf_counter()
    validate(state)
    target=Path(target).resolve()
    forbidden={Path(__file__).resolve(),Path(__file__).with_name('diagram.py').resolve(),
               *(Path(p).resolve() for p in protected)}
    forbidden.update(p.resolve() for p in Path(__file__).resolve().parent.glob('*.py'))
    if font is not None:forbidden.add(Path(font).resolve())
    forbidden.update(Path(s['path']).resolve() for s in state['sources'] if s.get('path'))
    if target in forbidden:
        raise ValueError('output must not replace the state, script or a source file')
    if target.exists() and not overwrite:
        raise ValueError('output already exists; choose a new path or explicitly use --overwrite')
    result=dict(blocks=None,backend='text',artifacts=[],warnings=[],layout=[])
    drawing_seconds=0.0
    if selected_layout(state,layout)=='graph':
        if 'graph' not in state['presentation']:
            raise ValueError('complete reviewed graph fields before requesting graph output')
        folder=(target.parent/(target.stem+'.assets')).resolve()
        # An asset directory may not contain or coincide with a protected file.
        if any(p==folder or folder in p.parents for p in forbidden):
            raise ValueError('diagram directory intersects a protected source')
        t=time.perf_counter()
        result=drawing_module().generate(graph_model(state),folder,overwrite=overwrite,font=font,protected=forbidden)
        drawing_seconds=time.perf_counter()-t
    markdown=render(state,result['blocks'],layout)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('w' if overwrite else 'x',encoding='utf-8',newline='\n') as handle:
        handle.write(markdown)
    return dict(output=str(target),report_id=state['presentation']['report_id'],
                backend=result['backend'],artifacts=result['artifacts'],warnings=result['warnings'],
                drawing_seconds=drawing_seconds,total_seconds=time.perf_counter()-start,
                qualification='Rendering and review fingerprints do not certify scientific correctness.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('state', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--overwrite', action='store_true')
    parser.add_argument('--layout', choices=['auto','graph','text'], default='auto')
    parser.add_argument('--font', type=Path, help='Chinese font for static diagrams; unavailable -> Mermaid')
    args = parser.parse_args()
    try:
        source = args.state.resolve(strict=True)
        state = json.loads(source.read_text(encoding='utf-8-sig'))
        target = args.out.resolve()
        protected = {source, Path(__file__).resolve()}
        for item in state.get('sources', []):
            if item.get('path'):
                path = Path(item['path'])
                protected.add((source.parent / path).resolve() if not path.is_absolute() else path.resolve())
        result=write_report(state,target,args.overwrite,args.layout,args.font,protected)
        print(json.dumps(result,ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
