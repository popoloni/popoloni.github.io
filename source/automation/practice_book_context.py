#!/usr/bin/env python3
"""Reconcile reviewed Practices reading routes with a later supplied NDSE2.

Call ``reconcile_practice_book_context(payload, book, review)`` after the graph's
book reconciliation and before exporting it. Only existing PAT nodes can change;
the function never adds nodes, changes IDs, edits edges, or grants literal cites.
It commits changes only after all input and practice checks succeed.

An unchanged chapter ID, path, SHA-256 and title permits a source-version carry
forward, recorded as byte continuity rather than a new editorial effectiveness
judgment. A changed/disappeared context requires this explicit reviewed input::

    "practice_context_review": {
      "status": "complete", "reviewer": "Named reviewer",
      "scope": "Which changed context and operational guidance were checked",
      "source_version": "the-new-book-version",
      "records": [{
        "id": "PAT:043", "action": "retain", "chapter_ids": ["NDSE2:C04", "NDSE2:C13"],
        "editorial_note": "Updated English note describing the reviewed basis."
      }]
    }

Records must cover every affected practice. Additional records may deliberately
remap or revise otherwise unchanged practice context. ``action: revise`` also
requires ``content`` with id, summary, limitation, required_revision and the full
English ``practice`` content object. The context record's editorial_note is the
authoritative updated note; generated provenance is never taken from content.
"""
from __future__ import annotations

import copy
import hashlib
import json

SOURCE_TYPE = 'published_book_thematic_context'
SCHEMA = 'atlas_practice_book_context/1'
CONTENT_FIELDS = (
    'schema_version', 'language', 'purpose', 'when_to_use', 'when_not_to_use',
    'prerequisites', 'steps', 'example', 'verification', 'outputs', 'risks',
    'related_practices', 'editorial_note',
)
GENERATED_FIELDS = {'source_basis', 'chapter_references', 'book_context_review'}


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _chapters(book, nodes):
    version = book.get('meta', {}).get('source_version')
    if not _nonempty(version):
        raise ValueError('Practice context requires book.meta.source_version')
    other_version = book.get('book', {}).get('source_version')
    if other_version is not None and other_version != version:
        raise ValueError('Book source_version disagrees between meta and book records')
    chapters = book.get('chapters')
    if not isinstance(chapters, list) or not chapters:
        raise ValueError('Practice context requires current reviewed book chapters')
    result = {}
    for chapter in chapters:
        if not isinstance(chapter, dict) or any(not _nonempty(chapter.get(k)) for k in ('id', 'title', 'root_file', 'root_sha256', 'hub_id')):
            raise ValueError('Each current context chapter needs id, title, root_file, root_sha256 and hub_id')
        cid = chapter['id']
        if cid in result:
            raise ValueError('Duplicate current context chapter: ' + cid)
        if cid not in nodes or nodes[cid].get('collection') != 'N':
            raise ValueError('Current context chapter is absent from the reconciled N collection: ' + cid)
        if chapter['hub_id'] not in nodes:
            raise ValueError('Current context chapter hub is absent from the reconciled graph: ' + chapter['hub_id'])
        result[cid] = chapter
    return version, result


def _previous(node):
    p = node.get('attributes', {}).get('practice', {})
    refs = p.get('chapter_references', [])
    sources = p.get('source_basis', [])
    if not isinstance(refs, list) or not isinstance(sources, list):
        return [], {}, ['Previous practice context is malformed']
    by_source, errors = {}, []
    for item in sources:
        if not isinstance(item, dict):
            errors.append('Previous source-basis entry is malformed')
            continue
        if item.get('type') != SOURCE_TYPE:
            continue
        cid = item.get('chapter_id')
        if not _nonempty(cid) or cid in by_source:
            errors.append('Previous context has a missing or duplicate source chapter')
        else:
            by_source[cid] = item
    ids = [r.get('id') if isinstance(r, dict) else None for r in refs]
    if not ids or any(not _nonempty(i) for i in ids) or len(ids) != len(set(ids)):
        errors.append('Previous context has missing or duplicate chapter references')
    if set(ids) != set(by_source):
        errors.append('Previous chapter references and source-basis entries disagree')
    return refs, by_source, errors


