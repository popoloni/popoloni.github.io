#!/usr/bin/env python3
"""Explicit, reviewed W-collection migration for the Knowledge Atlas.

The routine article updater intentionally does not edit the foundational W
collection. This adapter is a separately named operation with its own review,
coverage and preservation checks. It appends stable W IDs, revises only named W
records, preserves every historical edge and leaves the book and other source
collections unchanged. It performs no network retrieval or empirical validation.
"""
from __future__ import annotations

import collections
import copy
import datetime as dt
import html
import ipaddress
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

KIND = 'atlas_polimi_update/1'
EDITABLE = {'label', 'summary', 'limitation', 'url', 'authors', 'year', 'streams', 'topics', 'mapped'}
PROTECTED = {'id', 'collection', 'kind', 'actual', 'printed', 'edition_id', 'source_version',
             'atlas_revision_history', 'atlas_editorial_revisions', 'atlas_added_release', 'atlas_added_date'}
EVIDENCE_ACCESS = {'full_public', 'restricted_preview', 'metadata_only', 'bibliography_only'}
MIRRORS = {'label': 'label', 'summary': 'contribution', 'limitation': 'limitation',
           'url': 'source', 'year': 'year'}
GROUP_FIELDS = {'streams': 'themes', 'topics': 'topics', 'mapped': 'chapters'}
TEXT_FIELDS = {'label', 'summary', 'limitation', 'url', 'authors', 'year'}


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _date(value, field):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError(field + ' must be YYYY-MM-DD')
    dt.date.fromisoformat(value)
    return value


def _url(value, field):
    from atlas_graph import canonical_url
    if not _text(value):
        raise ValueError(field + ' requires a public HTTP(S) URL')
    parsed = urlsplit(canonical_url(value))
    host = parsed.hostname or ''
    if parsed.port not in (None, 80, 443) or host == 'localhost' or host.endswith(('.local', '.localhost', '.internal')):
        raise ValueError(field + ' must identify a public source')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError(field + ' must identify a public source')
    return parsed


def _evidence(item, date, field):
    ev = item.get('evidence') or item.get('attributes', {}).get('evidence_review') or item.get('attributes_patch', {}).get('evidence_review')
    if not isinstance(ev, dict) or ev.get('reviewed_on') != date or ev.get('access') not in EVIDENCE_ACCESS:
        raise ValueError(field + ' requires dated evidence_review and an explicit access classification')
    parsed = _url(ev.get('url'), field + '.evidence_review.url')
    if not any(_text(ev.get(k)) for k in ('scope', 'locator', 'note')):
        raise ValueError(field + ' evidence must identify the inspected material and its limits')
    if ev['access'] == 'bibliography_only' and parsed.hostname not in {'www.sepolimi.com', 'sepolimi.com'}:
        raise ValueError('bibliography_only evidence must identify the actual SEPolimi discovery record')
    return ev


