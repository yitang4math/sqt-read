#!/usr/bin/env python3
"""Versioned PDF packets and structural reading-state checks. No semantic grading."""
import argparse
import bisect
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

EXTRACTOR = 'sqt-read-lab-pages-2-native'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True).encode('utf-8')


def emit(obj, save=None):
    output = json.dumps(obj, ensure_ascii=False, indent=2)
    if save:
        path = Path(save).resolve()
        if path.exists():
            raise ValueError('Output already exists; choose a new packet path: ' + str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output + '\n', encoding='utf-8')
    print(output)


def engine():
    try:
        import pymupdf as pdf
    except ImportError:
        try:
            import fitz as pdf
        except ImportError as error:
            raise ValueError('PyMuPDF unavailable; use an available PDF reader or obtain this dependency') from error
    return pdf


def health(text):
    if not text.strip():
        return 'no_searchable_text'
    bad = text.count('\ufffd') + text.count('\x00')
    return 'suspect_text' if bad / max(1, len(text)) > .005 else 'text_available'


def load_pdf(path, cache_dir=None):
    source = Path(path).resolve(strict=True)
    if not source.is_file():
        raise ValueError('Source is not a file')
    data = source.read_bytes()  # Hash and extract the same snapshot, never trust path-only cache.
    source_hash = digest(data)
    pdf = engine()
    version = pdf.VersionBind
    key = digest(encoded([source_hash, EXTRACTOR, version]))
    folder = Path(cache_dir) if cache_dir else Path(tempfile.gettempdir()) / 'sqt-read-lab-cache-v1'
    cache = folder / (key + '.json')
    warnings = []
    body = None
    if cache.exists():
        try:
            candidate = json.loads(cache.read_text(encoding='utf-8'))
            checksum = candidate.pop('checksum')
            valid = (checksum == digest(encoded(candidate)) and candidate['sha256'] == source_hash
                     and candidate['extractor'] == EXTRACTOR and candidate['engine'] == version
                     and isinstance(candidate['pages'], list) and len(candidate['pages']) > 0
                     and all(isinstance(t, str) for t in candidate['pages']))
            if valid:
                body = candidate
            else:
                warnings.append('invalid_cache_reextracted')
        except (OSError, ValueError, KeyError, TypeError):
            warnings.append('unreadable_cache_reextracted')
    if body is None:
        with pdf.open(stream=data, filetype='pdf') as doc:
            if doc.needs_pass:
                raise ValueError('Encrypted PDF requires an unlocked source')
            pages = [page.get_text('text', sort=False) for page in doc]
            body = {'sha256': source_hash, 'extractor': EXTRACTOR, 'engine': version,
                    'metadata': doc.metadata, 'pages': pages}
        try:
            folder.mkdir(parents=True, exist_ok=True)
            cache_body = dict(body, checksum=digest(encoded(body)))
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=str(folder),
                                             suffix='.tmp', delete=False) as handle:
                temp_path = Path(handle.name)
                json.dump(cache_body, handle, ensure_ascii=False)
            temp_path.replace(cache)
        except OSError:
            warnings.append('cache_not_saved')
    identity = {'path': str(source), 'sha256': source_hash, 'page_count': len(body['pages']),
                'extractor': EXTRACTOR, 'engine': version}
    return identity, body, warnings


def parse_pages(spec, count):
    pages = []
    for item in spec.split(','):
        if not re.fullmatch(r'\d+(?:-\d+)?', item.strip()):
            raise ValueError('Pages must be 1-based numbers or ascending ranges, e.g. 1,3-5')
        bounds = [int(n) for n in item.split('-')]
        first, last = bounds[0], bounds[-1]
        if first < 1 or first > last or last > count:
            raise ValueError('Page range outside source or reversed')
        pages.extend(range(first, last + 1))
    return sorted(set(pages))


def inspect_pdf(identity, body, warnings):
    return {'command': 'inspect', 'source': identity, 'metadata_unverified': body['metadata'],
            'pages': [{'page': i, 'characters': len(t), 'text_status': health(t)}
                      for i, t in enumerate(body['pages'], 1)],
            'warnings': warnings, 'coverage_note': 'Extraction inventory only; no pages marked read. Text may have incorrect columns/formulas. Validate document completeness visually.'}