def _context_changes(node, chapters):
    refs, old_sources, reasons = _previous(node)
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        cid = ref.get('id')
        old = old_sources.get(cid, {})
        current = chapters.get(cid)
        if current is None:
            reasons.append('Context chapter disappeared or changed identity: ' + str(cid))
            continue
        for field, previous, wanted in (
            ('file', old.get('file'), current['root_file']),
            ('sha256', old.get('sha256'), current['root_sha256']),
            ('title', ref.get('title'), current['title']),
        ):
            if previous != wanted:
                reasons.append(str(cid) + ': changed ' + field)
        prior_hub = old.get('chapter_hub') or ref.get('chapter_hub')
        if prior_hub is not None and prior_hub != current['hub_id']:
            reasons.append(str(cid) + ': changed chapter mapping')
    return refs, old_sources, reasons


def _review_records(review, version, practice_ids, affected):
    section = review.get('practice_context_review')
    if section is None:
        if affected:
            names = ', '.join(sorted(affected))
            raise ValueError(
                'NDSE2 context changed for practices: ' + names + '. Add review.practice_context_review '
                'with status="complete", reviewer, scope, source_version="' + version + '", and records '
                'covering every listed ID. Each record needs action="retain" or "revise", current '
                'chapter_ids and an updated English editorial_note; revise also needs the full content card. '
                'The old source basis is preserved; no stale context has been applied.'
            )
        return {}, None
    if not isinstance(section, dict) or section.get('status') != 'complete' or any(not _nonempty(section.get(k)) for k in ('reviewer', 'scope')):
        raise ValueError('practice_context_review must have complete status and a named reviewer and scope')
    if section.get('source_version') != version:
        raise ValueError('practice_context_review.source_version must match the new supplied book: ' + version)
    entries = section.get('records')
    if not isinstance(entries, list):
        raise ValueError('practice_context_review.records must be a list')
    result = {}
    for record in entries:
        if not isinstance(record, dict) or record.get('id') not in practice_ids:
            raise ValueError('Context review references an unknown current practice')
        nid = record['id']
        if nid in result:
            raise ValueError('Duplicate practice context review: ' + nid)
        if record.get('action') not in {'retain', 'revise'}:
            raise ValueError('Context review action must be retain or revise: ' + nid)
        ids = record.get('chapter_ids')
        if not isinstance(ids, list) or not ids or any(not _nonempty(cid) for cid in ids) or len(ids) != len(set(ids)):
            raise ValueError('Context review needs distinct current chapter_ids: ' + nid)
        if not _nonempty(record.get('editorial_note')):
            raise ValueError('Context review needs an updated English editorial_note: ' + nid)
        if record['action'] == 'retain' and 'content' in record:
            raise ValueError('A retain action cannot silently contain revised practice content: ' + nid)
        if record['action'] == 'revise':
            content = record.get('content')
            required = {'id', 'summary', 'limitation', 'required_revision', 'practice'}
            if not isinstance(content, dict) or set(content) != required or content.get('id') != nid:
                raise ValueError('A revise action needs the full content card for its unchanged ID: ' + nid)
            if any(not _nonempty(content.get(k)) for k in ('summary', 'limitation', 'required_revision')):
                raise ValueError('Revised practice summary, limitation and required_revision must be nonempty: ' + nid)
            practice = content.get('practice')
            if not isinstance(practice, dict) or not set(CONTENT_FIELDS).issubset(practice) or set(practice) - set(CONTENT_FIELDS) - GENERATED_FIELDS:
                raise ValueError('Revised practice must contain the full English content schema: ' + nid)
            if practice.get('schema_version') != 1 or practice.get('language') != 'en':
                raise ValueError('Revised practice requires schema_version=1 and language=en: ' + nid)
            # Exported generated fields are allowed for convenience, but never trusted.
        result[nid] = record
    missing = set(affected) - set(result)
    if missing:
        raise ValueError('practice_context_review lacks affected IDs: ' + ', '.join(sorted(missing)))
    return result, section