def validate_review(review, state):
    """Validate the named migration without weakening the O/P/F procedure."""
    if review.get('kind') != KIND or review.get('schema_version') != 1:
        raise ValueError('Unsupported Polimi migration schema')
    for field in ('baseline_sha256', 'baseline_payload_sha256', 'baseline_release', 'release', 'date'):
        if review.get(field) != state.get(field):
            raise ValueError('Polimi review does not match the frozen run: ' + field)
    _date(review['date'], 'review.date')
    if review.get('book_policy') != 'unchanged':
        raise ValueError('The W migration requires book_policy=unchanged')
    editorial = review.get('editorial_review', {})
    if editorial.get('status') != 'complete' or not all(_text(editorial.get(f)) for f in ('reviewer', 'scope')):
        raise ValueError('Complete and name the editorial review before building')
    coverage = review.get('coverage', {})
    if coverage.get('status') not in {'complete', 'complete_with_disclosed_limits'} or coverage.get('through') != review['date']:
        raise ValueError('Record the reviewed W coverage through the update date')
    limits = coverage.get('limitations', [])
    if not isinstance(limits, list) or any(not _text(x) for x in limits):
        raise ValueError('coverage.limitations must be a list of explicit statements')
    if coverage['status'] == 'complete_with_disclosed_limits' and not limits:
        raise ValueError('Limited coverage requires a concrete limitation')
    sources = coverage.get('sources')
    if not isinstance(sources, list) or not sources:
        raise ValueError('The W migration requires its SEPolimi discovery source')
    official = False
    for source in sources:
        if source.get('collection') != 'W' or source.get('status') not in {'complete', 'limited'} or not _text(source.get('method')):
            raise ValueError('This migration reviews W coverage only; each source needs method and status')
        urls = source.get('urls')
        if not isinstance(urls, list) or not urls:
            raise ValueError('coverage.sources requires explicit URLs')
        for url in urls:
            official |= _url(url, 'coverage.sources.urls').hostname in {'www.sepolimi.com', 'sepolimi.com'}
    if not official:
        raise ValueError('Coverage must identify an official SEPolimi page')
    for operation in ('additions', 'revisions', 'edges'):
        if not isinstance(review.get(operation, []), list) or any(not isinstance(x, dict) for x in review.get(operation, [])):
            raise ValueError(operation + ' must be a list of reviewed operations')
    identifiers = []
    for i, addition in enumerate(review.get('additions', [])):
        if addition.get('collection') != 'W' or addition.get('kind') != 'paper' or not re.fullmatch(r'W\d{3,}', str(addition.get('id', ''))):
            raise ValueError('W additions require explicit Wnnn ID, collection W and kind paper')
        identifiers.append(addition['id'])
        if any(not _text(addition.get(f)) for f in TEXT_FIELDS):
            raise ValueError('Each W addition requires label, authors, year, URL, summary and limitation')
        _url(addition['url'], 'addition.url')
        _evidence(addition, review['date'], f'addition[{i}]')
        attrs = addition.get('attributes', {})
        if not _text(attrs.get('provenance')) or not _text(attrs.get('publication_status')):
            raise ValueError('Each W addition requires provenance and an honestly qualified publication_status')
        if addition.get('actual') or addition.get('printed') or addition.get('volumes'):
            raise ValueError('New W records cannot claim current book citations, bibliography or source-volume membership')
    for i, revision in enumerate(review.get('revisions', [])):
        if not re.fullmatch(r'W\d{3,}', str(revision.get('id', ''))) or not _text(revision.get('reason')):
            raise ValueError('Revisions require an existing W ID and an explicit reason')
        identifiers.append(revision['id'])
        if not isinstance(revision.get('patch', {}), dict) or not isinstance(revision.get('attributes_patch', {}), dict):
            raise ValueError('Revision patches must be objects')
        if set(revision.get('patch', {})) - EDITABLE:
            raise ValueError('Revision attempts to change protected identity or book fields')
        _evidence(revision, review['date'], f'revision[{i}]')
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('A W record must have one consolidated addition or revision per review')
    for item in review.get('candidate_decisions', []):
        if not isinstance(item, dict) or item.get('decision') not in {'add', 'revise', 'exclude', 'already_present', 'defer'} or not _text(item.get('reason')):
            raise ValueError('Every candidate disposition needs a reason')
    return {'kind': KIND, 'status': 'complete', 'additions': len(review.get('additions', [])), 'revisions': len(review.get('revisions', []))}


def _identity(value):
    from atlas_graph import canonical_url
    value = canonical_url(value)
    # An arXiv version or DOI host spelling does not create a new study.
    value = re.sub(r'(?i)^https://(?:www\.)?arxiv\.org/(?:html|pdf|abs)/', 'https://arxiv.org/abs/', value)
    value = re.sub(r'(?<=\d)v\d+(?:\.pdf)?$', '', value)
    if value.startswith(('https://doi.org/', 'https://dx.doi.org/')):
        value = value.replace('https://dx.doi.org/', 'https://doi.org/').lower()
    return value


