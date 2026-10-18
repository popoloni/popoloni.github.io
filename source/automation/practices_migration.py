#!/usr/bin/env python3
"""Reviewed Practices content adapter for the normalized Atlas, schema 1.

This is an explicit collection/content migration, separate from article discovery.
The reviewed input freezes all English cards, family text and frontend changes.
It keeps all historical node IDs, keyed edges and non-practice records unchanged.
"""
from __future__ import annotations

import collections
import copy
import hashlib
import html
import json
import re
import shutil
from pathlib import Path

KIND = 'atlas_practices_update/1'
DISPOSITIONS = {
    'RICOMPORRE': 'Recompose the mechanism', 'COMPANION': 'Companion variant',
    'RINVIO_BREVE': 'Brief thematic reference', 'RIVEDERE_CRITICAMENTE': 'Apply the critical qualification',
    'PRECISARE': 'Retain with explicit qualifications', 'FUORI_CORPO': 'Outside the core execution scope',
    'CONSERVARE': 'Retain', 'AMPLIARE': 'Expand the operational treatment',
    'RICONCILIARE': 'Reconcile historical variants',
}


def release_paths(review):
    suffix = 'v' + review['release'].replace('.', '_') + '_' + review['date'].replace('-', '')
    return {'release_notes': 'UPDATE_' + suffix + '.html',
            'practice_audit': 'data/updates/practices_review_' + suffix + '.json'}


def validate_review(review, state):
    if review.get('kind') != KIND:
        raise ValueError('Unsupported practice migration schema')
    for field in ('baseline_sha256', 'baseline_payload_sha256', 'baseline_release', 'release', 'date'):
        if review.get(field) != state.get(field):
            raise ValueError('Practice review does not match the frozen run: ' + field)
    editorial = review.get('editorial_review', {})
    if editorial.get('status') != 'complete' or not editorial.get('reviewer') or not editorial.get('scope'):
        raise ValueError('A completed named editorial review of all practice cards is required')
    if any(review.get(field) for field in ('additions', 'revisions', 'edges')):
        raise ValueError('Practice migration cannot hide article, node or edge operations')
    for key in ('practices', 'families'):
        items = review.get(key)
        if not isinstance(items, list) or not items or len({n.get('id') for n in items}) != len(items):
            raise ValueError('Missing or duplicate reviewed ' + key)
    required = {'atlas_template.html', 'atlas_navigation_patch.js', 'site.css', 'catalogues.js'}
    if set(review.get('frontend', {})) != required or any(not isinstance(v, str) or not v.strip() for v in review['frontend'].values()):
        raise ValueError('Frontend migration requires exactly the four reviewed template/asset files')
    template = review['frontend']['atlas_template.html']
    if '<script id="graph-data" type="application/json">{}</script>' not in template:
        raise ValueError('The reviewed template must have an empty normalized data placeholder')
    if 'id="sourcePAT"' not in template or 'id="sourceW"' not in template:
        raise ValueError('The reviewed template lacks the PAT or W collection')
    return {'status': 'complete', 'kind': KIND, 'reviewed_practices': len(review['practices'])}