def reconcile_practice_book_context(payload, book, review):
    """Return a JSON audit; transactionally update only existing PAT records.

    ``payload`` must already contain the current book's N nodes and chapter hubs.
    ``book`` is the validated final extraction, including its source hashes.
    ``review`` is the normal frozen update review, optionally containing the
    explicit practice_context_review described in the module documentation.

    Any failure leaves ``payload`` untouched. The caller should include the
    returned audit in its update report and recompute the result payload digest
    after this function, as with other authorized content changes.
    """
    from practices_checks import validate_practices

    if not isinstance(payload, dict) or not isinstance(review, dict):
        raise ValueError('Practice context reconciliation requires a payload and review object')
    nodes = {n['id']: n for n in payload['nodes']}
    practices = [n for n in payload['nodes'] if n.get('collection') == 'PAT']
    if not practices:
        declared = payload.get('meta', {}).get('practices')
        content_present = any(n.get('kind') == 'practice_descriptor' and n.get('attributes', {}).get('practice') for n in payload['nodes'])
        if declared or content_present:
            raise ValueError('PAT collection disappeared before practice context reconciliation')
        return {'schema': SCHEMA, 'status': 'not_applicable', 'updated_ids': [], 'affected_ids': []}
    version, chapters = _chapters(book, nodes)
    changed = {n['id']: _context_changes(n, chapters) for n in practices}
    affected = {nid: info[2] for nid, info in changed.items() if info[2]}
    records, section = _review_records(review, version, {n['id'] for n in practices}, affected)
    for nid, record in records.items():
        invalid = set(record['chapter_ids']) - set(chapters)
        if invalid:
            raise ValueError('Context review for ' + nid + ' references absent current N chapters: ' + ', '.join(sorted(invalid)))
    work = copy.deepcopy(payload)
    proposed = {n['id']: n for n in work['nodes']}
    carried, retained, revised, updates = [], [], [], []
    for node in practices:
        nid = node['id']
        target = proposed[nid]
        a = target['attributes']
        p = a['practice']
        old_practice = node['attributes']['practice']
        old_refs, old_sources, reasons = changed[nid]
        record = records.get(nid)
        ids = record['chapter_ids'] if record else [ref['id'] for ref in old_refs]
        old_refs_by_id = {ref['id']: ref for ref in old_refs if isinstance(ref, dict) and ref.get('id')}
        source_versions = sorted({str(s.get('source_version', '')) for s in old_sources.values()})
        source_current = all(old_sources[cid].get('source_version') == version for cid in ids if cid in old_sources)
        if not record and not reasons and source_current:
            # No editorial or source-version event; preserve existing bytes exactly.
            continue
        if record and record['action'] == 'revise':
            content = record['content']
            for key in ('summary', 'limitation'):
                target[key] = content[key]
            a['required_revision'] = content['required_revision']
            a['limitation'] = content['limitation']
            a['practice'] = p = {key: copy.deepcopy(content['practice'][key]) for key in CONTENT_FIELDS}
            if _nonempty(review.get('release')):
                a['content_version'] = review['release']
            if _nonempty(review.get('date')):
                a['content_reviewed_on'] = review['date']
        if record:
            p['editorial_note'] = record['editorial_note']
        non_context = [copy.deepcopy(s) for s in old_practice.get('source_basis', [])
                       if isinstance(s, dict) and s.get('type') != SOURCE_TYPE]
        refs, basis = [], []
        for cid in ids:
            c = chapters[cid]
            old_ref = old_refs_by_id.get(cid, {})
            role = old_ref.get('role') if not record else None
            role = role or 'Reviewed thematic reading guidance'
            refs.append({'id': cid, 'title': c['title'], 'role': role, 'chapter_hub': c['hub_id']})
            basis.append({'type': SOURCE_TYPE, 'chapter_id': cid, 'chapter_hub': c['hub_id'],
                          'file': c['root_file'], 'line': c.get('title_locator', {}).get('line', 1),
                          'sha256': c['root_sha256'], 'source_version': version,
                          'scope': role + '; a reading suggestion, not a literal citation of this named practice.'})
        p['chapter_references'] = refs
        p['source_basis'] = non_context + basis
        status = 'editorially_reviewed' if record else 'carried_forward_same_source_bytes'
        decision = {'schema': SCHEMA, 'status': status, 'source_version': version,
                    'previous_source_versions': source_versions,
                    'identity_fields': ['chapter_id', 'file', 'sha256', 'title'],
                    'review_date': review.get('date'), 'release': review.get('release')}
        if record:
            decision.update(reviewer=section['reviewer'], scope=section['scope'], action=record['action'])
        else:
            decision['basis'] = 'Referenced chapter IDs, paths, hashes and titles are identical. This carries forward source-byte provenance, not a new empirical validation or approval claim.'
        p['book_context_review'] = decision
        target['actual'] = []
        target['printed'] = False
        target['mapped'] = sorted({chapters[cid]['hub_id'] for cid in ids})
        a['language'] = 'en'
        # Historical occurrence IDs, aliases, descriptor source and all other
        # provenance attributes remain inherited from the existing practice.
        a['historical_practice_mapped_chapters'] = sorted(set(a.get('historical_practice_mapped_chapters', [])) | set(node.get('mapped', [])))
        history = {
            'schema': SCHEMA, 'transition': status, 'to_source_version': version,
            'previous_source_versions': source_versions,
            'date': review.get('date'), 'release': review.get('release'),
            'previous_source_basis': copy.deepcopy(old_practice.get('source_basis', [])),
            'previous_chapter_references': copy.deepcopy(old_practice.get('chapter_references', [])),
            'previous_mapped': copy.deepcopy(node.get('mapped', [])),
            'previous_editorial_note': old_practice.get('editorial_note'),
            'previous_content_sha256': _digest(old_practice),
            'changed_context': reasons,
        }
        if record:
            history.update(reviewer=section['reviewer'], scope=section['scope'], action=record['action'])
        a.setdefault('practice_book_context_history', []).append(history)
        updates.append(nid)
        if record:
            (revised if record['action'] == 'revise' else retained).append(nid)
        else:
            carried.append(nid)
    report = validate_practices(work, baseline=payload, book=book)
    if report.get('failed') or not report.get('applicable'):
        failures = [r for r in report.get('checks', []) if not r.get('passed')]
        raise ValueError('Reconciled practice content is incomplete or inconsistent: ' + json.dumps(failures, ensure_ascii=False))
    if [n['id'] for n in work['nodes']] != [n['id'] for n in payload['nodes']] or work['edges'] != payload['edges']:
        raise ValueError('Practice context reconciliation changed graph identities or edges')
    if any(before != after for before, after in zip(payload['nodes'], work['nodes']) if before.get('collection') != 'PAT'):
        raise ValueError('Practice context reconciliation changed a non-practice record')
    # Apply only after the complete set has passed. No partially reviewed state
    # escapes when a later card, source locator or schema check fails.
    for index, node in enumerate(payload['nodes']):
        if node['id'] in updates:
            payload['nodes'][index] = work['nodes'][index]
    return {
        'schema': SCHEMA, 'status': 'reconciled' if updates else 'unchanged',
        'source_version': version, 'book_metadata_sha256': _digest(book),
        'updated_ids': updates, 'affected_ids': sorted(affected),
        'affected_reasons': affected, 'same_source_bytes_ids': carried,
        'reviewed_retained_ids': retained, 'reviewed_revised_ids': revised,
        'editorial_review': ({k: section[k] for k in ('status', 'reviewer', 'scope', 'source_version')} if section else None),
        'validation': {'passed': report['passed'], 'failed': report['failed'], 'summary': report['summary']},
        'all_node_ids_preserved': True, 'all_edges_preserved': True,
        'all_nonpractice_nodes_unchanged': True,
        'scope': 'Current thematic reading context and reviewed operational guidance only; historical source trails remain retained and no literal book citations are created.'
    }
