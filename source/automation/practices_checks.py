#!/usr/bin/env python3
"""Offline content and provenance gates for the Atlas Practices collection.

These checks detect missing operational content and structural regressions.
They do not certify the effectiveness of a practice or replace editorial review.
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
from pathlib import Path

TEXT_FIELDS = ('purpose', 'example', 'editorial_note')
LIST_FIELDS = {'when_to_use': 2, 'when_not_to_use': 1, 'prerequisites': 2,
               'steps': 4, 'verification': 3, 'outputs': 1, 'risks': 2,
               'related_practices': 2}
OPERATIONAL_FIELDS = ('purpose', 'when_to_use', 'when_not_to_use', 'prerequisites',
                      'steps', 'example', 'verification', 'outputs', 'risks')


def word_count(node):
    practice = node.get('attributes', {}).get('practice', {})
    parts = [node.get('summary', ''), node.get('limitation', '')]
    for key in OPERATIONAL_FIELDS:
        value = practice.get(key, '')
        parts.extend(value if isinstance(value, list) else [value])
    return len(re.findall(r"\b[\w]+(?:['’-][\w]+)*\b", ' '.join(parts)))


def validate_practices(payload, baseline=None, book=None, *, required=False):
    checks = []

    def check(name, ok, detail=None):
        row = {'check': name, 'passed': bool(ok)}
        if detail is not None:
            row['detail'] = detail
        checks.append(row)

    records = [n for n in payload['nodes'] if n['kind'] == 'practice_descriptor']
    families = [n for n in payload['nodes'] if n['kind'] == 'practice_family']
    occurrences = [n for n in payload['nodes'] if n['kind'] == 'practice_occurrence']
    by = {n['id']: n for n in payload['nodes']}
    expected = required or bool(payload.get('meta', {}).get('practices')) or bool(baseline and (baseline.get('meta', {}).get('practices') or any(n.get('collection') == 'PAT' for n in baseline['nodes'])))
    present = any(n.get('collection') == 'PAT' for n in records)
    if not present and not expected:
        return {'schema_version': 1, 'kind': 'atlas_practices_validation',
                'applicable': False, 'passed': 0, 'failed': 0, 'checks': []}
    check('The expected PAT collection is present', present)
    check('Every practice descriptor belongs to PAT', all(n.get('collection') == 'PAT' for n in records))
    check('PAT contains only practice descriptors', all(n['kind'] == 'practice_descriptor' for n in payload['nodes'] if n.get('collection') == 'PAT'))
    check('Families and historical occurrences remain contextual records', all(n.get('collection') is None for n in families + occurrences))
    if baseline:
        for kind in ('practice_descriptor', 'practice_family', 'practice_occurrence'):
            prior_ids = [n['id'] for n in baseline['nodes'] if n['kind'] == kind]
            new_ids = [n['id'] for n in payload['nodes'] if n['kind'] == kind]
            check('All historical IDs retained: ' + kind, set(prior_ids).issubset(new_ids))
    check('Every family has an English label, purpose and explanation', all(n.get('summary') and n['attributes'].get('purpose') and n['attributes'].get('language') == 'en' for n in families))
    family_ids = {n['id'] for n in families}
    check('All practice-layer nodes have one valid family', all(len(n.get('families', [])) == 1 and n['families'][0] in family_ids for n in records + families + occurrences))
    check('Every descriptor has explicit stream and topic classification', all(n.get('streams') and n.get('topics') for n in records))
    check('Practices do not masquerade as literal bibliography citations', all(not n.get('actual') and not n.get('printed') for n in records))
    counts, problems = [], []
    for node in records:
        a = node['attributes']
        p = a.get('practice', {})
        if p.get('schema_version') != 1 or p.get('language') != 'en':
            problems.append([node['id'], 'Missing current English content schema'])
        for field in TEXT_FIELDS:
            if not isinstance(p.get(field), str) or not p[field].strip():
                problems.append([node['id'], field])
        for field, minimum in LIST_FIELDS.items():
            value = p.get(field)
            if not isinstance(value, list) or len(value) < minimum or any(not isinstance(x, str) or not x.strip() for x in value):
                problems.append([node['id'], field])
            elif len(value) != len(set(value)):
                problems.append([node['id'], 'Duplicate entries in ' + field])
        if not node.get('summary', '').strip() or not node.get('limitation', '').strip() or not a.get('required_revision', '').strip():
            problems.append([node['id'], 'Missing summary, limitation or translated revision'])
        if not p.get('example', '').startswith('Illustrative example:'):
            problems.append([node['id'], 'Example is not explicitly illustrative'])
        if any(x == node['id'] or x not in by or by[x]['kind'] != 'practice_descriptor' for x in p.get('related_practices', [])):
            problems.append([node['id'], 'Invalid related practice'])
        words = word_count(node)
        counts.append({'id': node['id'], 'words': words, 'family': a.get('family')})
        if words < 260:
            problems.append([node['id'], 'Operational content below 260 words', words])
        if not p.get('source_basis') or not a.get('historical_occurrence_ids'):
            problems.append([node['id'], 'Missing editorial source basis or occurrence trail'])
        if not p.get('chapter_references'):
            problems.append([node['id'], 'Missing thematic reading route'])
        for ref in p.get('chapter_references', []):
            if ref.get('id') not in by or by[ref['id']].get('collection') != 'N':
                problems.append([node['id'], 'Invalid chapter reference'])
        for oid in a.get('historical_occurrence_ids', []):
            if oid not in by or by[oid]['kind'] != 'practice_occurrence':
                problems.append([node['id'], 'Invalid historical occurrence'])
    check('Every practice has complete substantive operational content', not problems, problems)
    check('Practice summaries are distinct', len({n['summary'].casefold() for n in records}) == len(records))
    check('Illustrative examples are distinct', len({n['attributes'].get('practice', {}).get('example', '').casefold() for n in records}) == len(records))
    check('All historical occurrences resolve to a current descriptor', all(n['attributes'].get('practice_id') in by and by[n['attributes']['practice_id']]['kind'] == 'practice_descriptor' for n in occurrences))
    if book:
        known = {c['id']: c for c in book['chapters']}
        wrong = []
        for n in records:
            for ref in n['attributes'].get('practice', {}).get('source_basis', []):
                if ref.get('type') != 'published_book_thematic_context':
                    continue
                c = known.get(ref.get('chapter_id'))
                if not c or ref.get('file') != c['root_file'] or ref.get('sha256') != c['root_sha256'] or ref.get('source_version') != book['meta']['source_version']:
                    wrong.append([n['id'], ref])
        check('Thematic source locators match the current supplied published book', not wrong, wrong)
    summary = {'records': len(records), 'families': len(families), 'historical_occurrences': len(occurrences),
               'words_min': min((r['words'] for r in counts), default=0),
               'words_max': max((r['words'] for r in counts), default=0),
               'words_total': sum(r['words'] for r in counts),
               'by_family': dict(sorted(collections.Counter(n['attributes']['family'] for n in records).items()))}
    return {'schema_version': 1, 'kind': 'atlas_practices_validation', 'applicable': True,
            'passed': sum(c['passed'] for c in checks), 'failed': sum(not c['passed'] for c in checks),
            'summary': summary, 'per_practice': counts, 'checks': checks,
            'editorial_boundary': 'Depth gates check content completeness and provenance. The examples and steps are editorial guidance, not new empirical findings.'}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--book', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    read = lambda p: json.loads(p.read_text(encoding='utf-8')) if p else None
    report = validate_practices(read(args.payload), read(args.baseline), read(args.book))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('passed', 'failed', 'summary') if k in report}, ensure_ascii=False))
    raise SystemExit(bool(report['failed']))


if __name__ == '__main__':
    main()