def migrate_payload(baseline, review):
    from atlas_graph import payload_sha256, validate_payload
    validate_payload(baseline)
    if payload_sha256(baseline) != review['baseline_payload_sha256']:
        raise ValueError('W migration baseline payload checksum differs')
    D = copy.deepcopy(baseline)
    by = {n['id']: n for n in D['nodes']}
    indexes = {n['id']: i for i, n in enumerate(D['nodes'])}
    before_w = [n['id'] for n in baseline['nodes'] if n.get('collection') == 'W']
    maximum = max((int(n[1:]) for n in before_w), default=0)
    added = review.get('additions', [])
    expected = [f'W{maximum + i + 1:03}' for i in range(len(added))]
    if [n['id'] for n in added] != expected:
        raise ValueError('New W IDs must append contiguously in reviewed order: ' + ', '.join(expected))
    digest = payload_sha256(review)
    changes, added_nodes, added_edges = [], [], []
    revised_ids = {r['id'] for r in review.get('revisions', [])}
    aliases = {}

    def change(n, field, value, reason, attribute=False):
        target = n['attributes'] if attribute else n
        if field in target and target[field] == value:
            return
        n['attributes'].setdefault('atlas_revision_history', []).append({
            'release': review['release'], 'date': review['date'], 'reason': reason,
            'field': ('attributes.' if attribute else '') + field,
            'previous_present': field in target, 'previous': copy.deepcopy(target.get(field))})
        target[field] = copy.deepcopy(value)
        changes.append({'id': n['id'], 'field': ('attributes.' if attribute else '') + field})

    for supplied in added:
        nid = supplied['id']
        if nid in by:
            raise ValueError('Existing node ID cannot be reused: ' + nid)
        n = {'id': nid, 'label': supplied['label'], 'kind': 'paper', 'collection': 'W', 'category': None,
             'streams': [], 'topics': [], 'mapped': [], 'actual': [], 'volumes': [], 'printed': False,
             'summary': supplied['summary'], 'limitation': supplied['limitation'], 'url': supplied['url'],
             'authors': supplied['authors'], 'year': supplied['year'], 'attributes': copy.deepcopy(supplied.get('attributes', {}))}
        for field in GROUP_FIELDS:
            n[field] = copy.deepcopy(supplied.get(field, []))
        if not n['streams']:
            raise ValueError('Each new W record must name its main SEPolimi stream: ' + nid)
        n['attributes']['evidence_review'] = copy.deepcopy(_evidence(supplied, review['date'], nid))
        for field, mirror in MIRRORS.items():
            if mirror in n['attributes'] and n['attributes'][mirror] != n[field]:
                raise ValueError(f'Conflicting normalized/attribute value: {nid}.{field}')
            n['attributes'][mirror] = n[field]
        n['attributes'].setdefault('summary', n['summary'])
        n['attributes'].setdefault('authors', n['authors'])
        n['attributes'].update(atlas_added_release=review['release'], atlas_added_date=review['date'],
            manuscript_citation_status='COMPANION_READING_ABSENT_FROM_CURRENT_BOOK',
            ndse2_actual_chapters_json='[]', ndse2_in_bibliography=False)
        indexes[nid] = len(D['nodes'])
        D['nodes'].append(n)
        by[nid] = n
        added_nodes.append(nid)
        if supplied.get('ref'):
            alias = '$' + str(supplied['ref']).lstrip('$')
            if alias in aliases:
                raise ValueError('Duplicate W addition alias')
            aliases[alias] = nid

    for revision in review.get('revisions', []):
        nid = revision['id']
        if nid not in by or nid in added_nodes or by[nid].get('collection') != 'W':
            raise ValueError('Revision must target an existing W record: ' + nid)
        n = by[nid]
        patch = copy.deepcopy(revision.get('patch', {}))
        attrs = copy.deepcopy(revision.get('attributes_patch', {}))
        for field in attrs:
            if field in PROTECTED or field.startswith('ndse2_'):
                raise ValueError('W revision changes protected attribute: ' + field)
        for field, value in patch.items():
            change(n, field, value, revision['reason'])
            if field in MIRRORS:
                mirror = MIRRORS[field]
                if mirror in attrs and attrs[mirror] != value:
                    raise ValueError(f'Conflicting revision/display values: {nid}.{field}')
                attrs[mirror] = value
            if field == 'summary' and 'summary' not in attrs:
                attrs['summary'] = value
            if field == 'authors' and 'authors' not in attrs:
                attrs['authors'] = value
        attrs['evidence_review'] = copy.deepcopy(_evidence(revision, review['date'], nid))
        for field, value in attrs.items():
            change(n, field, value, revision['reason'], attribute=True)
        n['attributes'].setdefault('atlas_editorial_revisions', []).append({
            'release': review['release'], 'date': review['date'], 'reason': revision['reason'],
            'evidence': copy.deepcopy(attrs['evidence_review'])})

    touched = set(added_nodes) | revised_ids
    known_groups = {field: {g['id'] for g in D[group]} for field, group in GROUP_FIELDS.items()}
    for nid in touched:
        n = by[nid]
        for field in TEXT_FIELDS:
            if not isinstance(n.get(field), str):
                raise ValueError(f'{nid}.{field} must be a string')
        _url(n['url'], nid + '.url')
        for field, known in known_groups.items():
            if not isinstance(n[field], list) or any(not isinstance(x, str) for x in n[field]) or len(set(n[field])) != len(n[field]) or not set(n[field]).issubset(known):
                raise ValueError(f'{nid}.{field} contains unknown or duplicate group IDs')
        for field in ('publication_date', 'updated_date', 'latest_activity_date'):
            if n['attributes'].get(field):
                _date(n['attributes'][field], nid + '.' + field)
        if not set(n['actual']).issubset(n['mapped']):
            raise ValueError('A revision removed a current literal-citation chapter from its mapped reading view')

    # Shared historical bibliography-index URLs are retained. Newly introduced
    # source URLs must not duplicate another source record or one another.
    identities = collections.defaultdict(list)
    for n in D['nodes']:
        if n.get('collection') in {'W', 'O', 'P', 'F'} and n.get('url'):
            identities[_identity(n['attributes'].get('canonical_url') or n['url'])].append(n['id'])
    for values in identities.values():
        if len(values) > 1 and set(values).intersection(added_nodes):
            raise ValueError('Duplicate new study URL; revise the existing record instead: ' + ', '.join(values))

    family_map = {r['id']: r['family'] for r in D['relations']}
    valid_families = {f['id'] for f in D['edgeFamilies']}
    keyed = {(e['source'], e['target'], json.dumps(e['key'], sort_keys=True)) for e in D['edges']}
    for ordinal, supplied in enumerate(review.get('edges', [])):
        source = aliases.get(supplied.get('source'), supplied.get('source'))
        target = aliases.get(supplied.get('target'), supplied.get('target'))
        relation, family = supplied.get('relation', ''), supplied.get('family')
        if source not in by or target not in by or not {source, target}.intersection(touched):
            raise ValueError('New relationships must connect a reviewed W record to a known node')
        if family not in valid_families or family == 'actual' or relation.startswith(('NDSE2_', 'CITED_')):
            raise ValueError('New W relationships must not claim book citations')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_:. -]*', relation) or (relation in family_map and family_map[relation] != family):
            raise ValueError('Invalid relationship name or changed relationship family')
        attrs = copy.deepcopy(supplied.get('attributes', {}))
        if not _text(attrs.get('provenance')):
            raise ValueError('Every W relationship requires explicit provenance')
        if attrs.get('relation', relation) != relation:
            raise ValueError('Relationship attributes conflict with the normalized relation')
        attrs['relation'] = relation
        eid = f'polimi_{digest[:16]}_{ordinal:05}'
        key = supplied.get('key', f'POLIMI:{digest[:16]}:{ordinal:05}:{relation}')
        identity = indexes[source], indexes[target], json.dumps(key, sort_keys=True)
        if identity in keyed or any(e['id'] == eid for e in D['edges']):
            raise ValueError('Duplicate W keyed relationship')
        D['edges'].append({'id': eid, 'source': indexes[source], 'target': indexes[target],
                           'key': key, 'relation': relation, 'family': family, 'attributes': attrs})
        keyed.add(identity)
        family_map[relation] = family
        added_edges.append(eid)

    memberships = {(D['nodes'][e['source']]['id'], D['nodes'][e['target']]['id'], e['relation']) for e in D['edges']}
    for nid in added_nodes:
        n = by[nid]
        expected_edges = [(x, 'PRIMARY_STREAM' if i == 0 else 'SECONDARY_STREAM') for i, x in enumerate(n['streams'])]
        expected_edges += [(x, 'ADDRESSES_TOPIC') for x in n['topics']] + [(x, 'INFORMS_CHAPTER') for x in n['mapped']]
        if any((nid, target, relation) not in memberships for target, relation in expected_edges):
            raise ValueError('W display groups require matching explicit classification/mapping edges: ' + nid)

    relation_counts = collections.Counter(e['relation'] for e in D['edges'])
    old_relation_ids = {r['id'] for r in D['relations']}
    D['relations'] = [{**r, 'count': relation_counts[r['id']]} for r in D['relations']] + [
        {'id': rid, 'label': rid.replace('_', ' ').title(), 'family': family_map[rid], 'count': relation_counts[rid]}
        for rid in sorted(set(relation_counts) - old_relation_ids)]
    family_counts = collections.Counter(e['family'] for e in D['edges'])
    D['edgeFamilies'] = [{**g, 'count': family_counts[g['id']]} for g in D['edgeFamilies']]
    group_counts = collections.Counter(n.get('category') for n in D['nodes'] if not n.get('collection'))
    D['nodeGroups'] = [{**g, 'count': group_counts[g['id']]} for g in D['nodeGroups']]
    counts = dict(collections.Counter(n.get('collection') for n in D['nodes'] if n.get('collection')))
    meta = D['meta']
    meta.setdefault('atlas_metadata_history', []).append({'release_before_update': baseline['meta'].get('edition'),
        'date_before_update': baseline['meta'].get('date'), 'graphAttributes': copy.deepcopy(baseline['meta'].get('graphAttributes', {}))})
    meta.update(edition='v' + review['release'], date=review['date'], nodeCount=len(D['nodes']),
                edgeCount=len(D['edges']), relationCount=len(D['relations']))
    meta.pop('graphSha256', None)
    meta['polimi_update'] = {'kind': KIND, 'date': review['date'], 'baseline_count': len(before_w),
                            'current_count': counts['W'], 'added_ids': added_nodes, 'revised_ids': sorted(revised_ids),
                            'coverage': copy.deepcopy(review['coverage'])}
    meta.setdefault('graphAttributes', {}).update(portable_atlas_release='v' + review['release'],
        portable_atlas_snapshot_date=review['date'], atlas_update='v' + review['release'] + '_' + review['date'].replace('-', ''),
        polimi_records=counts['W'], polimi_update_kind=KIND, polimi_review=release_paths(review)['research_audit'],
        portable_atlas_basis='Pinned published repository baseline plus a separately reviewed W-collection migration; book metadata and other collections unchanged',
        graphml_key_encoding='atlas_original_key_json retains each original keyed-edge identity')
    meta.setdefault('notes', []).append(f"SEPolimi update {review['date']}: {len(added_nodes)} new W records and {len(revised_ids)} revised records; access limits and original-source checks are recorded per record.")
    meta.setdefault('automation_updates', []).append({'kind': KIND, 'review_digest': digest, 'release': review['release'],
        'date': review['date'], 'baseline_payload_sha256': review['baseline_payload_sha256'], 'baseline_zip_sha256': review['baseline_sha256']})
    validate_payload(D)
    if [n['id'] for n in D['nodes'][:len(baseline['nodes'])]] != [n['id'] for n in baseline['nodes']] or D['edges'][:len(baseline['edges'])] != baseline['edges']:
        raise ValueError('W migration changed historical graph identity or keyed edges')
    if any(old != new for old, new in zip(baseline['nodes'], D['nodes']) if old['id'] not in revised_ids):
        raise ValueError('W migration modified an unreviewed baseline record')
    for old, new in zip(baseline['nodes'], D['nodes']):
        if any(old.get(f) != new.get(f) for f in ('actual', 'printed', 'volumes')):
            raise ValueError('W migration changed book/source-volume membership')
    audit = {'kind': KIND, 'date': review['date'], 'release': review['release'], 'no_changes': False,
        'baseline_payload_sha256': payload_sha256(baseline), 'result_payload_sha256': payload_sha256(D),
        'baseline_nodes': len(baseline['nodes']), 'baseline_edges': len(baseline['edges']),
        'nodes': len(D['nodes']), 'edges': len(D['edges']), 'relation_types': len(D['relations']),
        'source_counts': counts, 'source_additions': added_nodes, 'new_source_ids': added_nodes,
        'changed_source_ids': sorted(revised_ids), 'added_nodes': added_nodes, 'added_edges': added_edges, 'changes': changes,
        'assigned_ids': [{'position': i, 'id': n['id'], 'ref': n.get('ref')} for i, n in enumerate(added)],
        'all_original_node_ids_retained': True, 'all_original_edges_identical': True,
        'all_non_w_nodes_unchanged': True, 'book': {'status': 'unchanged'},
        'opening_preset': {'collection': 'W', 'source_ids': before_w + added_nodes, 'original_w_ids': before_w},
        'review_digest': digest, 'coverage': copy.deepcopy(review['coverage'])}
    return D, audit