def migrate_payload(baseline, review, book):
    from atlas_graph import payload_sha256, validate_payload
    from practices_checks import validate_practices
    D = copy.deepcopy(baseline)
    by = {n['id']: n for n in D['nodes']}
    descriptors = [n for n in D['nodes'] if n['kind'] == 'practice_descriptor']
    families = [n for n in D['nodes'] if n['kind'] == 'practice_family']
    occurrences = [n for n in D['nodes'] if n['kind'] == 'practice_occurrence']
    cards = {n['id']: n for n in review['practices']}
    family_cards = {n['id']: n for n in review['families']}
    if set(cards) != {n['id'] for n in descriptors} or set(family_cards) != {n['id'] for n in families}:
        raise ValueError('This adapter requires a complete review of the existing descriptors and families')
    book_chapters = {c['number']: c for c in book['chapters']}
    adjacency = collections.defaultdict(list)
    for edge in D['edges']:
        s, t = D['nodes'][edge['source']]['id'], D['nodes'][edge['target']]['id']
        adjacency[s].append((t, edge))
        adjacency[t].append((s, edge))
    occurrence_to_practice = {}
    for n in descriptors:
        for other, edge in adjacency[n['id']]:
            if edge['relation'] == 'V10_DESCRIBES_RECONCILED_PRACTICE' and by[other]['kind'] == 'practice_occurrence':
                if other in occurrence_to_practice and occurrence_to_practice[other] != n['id']:
                    raise ValueError('Conflicting occurrence identity: ' + other)
                occurrence_to_practice[other] = n['id']
    for n in families:
        f = family_cards[n['id']]
        n.update(label=f['label'], summary=f['summary'], families=[n['id']])
        n['attributes'].update(label=f['label'], purpose=f['purpose'], language='en',
                               symptom=f['symptom'], selection_hint=f['selection_hint'], family_name=f['label'])
    for n in descriptors:
        card = cards[n['id']]
        a = n['attributes']
        family_id = 'FAMILY:' + a['family']
        if family_id not in family_cards:
            raise ValueError('Unknown practice family: ' + family_id)
        n.update(collection='PAT', summary=card['summary'], limitation=card['limitation'],
                 families=[family_id], printed=False)
        a['historical_structural_chapters'] = sorted(set(a.get('historical_structural_chapters', [])) | set(n.get('actual', [])))
        # These memberships describe a thematic reading route, not literal citations.
        n['mapped'] = sorted(set(n.get('mapped', [])) | set(n.get('actual', [])) | {'C:C13'})
        n['actual'] = []
        a.update(required_revision=card['required_revision'], limitation=card['limitation'],
                 family_name=family_cards[family_id]['label'], language='en',
                 content_version=review['release'], content_reviewed_on=review['date'])
        old_disposition = a.get('disposition', '')
        a['disposition_code'] = a.get('disposition_code', old_disposition)
        a['disposition'] = DISPOSITIONS.get(old_disposition, old_disposition)
        a['practice_scope'] = ('Conceptual entry; outside the core execution scope' if a['disposition_code'] == 'FUORI_CORPO'
                               else 'Optional companion variant' if a['disposition_code'] == 'COMPANION'
                               else 'Editorial operational guide')
        a['practice'] = copy.deepcopy(card['practice'])
        p = a['practice']
        p['source_basis'] = [{'type': 'retained_editorial_descriptor', 'id': n['id'],
                              'baseline_release': review.get('baseline_release', '13.0'),
                              'baseline_zip_sha256': review['baseline_sha256'],
                              'scope': 'Historical label, family, occurrences and critical revision; operational explanation expanded editorially.'}]
        p['chapter_references'] = []
        # A historical chapter=0 marks exclusion from core execution, not the
        # absence of useful model-limit context in its family chapter.
        primary = a.get('chapter') or int(a['family'][1:])
        numbers = [primary, 13]
        for number in dict.fromkeys(numbers):
            if number not in book_chapters:
                continue
            c = book_chapters[number]
            n['mapped'] = sorted(set(n['mapped']) | {c['hub_id']})
            role = 'Practice selection and proportionality' if number == 13 else ('Model-limit context; this training variant remains outside core execution' if not a.get('chapter') else 'Thematic chapter guidance')
            p['chapter_references'].append({'id': c['id'], 'title': c['title'], 'role': role})
            p['source_basis'].append({'type': 'published_book_thematic_context', 'chapter_id': c['id'],
                                     'file': c['root_file'], 'line': c.get('title_locator', {}).get('line', 1),
                                     'sha256': c['root_sha256'], 'source_version': book['meta']['source_version'],
                                     'scope': role + '; a reading suggestion, not a literal citation of this named practice.'})
        occ_ids = sorted(k for k, v in occurrence_to_practice.items() if v == n['id'])
        a['historical_occurrence_ids'] = occ_ids
        a['provenance'] = 'English operational guidance expanded from the retained descriptor, its historical occurrence trail and thematic chapters of the author-supplied published NDSE2. Illustrative examples are not observed outcomes.'
    for n in occurrences:
        a = n['attributes']
        if n['id'] not in occurrence_to_practice:
            raise ValueError('Historical occurrence has no current descriptor: ' + n['id'])
        current = by[occurrence_to_practice[n['id']]]
        family_id = 'FAMILY:' + a['family']
        n['families'] = [family_id]
        a.update(practice_id=current['id'], family_name=family_cards[family_id]['label'], language='en')
        n['summary'] = (f"Historical occurrence of {current['label']} in the retained {a.get('volume_id', 'earlier volume')} source. "
                        f"The original title, alias and file locator preserve its lineage. Read {current['id']} for the current English operational guidance and its qualifications.")
    for n in descriptors + families + occurrences:
        # Normalize classifications that already exist as explicit graph relations.
        for field, prefix, relations in (
            ('streams', 'T:', {'V10_THEME_CLASSIFICATION', 'V10_PRIMARY_THEME_CLASSIFICATION'}),
            ('topics', 'K:', {'V10_TOPIC_CLASSIFICATION'}),
            ('volumes', 'V', {'V10_CATALOGUED_IN_VOLUME', 'V10_OCCURRENCE_IN_VOLUME'}),
        ):
            found = {other for other, edge in adjacency[n['id']] if edge['relation'] in relations and other.startswith(prefix)}
            n[field] = sorted(set(n.get(field, [])) | found)
    context_counts = collections.Counter(n.get('category') for n in D['nodes'] if not n.get('collection'))
    D['nodeGroups'] = [{**g, 'count': context_counts[g['id']], **({'label': 'Practice families and historical occurrences'} if g['id'] == 'practices' else {})} for g in D['nodeGroups']]
    meta = D['meta']
    meta.update(edition='v' + review['release'], date=review['date'], nodeCount=len(D['nodes']), edgeCount=len(D['edges']), relationCount=len(D['relations']))
    meta['practices'] = {'collection': 'PAT', 'language': 'en', 'descriptors': len(descriptors), 'families': len(families),
                         'historical_occurrences': len(occurrences), 'content_schema': 1,
                         'scope': 'Editorial operational guidance with illustrative examples; not independent empirical studies.'}
    g = meta['graphAttributes']
    g.update(portable_atlas_release='v' + review['release'] + '-static-' + review['date'].replace('-', ''),
             portable_atlas_basis='Exact supplied published website baseline; all practice descriptors enriched in English and assigned to PAT. Historical IDs, keyed edges, article records and published book citations retained.',
             atlas_update='v' + review['release'] + '_' + review['date'].replace('-', ''),
             practice_collection='PAT', practice_descriptor_count=len(descriptors), practice_language='en',
             practice_content_schema=1, practices_editorial_review=release_paths(review)['practice_audit'])
    validate_payload(D)
    practice_report = validate_practices(D, baseline, book)
    if practice_report['failed']:
        raise ValueError('Practice content validation failed: ' + json.dumps([x for x in practice_report['checks'] if not x['passed']], ensure_ascii=False))
    kinds = {'practice_descriptor', 'practice_family', 'practice_occurrence'}
    if any(n != old for n, old in zip(D['nodes'], baseline['nodes']) if n['kind'] not in kinds):
        raise ValueError('Unexpected change outside the authorized practice layer')
    if D['edges'] != baseline['edges']:
        raise ValueError('Practice migration changed historical keyed edges')
    audit = {'kind': KIND, 'date': review['date'], 'release': review['release'],
             'baseline_sha256': review['baseline_sha256'], 'baseline_payload_sha256': payload_sha256(baseline),
             'result_payload_sha256': payload_sha256(D), 'source_additions': [], 'changed_source_ids': [],
             'practice_ids': [n['id'] for n in descriptors], 'no_changes': False,
             'book_source_version': book['meta']['source_version'],
             'all_nonpractice_nodes_unchanged': True, 'all_keyed_edges_unchanged': True,
             'counts': practice_report['summary'], 'editorial_review': review['editorial_review'],
             'historical_revisions': [{'id': n['id'], 'disposition': n['attributes'].get('disposition'),
                                       'required_revision': n['attributes'].get('required_revision')} for n in baseline['nodes'] if n['kind'] == 'practice_descriptor']}
    return D, audit, practice_report