def read_packet(identity, body, spec, offset, limit, warnings):
    pages = parse_pages(spec, identity['page_count'])
    if offset < 0 or offset > len(body['pages'][pages[0] - 1]) or limit < 1:
        raise ValueError('Invalid first-page offset or positive character limit')
    budget, segments, continuation = limit, [], None
    for index, number in enumerate(pages):
        text = body['pages'][number - 1]
        start = offset if index == 0 else 0
        if budget == 0 and start < len(text):
            continuation = {'page': number, 'offset': start, 'remaining_pages': pages[index:]}
            break
        end = min(len(text), start + budget)
        segments.append({'page': number, 'start': start, 'end': end, 'text': text[start:end],
                         'page_text_status': health(text)})
        budget -= end - start
        if end < len(text):
            continuation = {'page': number, 'offset': end, 'remaining_pages': pages[index:]}
            break
    text_count = sum(len(part['text']) for part in segments)
    status = 'partial' if continuation else 'complete_requested_range'
    if text_count == 0:
        status = 'no_text_in_requested_range'
    return {'command': 'read', 'source': identity, 'requested_pages': pages,
            'requested_first_offset': offset, 'status': status, 'segments': segments,
            'continuation': continuation, 'source_characters': text_count, 'warnings': warnings,
            'coverage_note': 'Only returned text is available for reading; completeness applies to requested range, not an abstract, section or whole paper. Empty/suspect pages need visual/OCR recovery.'}


def normalize(raw):
    chars, mapping = [], []
    index = 0
    while index < len(raw):
        char = raw[index]
        # Join alphabetic words hyphenated at a line end; provenance stays in raw offsets.
        if char == '-' and index > 0 and raw[index - 1].isalpha():
            match = re.match(r'-[^\S\n]*\n\s*(?=[^\W\d_])', raw[index:], re.UNICODE)
            if match:
                index += len(match.group(0))
                continue
        if char.isspace():
            if not chars or chars[-1] != ' ':
                chars.append(' ')
                mapping.append(index)
        else:
            for folded in char.casefold():
                chars.append(folded)
                mapping.append(index)
        index += 1
    return ''.join(chars), mapping


def search_packet(identity, body, query, offset, limit, context, warnings):
    if offset < 0 or limit < 1 or context < 0:
        raise ValueError('Invalid search offset/limit/context')
    parts, starts, cursor = [], [], 0
    for text in body['pages']:
        starts.append(cursor)
        parts.append(text)
        cursor += len(text) + 1
    raw = '\n'.join(parts)
    normalized, mapping = normalize(raw)
    needle = normalize(query)[0].strip()
    if not needle:
        raise ValueError('Search query cannot be empty')
    matches = list(re.finditer(re.escape(needle), normalized))

    def location(raw_position):
        page_index = max(0, bisect.bisect_right(starts, raw_position) - 1)
        return {'page': page_index + 1, 'offset': min(raw_position - starts[page_index], len(parts[page_index]))}

    hits = []
    for match in matches[offset:offset + limit]:
        start, end = mapping[match.start()], mapping[match.end() - 1] + 1
        hits.append({'start': location(start), 'end': location(end),
                     'raw_match': raw[start:end], 'context': raw[max(0, start-context):min(len(raw), end+context)],
                     'context_is_complete_sentence': False})
    next_offset = offset + len(hits) if offset + len(hits) < len(matches) else None
    return {'command': 'search', 'source': identity, 'query': query, 'normalization': 'casefold, whitespace, heuristic alphabetic line-end dehyphenation; verify raw text',
            'total_hits': len(matches), 'shown_hits': len(hits), 'skipped_before': min(offset, len(matches)),
            'remaining_after': max(0, len(matches)-offset-len(hits)), 'next_offset': next_offset,
            'hits': hits, 'warnings': warnings,
            'source_characters': sum(len(hit['raw_match']) + len(hit['context']) for hit in hits),
            'unsearchable_pages': [i for i, t in enumerate(parts, 1) if health(t) == 'no_searchable_text'],
            'scope_note': 'All pages including references/appendices. Zero means no match in current text index, not absence from the paper; image-only text and extraction order may differ.'}


def render(path, page, out, dpi):
    source = Path(path).resolve(strict=True)
    destination = Path(out).resolve()
    if destination.exists() or destination == source:
        raise ValueError('Render destination already exists; choose a new output path')
    if not 36 <= dpi <= 300:
        raise ValueError('DPI must be 36..300')
    data = source.read_bytes()
    pdf = engine()
    with pdf.open(stream=data, filetype='pdf') as doc:
        if page < 1 or page > len(doc) or doc.needs_pass:
            raise ValueError('Invalid page or encrypted PDF')
        pixmap = doc[page - 1].get_pixmap(dpi=dpi)
        destination.parent.mkdir(parents=True, exist_ok=True)
        pixmap.save(str(destination))
    return {'command': 'render', 'source_sha256': digest(data), 'page': page,
            'image_path': str(destination), 'width': pixmap.width, 'height': pixmap.height,
            'coverage_note': 'Rendered, not yet visually inspected. View this image before recording visual_checked.'}