def release_paths(review):
    suffix = 'v' + review['release'].replace('.', '_') + '_' + review['date'].replace('-', '')
    return {'release_notes': 'UPDATE_' + suffix + '.html',
            'research_audit': 'data/updates/polimi_review_' + suffix + '.json'}


def render_polimi_atlas(template, payload, review):
    """Refresh current W view wording while retaining the historical attribution."""
    from atlas_graph import PAYLOAD_RE, render_current_atlas
    text = render_current_atlas(template, payload, review['release'], review['date'])
    match = PAYLOAD_RE.search(text)
    embedded = match.group(0)
    text = text[:match.start()] + '<!--POLIMI_PAYLOAD-->' + text[match.end():]
    count = sum(n.get('collection') == 'W' for n in payload['nodes'])
    last_id = max((n['id'] for n in payload['nodes'] if n.get('collection') == 'W'), key=lambda x: int(x[1:]))
    text = text.replace('Original document collection', 'Updated research collection')
    text = re.sub(r'Reset to the original \d+ documents', f'Reset to the {count} research documents', text)
    text = re.sub(r'Reset to Polimi \d+', f'Reset to Polimi {count}', text)
    text = re.sub(r'(<b id="visibleDocs">)\d+(</b>)', lambda m: m.group(1) + str(count) + m.group(2), text)
    text = re.sub(r"Original Polimi view restored: W001–W\d+\.", f'Updated Polimi view restored: W001–{last_id}.', text)
    text = text.replace('the original <strong>193 Polimi W-series documents</strong>', f'the current <strong>{count} Polimi W-series documents</strong>')
    text = text.replace('the original 193-document view each time', f'the current {count}-document W-collection view each time')
    text = text.replace('193 works · 8 October 2026 snapshot</span>', f'193 original works · {count} in the updated collection</span>')
    text = text.replace('Starts with Polimi sources only.', f'Updated to {count} research records; starts with Polimi sources only.')
    text = text.replace('The original opening view is preserved.', 'The W-only opening controls are preserved and include the reviewed additions.')
    return text.replace('<!--POLIMI_PAYLOAD-->', embedded, 1)