def build_practices_to(root, destination, state, review, book=None):
    from atlas_cli import TOOLS, install_tools, load, run_builder, save, sha
    from atlas_graph import PAYLOAD_RE, export_raw, payload_sha256, render_current_atlas, write_graphml
    validate_review(review, state)
    baseline = load(root / 'baseline_payload.json')
    baseline_book = load(root / 'baseline/source/ndse2_book.json')
    if book is not None and book != baseline_book:
        raise ValueError('This migration keeps the published book unchanged; update its source edition separately')
    D, audit, practice_report = migrate_payload(baseline, review, baseline_book)
    shutil.copytree(root / 'baseline', destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git'))
    install_tools(destination)
    config = load(destination / 'source/site_config.json')
    config.update(site_version=state['release'], graph_version=state['release'], build_date=state['date'],
                  graph_snapshot=state['date'], payload_json='data/graph/atlas_payload_v13.json',
                  release_notes=release_paths(review)['release_notes'], practice_content_schema=1)
    pat_config = {'code': 'PAT', 'slug': 'practices', 'title': 'Software Engineering Practices', 'short': 'Practices',
                  'description': f"{len(review['practices'])} English operational guides in {len(review['families'])} families: when to use a practice, how to apply it, illustrative examples, verification, outputs and limitations. Historical source occurrences remain traceable.",
                  'source_url': '', 'record_type': 'editorial_practice'}
    config['collections'] = [c for c in config['collections'] if c['code'] != 'PAT'] + [pat_config]
    save(destination / 'source/site_config.json', config)
    D['meta']['graphFile'] = Path(config['graph_graphml']).name
    write_graphml(export_raw(D), destination / config['graph_graphml'])
    D['meta']['graphSha256'] = sha(destination / config['graph_graphml'])
    audit['result_payload_sha256'] = payload_sha256(D)
    save(destination / config['graph_json'], export_raw(D))
    save(destination / config['payload_json'], D)
    template = review['frontend']['atlas_template.html']
    old_embed = json.dumps(baseline, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('&', '\\u0026')
    with_old = PAYLOAD_RE.sub(lambda m: m.group(1) + old_embed + m.group(3), template, count=1)
    rendered = render_current_atlas(with_old, D, state['release'], state['date'])
    (destination / 'source' / config['atlas_source']).write_text(rendered, encoding='utf-8')
    for name, target in (('atlas_navigation_patch.js', 'source/atlas_navigation_patch.js'), ('site.css', 'assets/site.css'), ('catalogues.js', 'assets/catalogues.js')):
        (destination / target).write_text(review['frontend'][name], encoding='utf-8')
    save(destination / 'source/practices_review.json', review)
    save(destination / release_paths(review)['practice_audit'], audit)
    save(destination / 'verification/practices_content.json', practice_report)
    save(destination / 'source/automation_release.json', {'tool_version': '1.1.0', 'date': state['date'], 'release': state['release'],
         'baseline_name': state['baseline_name'], 'baseline_sha256': state['baseline_sha256'], 'update_kind': KIND})
    render_release_notes(destination, state, audit)
    run_builder(destination)
    return audit


def render_release_notes(site, state, audit):
    count = audit['counts']
    text = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Atlas v{state['release']} · Practices update</title><link rel="stylesheet" href="assets/site.css"></head><body><main class="wrap" id="main">
<p class="eyebrow">Release {state['release']} · {state['date']}</p><h1>Practices that can be read and used</h1>
<p class="intro">All {count['records']} existing practice descriptors now have substantive English operational guides and belong to the PAT Practices collection.</p>
<h2>What changed</h2><ul><li>Specific summaries, purposes, use conditions, prerequisites, steps, illustrative examples, verification criteria, outputs and risks.</li><li>{count['families']} English practice families with symptoms and selection guidance, a family filter in the catalogue and family grouping in the Atlas.</li><li>Catalogue links open the Practices collection and select the requested node. The inspector shows its complete guidance and related practices.</li><li>{count['historical_occurrences']} historical occurrences retain their original IDs, aliases, source paths, line locators and recorded hashes.</li><li>JSON and CSV exports retain the structured content; automated content and browser checks protect the collection during later updates.</li></ul>
<h2>Scope and provenance</h2><p>The operational guidance is an editorial expansion of the retained descriptors and thematic chapters of the author-supplied published NDSE2, source version {html.escape(str(audit['book_source_version']))}. Examples are illustrative. Practice names and source genealogy do not establish inventorship or effectiveness.</p>
<p>The published book's literal citations remain distinct from thematic reading suggestions. All existing article and book records, graph node IDs and keyed edges are retained. The opening view remains the 193-work Polimi collection.</p>
<p>The source release is the exact v{html.escape(str(state['baseline_release']))} ZIP supplied as published. No deployment is performed by the build.</p>
<h2>Repeatable updates</h2><p>The included <code>source/automation/atlas_cli.py</code> supports both reviewed article updates and an explicit <code>atlas_practices_update/1</code> adapter. The latter freezes the complete English card review and frontend migration, rebuilds from the exact baseline, checks content, graph preservation and real browser behavior, and creates a copy-only delta after verification.</p>
<p><a href="catalogues/practices.html">Read the Practices catalogue</a> · <a href="swe_knowledge_graph.html?collection=PAT&amp;grouping=family">Explore Practices in the Atlas</a> · <a href="verification/report.html">Release verification</a> · <a href="verification/practices_content.json">Content audit</a> · <a href="{release_paths(state)['practice_audit']}">Change and provenance audit</a> · <a href="index.html">Home</a></p>
</main></body></html>'''
    (site / release_paths(state)['release_notes']).write_text(text, encoding='utf-8')
