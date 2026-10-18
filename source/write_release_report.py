#!/usr/bin/env python3
"""Render release notes and current verification; never execute or invent tests."""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
DATE = "2026-10-18"
E = lambda value: html.escape(str(value), quote=True)


def read(relative, default=None):
    path = ROOT / relative
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def sha(relative):
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def write_json(relative, value):
    (ROOT / relative).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def link(target, label, css=""):
    return '<a href="' + E(target) + '"' + (' class="' + E(css) + '"' if css else '') + '>' + E(label) + '</a>'


def table(headings, rows):
    return '<div class="release-table"><table><thead><tr>' + ''.join('<th scope="col">' + E(x) + '</th>' for x in headings) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + x + '</td>' for x in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def page(relative, title, description, body, config):
    prefix = '../' if relative.startswith('verification/') else ''
    nav = ''.join(link(prefix + path, label) for path, label in [('swe_knowledge_graph.html', 'Atlas'), ('catalogues/index.html', 'Catalogues'), ('catalogues/ndse2.html', 'NDSE2'), ('about.html', 'About'), ('downloads.html', 'Downloads')])
    text = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="author" content="Enrico Papalini"><meta name="description" content="{E(description)}"><title>{E(title)} · Knowledge Atlas v{E(config['site_version'])}</title><link rel="stylesheet" href="{prefix}assets/site.css"><style>.release-table{{max-width:100%;overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:.93rem}}th,td{{padding:14px 12px;text-align:left;vertical-align:top;border-bottom:1px solid #dce3e9}}td{{overflow-wrap:anywhere}}.release-hash{{overflow-wrap:anywhere;word-break:break-all}}.release-status{{font-weight:700}}.release-list li{{margin-bottom:12px}}</style></head>
<body><a class="skip" href="#main">Skip to content</a><header class="site-head"><div class="nav"><a class="brand" href="{prefix}index.html"><span><small>AI &amp; Software Engineering</small><strong>Knowledge Atlas</strong></span></a><nav class="nav-links" aria-label="Main navigation">{nav}</nav></div></header><main id="main" class="wrap">{body}</main><footer class="site-foot"><div class="foot-inner"><p>Independent atlas by Enrico Papalini · Graph snapshot {E(config['graph_snapshot'])}</p><p>{link(prefix + 'UPDATE_20261018.html', 'Update notes')} · {link(prefix + 'verification/report.html', 'Verification')} · {link(prefix + 'attribution.html', 'Credits and boundaries')}</p></div></footer></body></html>
'''
    (ROOT / relative).write_text(text, encoding="utf-8")


def status(record, current, reason):
    if not record or not current:
        return {'status': 'pending', 'current': False, 'passed': None, 'failed': None, 'reason': reason}
    failed = record.get('failed', 0)
    complete = record.get('complete', True)
    return {'status': 'passed' if failed == 0 and complete else 'failed', 'current': True,
            'passed': record.get('passed'), 'failed': failed,
            'reason': record.get('fatalError') or ('' if complete else 'Run did not complete')}


def status_text(result):
    if result['status'] == 'pending':
        return 'Pending current verification'
    return f"{result['passed']} passed · {result['failed']} failed" if result['passed'] is not None else result['status'].title()


def main():
    config = read('source/site_config.json')
    build = read('source/build_summary.json')
    graph = read('verification/graph_update_checks.json', {})
    baseline = read('source/update_baseline_20261018.json')
    update = read('source/article_update_20261018.json')
    book = read('source/ndse2_book.json')
    structure = read('verification/structure_checks.json', {})
    browser = read('verification/browser_checks.json', {})
    repro = read('verification/reproducibility.json', {})
    graph_hash = sha('swe_knowledge_graph.html')
    counts = build['source_counts']
    slugs = {c['code']: c['slug'] for c in config['collections']}
    totals = book['audit']['totals']
    chapter_count = len(book['chapters'])
    section_count = sum(len(c['sections']) for c in book['chapters'])
    numbered = sum(bool(s.get('number')) for c in book['chapters'] for s in c['sections'])
    cited = {sid for c in book['chapters'] for sid in c['source_ids']}
    missing_baseline_paths = [p for p in baseline['files'] if not (ROOT / p).is_file()]
    article_rows, article_summary = [], []
    for node in update['nodes']:
        a = node.get('attributes', {})
        published, revised = a.get('publication_date', node.get('year', '')), a.get('updated_date')
        date = 'Published ' + published + ('; revised ' + revised if revised else '')
        target = 'catalogues/' + slugs[node['collection']] + '.html#' + quote(node['id'], safe='')
        scope = '<p class="micro">' + E(a['source_scope']) + '</p>' if a.get('source_scope') else ''
        article_rows.append([link(target, node['id'] + ' · ' + node['label']), E(node['authors']), E(date), E(node['summary']) + scope + '<p>' + link(node['url'], 'Primary publication') + '</p>'])
        article_summary.append({'id': node['id'], 'title': node['label'], 'authors': node['authors'], 'publication_date': published, 'updated_date': revised, 'url': node['url'], 'manuscript_citation': False})
    chapter_rows = [[link('catalogues/chapters/' + c['hub_id'].split(':')[-1].lower() + '.html', f"{c['number']:02d} · {c['title']}"), '<span lang="it">' + E(c['title_it']) + '</span>'] for c in book['chapters']]
    history = 'All original node IDs and keyed edges are retained.' if graph.get('all_original_node_ids_retained') and graph.get('all_original_edges_identical') else 'See the graph update audit for preservation checks.'
    baseline_name, baseline_sha = baseline['baseline_name'], baseline['baseline_sha256']
    update_body = f'''<p class="eyebrow">Website v{E(config['site_version'])} · 18 October 2026</p><h1>Published NDSE2 and the October article update</h1><p class="intro">Four additional practitioner articles and the 13 chapters of the published second edition are now part of the Knowledge Atlas. English and Italian chapter guides connect the book to its literal source citations.</p><div class="actions">{link('catalogues/ndse2.html', 'NDSE2 · published second edition', 'button primary')}{link('swe_knowledge_graph.html?collection=N', 'Explore the 13 chapters in the atlas', 'button')}{link('verification/report.html', 'Current verification report', 'button')}</div>
<section class="section"><h2>Articles added to the online companion</h2><p>The update adds {len(update['nodes'])} catalogue records. Publication dates are distinct from revision dates, and guest authors retain their own bylines. These additions are online companion reading; they are not literal citations in the supplied published NDSE2 manuscript.</p>{table(['Record', 'Actual authorship', 'Publication history', 'Contribution and primary source'], article_rows)}<p>The two Fowler-site additions extend the original <em>Exploring Generative AI</em> catalogue to explicitly identified adjacent articles. {link('catalogues/fowler.html#F033', 'F033 · Are Harnesses Worth the Cost?')} was already present and is retained without duplication. {link('catalogues/fowler.html#F026', 'F026')} now records the primary source’s pointer to the expanded harness-engineering article, while retaining its original memo URL and publication date.</p><p>{link('data/updates/source_review_20261018.json', 'Source coverage audit, exclusions and access limits')}</p></section>
<section class="section"><h2>The published second edition</h2><p><strong>{E(book['book']['title'])}</strong>, by {E(book['book']['author'])}, is the sixth published volume represented in the atlas. On 18 October 2026, the author confirmed that the book was already published. That confirmation is not an asserted first-publication date; no ISBN is inferred.</p><p>The final English and Italian source edition {E(book['book']['source_version'])} supplies {chapter_count} chapter guides and {section_count} section headings ({numbered} numbered and {section_count - numbered} unnumbered). Each language contains {totals['EN']['chapter_citation_occurrences']} literal chapter citation occurrences. Across the chapters there are {len(cited)} distinct cited sources, including {totals['EN']['chapter_resolved_auxiliary_unique_source_ids']} resolved auxiliary bibliography record. Section and manuscript file/line provenance is available from the chapter guides.</p>{table(['English chapter guide', 'Italian title'], chapter_rows)}<p>Actual chapter citations, introduction/appendix citations, identifier-index mentions, general bibliography membership and broader editorial mappings remain separate. The five earlier books retain their own volume and source records.</p><div class="actions">{link('catalogues/volumes/v06.html', 'Edition details', 'button')}{link('source/ndse2_book.json', 'Bilingual chapter metadata', 'button')}{link('data/updates/ndse2_citation_occurrences.json', 'Literal citation trace', 'button')}</div></section>
<section class="section"><h2>Current graph and stable identifiers</h2><p>The current graph contains <strong>{build['graph_nodes']:,} nodes, {build['graph_edges']:,} keyed edges and {build['graph_relation_types']} relation types</strong>. Source collections contain {E(' · '.join(code + str(counts[code]) for code in ['W', 'O', 'P', 'F', 'B', 'N']))}. {E(history)} Chapter hubs C:C01–C:C13 remain stable; the N collection adds published-chapter records NDSE2:C01–NDSE2:C13.</p><p>The original PoliMi-only starting view is retained. Current v13 JSON and GraphML exports are available from {link('downloads.html', 'Downloads')}; original v12 exports remain separately labelled historical files.</p></section>
<section class="section"><h2>Apply the full package or the delta</h2><p>The supplied complete website package used as the comparison baseline is <strong>{E(baseline_name)}</strong>.</p><p class="micro release-hash">Baseline SHA-256: <code>{E(baseline_sha)}</code></p><p>For the full package, use the complete site tree. For the delta, copy its added or changed files into the existing publishing folder, preserving each relative path and overwriting matching files. The delta is intended for this exact baseline. {'No baseline files have been removed from this update.' if not missing_baseline_paths else 'Consult the package manifest for baseline paths requiring attention.'} Retain <code>.nojekyll</code> and apply the files at the configured GitHub Pages publishing root.</p><p>{link('DEPLOYMENT.md', 'Preview and rebuild instructions')} · {link('source/update_baseline_20261018.json', 'Baseline file inventory')} · {link('verification/report.html', 'Verification results and scope')}</p></section>'''
    page('UPDATE_20261018.html', 'October 2026 update', 'Article additions, published NDSE2 chapter guides and exact baseline information.', update_body, config)

    graph_tests = [
        ('Current graph counts match static build', graph.get('as_of') == DATE and all(graph.get(a) == build.get(b) for a, b in [('nodes', 'graph_nodes'), ('edges', 'graph_edges'), ('relation_types', 'graph_relation_types')])),
        ('All original node IDs retained', graph.get('all_original_node_ids_retained') is True),
        ('All original keyed edges identical', graph.get('all_original_edges_identical') is True),
        ('No unresolved literal citations', graph.get('unresolved_citations') == []),
        ('English and Italian chapter source sets align', book['audit'].get('all_chapter_source_sets_match') is True),
        ('English and Italian chapter occurrence counts align', book['audit'].get('all_chapter_occurrence_counts_match') is True),
    ]
    graph_result = status({'passed': sum(v for _, v in graph_tests), 'failed': sum(not v for _, v in graph_tests)}, graph.get('as_of') == DATE, 'Current graph update audit is unavailable.')
    structural_date = structure.get('as_of', structure.get('graph_snapshot'))
    structural_version = str(structure.get('site_version', ''))
    structural_hash = structure.get('graph_html_sha256', structure.get('graphHTMLSHA256'))
    structural_current = bool((structural_date == DATE or structural_version == config['site_version']) and structural_hash == graph_hash)
    structure_result = status(structure, structural_current, 'The structural record is inherited or does not identify this current graph.')
    browser_current = bool(browser.get('graphHTMLSHA256') == graph_hash and browser.get('graphNodes') == build['graph_nodes'] and browser.get('graphEdges') == build['graph_edges'] and browser.get('graphRelations') == build['graph_relation_types'] and browser.get('navigation') == 'real local HTTP navigation and real DOM controls')
    browser_result = status(browser, browser_current, 'The browser record is inherited or does not match the current interactive HTML.')
    repro_current = bool(repro.get('as_of') == DATE and repro.get('graph_html_sha256') == graph_hash and repro.get('site_version') == config['site_version'] and repro.get('method_id') == 'isolated_graph_and_site_two_builds_v13')
    repro_result = status(repro, repro_current, 'The reproducibility record predates the current graph-and-site rebuild method.')
    results = {'graph': graph_result, 'structure': structure_result, 'browser': browser_result, 'reproducibility': repro_result}
    release_status = 'failed' if any(r['status'] == 'failed' for r in results.values()) else ('pending' if any(r['status'] == 'pending' for r in results.values()) else 'passed')
    switches = next((c for c in browser.get('checks', []) if c.get('check') == 'Every relationship switch exposes exact keyed edges and fully disables them' and c.get('passed')), None) if browser_current else None
    switch_count = (switches.get('detail') or {}).get('tested', 0) if switches else 0
    widths = sorted({int(m.group(1)) for c in browser.get('checks', []) if c.get('passed') and (m := re.match(r'(\d+)px responsive layout:', c.get('check', '')))}) if browser_current else []
    default_checked = browser_current and any(c.get('passed') and c.get('check') == 'Bare atlas preserves exact original edge IDs' for c in browser.get('checks', []))
    structure_scope = f"{structure.get('internal_links_checked', 0):,} local file, asset and fragment references across {structure.get('html_pages_checked', 0)} HTML pages." if structural_current else structure_result['reason']
    browser_scope = f"Real local HTTP navigation in Chrome/Chromium {browser.get('browser')}; {switch_count} relation switches individually checked against exact keyed edges." if browser_current else browser_result['reason']
    repro_scope = f"{repro.get('outputs_tested', 0)} generated outputs compared with delivered files and two isolated graph-then-site builds." if repro_current else repro_result['reason']
    rows = [
        ['Graph and bilingual sources', E(status_text(graph_result)), E(f"{build['graph_nodes']:,} nodes · {build['graph_edges']:,} keyed edges · {build['graph_relation_types']} relation types. Original IDs and keyed edges retained; current metadata changes audited.")],
        ['Static structure', E(status_text(structure_result)), E(structure_scope)],
        ['Browser and navigation', E(status_text(browser_result)), E(browser_scope)],
        ['Reproducibility', E(status_text(repro_result)), E(repro_scope)],
    ]
    records = [('../source/build_summary.json', 'Current build counts'), ('graph_update_checks.json', 'Graph update and citation reconciliation'), ('structure_checks.json', 'Static links, fragments, records and exports'), ('browser_checks.json', 'Browser checks; inherited records are not accepted as current'), ('relationship_switch_checks.json', 'Per-relation switch records; compare the count and browser attestation'), ('reproducibility.json', 'Graph and static-page byte comparison'), ('TEST_METHOD.md', 'Validation method and boundaries'), ('../data/updates/source_review_20261018.json', 'Primary-source coverage and access audit'), ('../source/ndse2_book.json', 'Bilingual chapter structure and citations'), ('../source/update_baseline_20261018.json', 'Exact baseline inventory'), ('../SHA256SUMS.txt', 'Package file checksums')]
    historical = [('visual_checks.json', 'Historical v12.1 responsive and portrait checks'), ('home_desktop.png', 'Historical v12.1 desktop landing page'), ('home_tablet.png', 'Historical v12.1 tablet-sized landing page'), ('atlas_mobile.png', 'Historical v12.1 mobile-sized atlas'), ('catalogue_mobile.png', 'Historical v12.1 mobile-sized Fowler catalogue')]
    note = '<p class="caution">Some current verification records are pending. Historical v12.1 successes are not counted as verification of this release.</p>' if release_status == 'pending' else ('<p class="caution">A current record contains a failure or incomplete run. Consult that record before publishing.</p>' if release_status == 'failed' else '<p class="note">All current verification groups recorded below passed.</p>')
    report_body = f'''<p class="eyebrow">Website v{E(config['site_version'])} · 18 October 2026</p><h1>Current release verification</h1><p class="intro">This report covers the October article update, the published NDSE2 chapter layer and their static website. Results come from recorded checks; the report generator does not execute tests.</p><p class="release-status">Verification status: {E(release_status.upper())}</p>{note}<div class="actions">{link('../UPDATE_20261018.html', 'What changed', 'button primary')}{link('../catalogues/ndse2.html', 'Published chapter guides', 'button')}{link('../downloads.html', 'Downloads', 'button')}</div>
<section class="section"><h2>Current checks</h2>{table(['Area', 'Recorded result', 'Scope'], rows)}<p>The site contains {build['static_source_records']} source/chapter records across {len(counts)} source collections, {build['practice_descriptors']} practice descriptors, {build['practice_occurrences']} historical occurrences and {build['published_books']} published volumes. The static builder generated {build['html_pages_built']} pages; the update page and this report are supplemental pages.</p><p>{'The exact original W193 / 0 context / 64-edge starting view passed current browser checks.' if default_checked else 'The exact original W193 / 0 context / 64-edge starting view awaits a matching current browser result.'} {'Current responsive checks cover ' + E(', '.join(str(w) + 'px' for w in widths)) + ' CSS viewports.' if widths else 'Current responsive results are pending with browser verification.'}</p></section>
<section class="section"><h2>Book citation reconciliation</h2><p>The final EN/ITA edition {E(book['book']['source_version'])} has {chapter_count} chapter records and {section_count} section headings per language. There are {totals['EN']['chapter_citation_occurrences']} literal chapter citation occurrences per language and {len(cited)} distinct cited chapter sources, including {totals['EN']['chapter_resolved_auxiliary_unique_source_ids']} auxiliary bibliography record. These form {graph.get('literal_chapter_source_pairs', 0)} distinct chapter–source pairs.</p><p>The introduction and appendices add {totals['EN']['nonchapter_body_citation_occurrences']} literal body citations per language. The occurrence trace therefore contains {graph.get('literal_occurrences', 0)} English-plus-Italian occurrences across those scopes. Identifier-index mentions and blanket bibliography inclusion are excluded from chapter citation counts. A citation establishes use by the book; it does not establish independent replication of a source’s empirical claims.</p></section>
<section class="section"><h2>Method and limits</h2><p>Current browser tests use a local HTTP server and real DOM controls in Chrome/Chromium. They check local navigation, collection filters, deep links, source inspection, exports, responsive layouts and current relation switches. Browser records are accepted as current only when graph counts and the interactive-HTML hash match this release. These are local browser checks, not a GitHub deployment or native Safari/iPad tests.</p><p>The structural checker resolves local files and fragments; it does not fetch every external URL. The separate October source review inspected primary metadata and the accessible passages documented in its audit. Access qualifications and actual author/excerpt credits remain attached to each article. The four online additions are not retroactively presented as manuscript citations.</p><p>Reproducibility uses the frozen baseline, audited article metadata, final bilingual chapter metadata and supplied Python builders. It rebuilds graph data before static pages without a source refresh. Runtime test reports, release reports and package checksum manifests are excluded from the byte-comparison set, avoiding circular report hashes.</p></section>
<section class="section"><h2>Verification records</h2><ul class="release-list">{''.join('<li>' + link(p, t) + '</li>' for p, t in records)}</ul></section>
<section class="section"><h2>Historical v12.1 visual evidence</h2><p>The original packaged PNG screenshots and <code>visual_checks.json</code> are retained from the 14 October 2026 v12.1 package. They document that earlier presentation and its inlined-content browser method. They are not new screenshots or current v13 visual checks; their pass counts are excluded above.</p><ul>{''.join('<li>' + link(p, t) + '</li>' for p, t in historical)}</ul></section>'''
    page('verification/report.html', 'Release verification', 'Current v13 checks and separately identified historical v12.1 evidence.', report_body, config)
    summary = {
        'site_release': config['site_version'], 'graph_version': config['graph_version'], 'graph_snapshot': config['graph_snapshot'], 'release_date': DATE,
        'verification_status': release_status, 'baseline': {'archive_name': baseline_name, 'sha256': baseline_sha, 'missing_paths': missing_baseline_paths},
        'source_counts': counts, 'nodes': build['graph_nodes'], 'keyed_edges': build['graph_edges'], 'edge_types': build['graph_relation_types'],
        'static_html_pages_built': build['html_pages_built'], 'supplemental_release_pages': 2, 'group_pages': build['group_pages'], 'article_additions': article_summary,
        'ndse2': {'source_version': book['book']['source_version'], 'published': True, 'publication_confirmation_date': DATE, 'publication_date': book['book'].get('publication_date'), 'isbn': book['book'].get('isbn'), 'chapters': chapter_count, 'section_headings_per_language': section_count, 'numbered_section_headings': numbered, 'chapter_citation_occurrences_per_language': totals['EN']['chapter_citation_occurrences'], 'distinct_cited_chapter_sources': len(cited), 'auxiliary_chapter_sources': totals['EN']['chapter_resolved_auxiliary_unique_source_ids'], 'chapter_source_pairs': graph.get('literal_chapter_source_pairs'), 'all_scope_literal_occurrences_both_languages': graph.get('literal_occurrences')},
        'all_original_node_ids_retained': graph.get('all_original_node_ids_retained'), 'all_original_keyed_edges_identical': graph.get('all_original_edges_identical'),
        'source_graph_data_unchanged': False, 'current_graph_payload_matches_current_source': build.get('graph_payload_matches_current_source'),
        'default_view': {'sources': 193, 'context': 0, 'edges': 64, 'current_browser_verified': default_checked},
        'named_checks': results, 'graph_reconciliation_checks': [{'check': name, 'passed': passed} for name, passed in graph_tests],
        'relationship_switches_individually_checked': switch_count, 'local_html_links_and_fragments_checked': structure.get('internal_links_checked') if structural_current else None,
        'source_validation_refreshed': True, 'source_review_scope': 'Primary metadata and documented accessible passages; no empirical replication',
        'local_http_navigation_tested': browser_current and browser_result['status'] == 'passed', 'github_deployed': False, 'native_safari_tested': False,
        'responsive_viewport_widths_current': widths,
        'historical_visual_evidence': {'release': '12.1', 'date': '2026-10-14', 'files': [p for p, _ in historical], 'included_in_current_pass_counts': False},
        'report_generator_executes_tests': False,
    }
    write_json('verification/release_summary.json', summary)
    print(f"Wrote October update and current verification report: {release_status}.")


if __name__ == '__main__':
    main()