def build_polimi_to(root, destination, state, review, book=None):
    from atlas_cli import VERSION, install_tools, load, run_builder, save, sha
    from atlas_graph import export_raw, payload_sha256, write_graphml
    validate_review(review, state)
    original_book = load(root / 'baseline/source/ndse2_book.json')
    if book is not None and book != original_book:
        raise ValueError('A W update cannot replace the published book metadata')
    baseline = load(root / 'baseline_payload.json')
    D, audit = migrate_payload(baseline, review)
    shutil.copytree(root / 'baseline', destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git'))
    install_tools(destination)
    config = load(destination / 'source/site_config.json')
    old_source = root / 'baseline/source' / config['atlas_source']
    config.update(site_version=state['release'], graph_version=state['release'], build_date=state['date'],
        graph_snapshot=state['date'], atlas_source='atlas_current.html', graph_json='data/graph/knowledge_graph_current.json',
        graph_graphml='data/graph/knowledge_graph_current.graphml', payload_json='data/graph/atlas_payload_current.json',
        polimi_update=copy.deepcopy(D['meta']['polimi_update']), **release_paths(review))
    for collection in config['collections']:
        if collection['code'] == 'W':
            collection['description'] = (f"{audit['source_counts']['W']} research records discovered through Software Engineering @ PoliMi: the original 193-work snapshot plus {len(audit['source_additions'])} reviewed additions in this release. "
                'Original research authors, publication status, inspection scope and evidence limitations remain explicit. Summaries are independent atlas annotations.')
    save(destination / 'source/site_config.json', config)
    D['meta']['graphFile'] = Path(config['graph_graphml']).name
    write_graphml(export_raw(D), destination / config['graph_graphml'])
    D['meta']['graphSha256'] = sha(destination / config['graph_graphml'])
    audit['result_payload_sha256'] = payload_sha256(D)
    save(destination / config['graph_json'], export_raw(D))
    save(destination / config['payload_json'], D)
    current = render_polimi_atlas(old_source.read_text(encoding='utf-8'), D, review)
    (destination / 'source' / config['atlas_source']).write_text(current, encoding='utf-8')
    save(destination / config['research_audit'], {'as_of': review['date'], 'review': review, 'graph_update': audit})
    save(destination / 'source/polimi_review.json', review)
    save(destination / 'source/automation_release.json', {'tool_version': VERSION, 'date': state['date'], 'release': state['release'],
        'baseline_name': state['baseline_name'], 'baseline_sha256': state['baseline_sha256'], 'update_kind': KIND,
        'source_additions': audit['source_additions'], 'changed_source_ids': audit['changed_source_ids']})
    (destination / '.nojekyll').touch()
    render_release_notes(destination, state, review, audit)
    run_builder(destination)
    return audit


def render_release_notes(site, state, review, audit):
    esc = lambda value: html.escape(str(value), quote=True)
    additions = ''.join(f'<li><a href="catalogues/polimi.html#{esc(n["id"])}">{esc(n["id"])} · {esc(n["label"])}</a></li>' for n in review.get('additions', []))
    revisions = ''.join(f'<li><a href="catalogues/polimi.html#{esc(n["id"])}">{esc(n["id"])}</a>: {esc(n["reason"])}</li>' for n in review.get('revisions', []))
    limits = ''.join('<li>' + esc(x) + '</li>' for x in review['coverage'].get('limitations', []))
    notes = ''.join('<li>' + esc(x) + '</li>' for x in review.get('notes', []))
    intro = review.get('release_intro') or 'This release integrates the reviewed SEPolimi additions, publication-status updates and corrections into the existing research atlas.'
    body = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Knowledge Atlas v{esc(state['release'])} · SEPolimi update</title><link rel="stylesheet" href="assets/site.css"></head><body><main class="wrap" id="main">
<p class="eyebrow">Version {esc(state['release'])} · {esc(state['date'])}</p><h1>SEPolimi research update</h1><p class="intro">{esc(intro)}</p>
<p>The W catalogue now contains <strong>{audit['source_counts']['W']} records</strong>. This release adds {len(audit['source_additions'])} and revises {len(audit['changed_source_ids'])} existing records. The full graph contains {audit['nodes']:,} nodes and {audit['edges']:,} keyed relationships.</p>
<h2>New research records</h2><ul>{additions or '<li>No additions.</li>'}</ul><h2>Revised records</h2><ul>{revisions or '<li>No revisions.</li>'}</ul>
<h2>Evidence and scope</h2><p>Publication status and access depth are separate fields. Each record identifies the source actually inspected. Bibliography-only or metadata-only checks do not constitute a full manuscript review or a replication. New topic and chapter links are editorial reading mappings, not citations added to the published book.</p><ul>{limits}{notes}</ul>
<h2>Preservation and reproducibility</h2><p>All previous node IDs retain their positions, and every historical keyed relationship remains unchanged. The published book, other source collections and practice descriptors retain their existing data. The migration uses the explicitly named <code>{KIND}</code> adapter; routine O/P/F updates keep their original scope.</p>
<p>Frozen baseline: <code>{esc(state['baseline_name'])}</code><br>SHA-256: <code style="overflow-wrap:anywhere">{state['baseline_sha256']}</code></p>
<p><a href="{release_paths(review)['research_audit']}">Complete source and change audit</a> · <a href="verification/report.html">Verification report</a> · <a href="catalogues/polimi.html">Updated research catalogue</a> · <a href="swe_knowledge_graph.html">Interactive atlas</a> · <a href="index.html">Home</a></p>
</main></body></html>'''
    (site / release_paths(review)['release_notes']).write_text(body, encoding='utf-8')