def verify_state(path):
    state_path = Path(path).resolve(strict=True)
    state = json.loads(state_path.read_text(encoding='utf-8'))
    errors, checked = [], {}
    required = ('schema_version', 'mode', 'user_goal', 'completion', 'sources', 'questions', 'claims', 'evidence', 'coverage', 'history', 'next')
    for field in required:
        if field not in state:
            errors.append('missing field: ' + field)
    if errors:
        return {'valid': False, 'errors': errors}
    if state['schema_version'] != 1:
        errors.append('unsupported schema_version')
    if not isinstance(state['coverage'], dict):
        errors.append('coverage must be an object')
    else:
        for field in ('text', 'visual', 'acquired_unread', 'missing'):
            if not isinstance(state['coverage'].get(field), list):
                errors.append('coverage.' + field + ' must be an array')
        for field in ('text', 'visual'):
            if isinstance(state['coverage'].get(field), list) and not all(isinstance(item, dict) for item in state['coverage'][field]):
                errors.append('coverage.' + field + ' must contain objects')
    for field in ('history', 'next'):
        if not isinstance(state[field], list) or not all(isinstance(item, dict) for item in state[field]):
            errors.append(field + ' must be an array of objects')
    if errors:
        return {'valid': False, 'errors': errors}

    def ids(field):
        items = state[field]
        if not isinstance(items, list) or not all(isinstance(item, dict) and isinstance(item.get('id'), str) for item in items):
            raise ValueError(field + ' must be an array of objects with string IDs')
        values = [item['id'] for item in items]
        if len(set(values)) != len(values):
            errors.append('duplicate IDs: ' + field)
        return {item['id']: item for item in items}

    sources, questions, claims, evidence = [ids(f) for f in ('sources', 'questions', 'claims', 'evidence')]
    for sid, source in sources.items():
        if source.get('availability') not in ('acquired', 'missing'):
            errors.append(sid + ': invalid availability')
        if source.get('availability') == 'acquired' and source.get('kind') != 'external':
            try:
                local = Path(source['path'])
                if not local.is_absolute():
                    local = state_path.parent / local
                actual = digest(local.read_bytes())
                if actual != source.get('sha256'):
                    errors.append(sid + ': source changed; historical judgments require recheck')
                if source.get('kind') == 'pdf':
                    identity, body, _ = load_pdf(local)
                    checked[sid] = body['pages']
                    if source.get('page_count') != identity['page_count']:
                        errors.append(sid + ': page_count mismatch')
                    if source.get('extractor') != identity['extractor'] or source.get('engine') != identity['engine']:
                        errors.append(sid + ': extraction profile changed or missing; relocate text offsets')
            except (KeyError, OSError, ValueError) as error:
                errors.append(sid + ': source unavailable: ' + str(error))

    def locator(source_id, loc, label):
        if not isinstance(loc, dict):
            errors.append(label + ': locator must be an object')
            return
        if source_id in checked:
            page = loc.get('page')
            if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= len(checked[source_id]):
                errors.append(label + ': invalid PDF page')
                return
            if 'start' in loc or 'end' in loc:
                start, end = loc.get('start'), loc.get('end')
                if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start <= end <= len(checked[source_id][page-1]):
                    errors.append(label + ': invalid PDF offsets')

    for qid, question in questions.items():
        if not question.get('text') or question.get('basis') not in ('source', 'inference', 'unresolved'):
            errors.append(qid + ': missing question text/basis')
        if any(sid not in sources for sid in question.get('source_ids', [])):
            errors.append(qid + ': unknown source ID')
        if question.get('parent_id') and question['parent_id'] not in questions:
            errors.append(qid + ': unknown parent question')
    for eid, item in evidence.items():
        sid = item.get('source_id')
        if sid not in sources:
            errors.append(eid + ': unknown source ID')
            continue
        inspection = item.get('inspection')
        if inspection not in ('located', 'text_checked', 'visual_checked', 'proof_checked', 'reproduced'):
            errors.append(eid + ': invalid inspection action')
        if inspection != 'located' and sources[sid].get('availability') != 'acquired':
            errors.append(eid + ': cannot check unavailable source')
        if not item.get('type') or not item.get('inspection_detail'):
            errors.append(eid + ': missing type or inspection detail')
        locator(sid, item.get('locator'), eid)
        if sid in checked and isinstance(item.get('locator'), dict):
            loc = item['locator']
            if inspection in ('text_checked', 'proof_checked'):
                covered = any(span.get('source_id') == sid and span.get('page') == loc.get('page')
                              and (loc.get('start') is None or span.get('start', -1) <= loc['start'])
                              and (loc.get('end') is None or span.get('end', -1) >= loc['end'])
                              for span in state['coverage']['text'])
                if not covered:
                    errors.append(eid + ': text/proof check absent from declared reading coverage')
            if inspection == 'visual_checked' and not any(span.get('source_id') == sid and span.get('page') == loc.get('page') for span in state['coverage']['visual']):
                errors.append(eid + ': visual check absent from declared visual coverage')
        for link in item.get('links', []):
            if link.get('claim_id') not in claims or link.get('relation') not in ('for', 'against', 'context') or not link.get('scope'):
                errors.append(eid + ': invalid claim link/relation/scope')
    for cid, claim in claims.items():
        if claim.get('question_id') not in questions or not claim.get('author_claim') or not claim.get('reason'):
            errors.append(cid + ': missing question, author claim or reason')
        verdict = claim.get('verdict')
        if verdict not in ('supported', 'limited', 'counter', 'pending'):
            errors.append(cid + ': invalid verdict')
        eids = claim.get('evidence_ids', [])
        if any(eid not in evidence for eid in eids):
            errors.append(cid + ': unknown evidence ID')
        if verdict in ('supported', 'limited', 'counter'):
            relation = 'against' if verdict == 'counter' else 'for'
            relevant = [evidence[eid] for eid in eids if eid in evidence and evidence[eid].get('inspection') != 'located'
                        and any(link.get('claim_id') == cid and link.get('relation') == relation for link in evidence[eid].get('links', []))]
            if not relevant:
                errors.append(cid + ': verdict lacks checked evidence with appropriate relation')
            if not claim.get('supported_scope') or not claim.get('author_locator'):
                errors.append(cid + ': decided claim needs explicit scope and author locator')
        aloc = claim.get('author_locator')
        if aloc:
            if aloc.get('source_id') not in sources:
                errors.append(cid + ': author locator source missing')
            else:
                locator(aloc['source_id'], aloc, cid + ' author')
    coverage = state['coverage']
    for field in ('text', 'visual'):
        for item in coverage.get(field, []):
            sid = item.get('source_id')
            if sid not in sources or sources[sid].get('availability') != 'acquired':
                errors.append('coverage: source not acquired')
            else:
                locator(sid, item, 'coverage ' + field)
    for task in state['next']:
        if task.get('claim_id') is not None and task.get('claim_id') not in claims:
            errors.append('next: unknown claim ID')
        if any(not task.get(field) for field in ('location', 'action', 'decides', 'stop_condition')):
            errors.append('next: incomplete executable task')
    for change in state['history']:
        if any(field not in change for field in ('id', 'before', 'after', 'why', 'evidence_ids')):
            errors.append('history: incomplete change record')
        if any(eid not in evidence for eid in change.get('evidence_ids', [])):
            errors.append('history: unknown evidence ID')
    return {'command': 'verify-state', 'valid': not errors, 'errors': errors,
            'checked_pdf_sources': list(checked), 'qualification': 'Structural/provenance check only; does not certify semantic correctness, reading actions or replication.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('inspect', 'read', 'search', 'render'):
        command = commands.add_parser(name)
        command.add_argument('pdf')
        command.add_argument('--cache-dir')
        command.add_argument('--save')
        if name == 'read':
            command.add_argument('--pages', required=True)
            command.add_argument('--offset', type=int, default=0)
            command.add_argument('--limit', type=int, default=12000)
        if name == 'search':
            command.add_argument('--query', required=True)
            command.add_argument('--offset', type=int, default=0)
            command.add_argument('--limit', type=int, default=10)
            command.add_argument('--context', type=int, default=160)
        if name == 'render':
            command.add_argument('--page', type=int, required=True)
            command.add_argument('--out', required=True)
            command.add_argument('--dpi', type=int, default=130)
    command = commands.add_parser('verify-state')
    command.add_argument('state')
    args = parser.parse_args()
    try:
        if args.command == 'verify-state':
            result = verify_state(args.state)
            emit(result)
            return 0 if result['valid'] else 2
        if args.command == 'render':
            result = render(args.pdf, args.page, args.out, args.dpi)
        else:
            identity, body, warnings = load_pdf(args.pdf, args.cache_dir)
            if args.command == 'inspect':
                result = inspect_pdf(identity, body, warnings)
            elif args.command == 'read':
                result = read_packet(identity, body, args.pages, args.offset, args.limit, warnings)
            else:
                result = search_packet(identity, body, args.query, args.offset, args.limit, args.context, warnings)
        if args.save and Path(args.save).resolve() == Path(args.pdf).resolve():
            raise ValueError('Packet destination must not overwrite the source')
        emit(result, args.save)
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        emit({'command': args.command, 'status': 'error', 'error': str(error),
              'recovery': 'Check source/arguments; for unreadable PDF use an unlocked source or visual/OCR reader. Do not treat extraction failure as absent evidence.'})
        return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
