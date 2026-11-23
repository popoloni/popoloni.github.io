#!/usr/bin/env python3
"""Validate Atlas book navigation and public HTML. Run from any directory.

python source/check_book_navigation.py --report /tmp/book-navigation.json
Use --browser /path/to/chrome-headless-shell to select a Chromium executable.
Use --static-only to run just the standard-library HTML and graph-link audit.
"""
import argparse
import collections
import functools
import http.server
import json
import shutil
import threading
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlsplit


class Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = collections.Counter()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id'):
            self.ids[attrs['id']] += 1
        if tag == 'a' and attrs.get('name') and attrs.get('name') != attrs.get('id'):
            self.ids[attrs['name']] += 1
        key = {'a': 'href', 'link': 'href', 'script': 'src', 'img': 'src', 'iframe': 'src',
               'source': 'src'}.get(tag)
        if key and attrs.get(key):
            self.links.append(attrs[key])


def static_audit(root, failures):
    # Frozen template/source snapshots are downloads, not rendered site routes.
    public = sorted(p for p in root.rglob('*.html') if p.relative_to(root).parts[0]
                    not in {'source', 'data', '.git'})
    graph = json.loads((root / 'data/graph/knowledge_graph_current.json').read_text())
    node_ids = {n['id'] for n in graph['nodes']}
    fake_origin = 'http://atlas.invalid'
    docs = {}
    counts = collections.Counter()
    for page in public:
        doc = Document()
        doc.feed(page.read_text(encoding='utf-8'))
        doc.close()
        relative = page.relative_to(root).as_posix()
        docs[relative] = doc
        for tag, count in doc.ids.items():
            if count > 1:
                failures.append(f'{relative}: duplicate anchor {tag}')
    for page, doc in docs.items():
        for href in doc.links:
            target = urlsplit(urljoin(fake_origin + '/' + page, href))
            if target.scheme not in {'http', 'https'} or target.netloc != 'atlas.invalid':
                continue
            local = unquote(target.path).lstrip('/')
            dest = root / local
            if not dest.resolve().is_relative_to(root):
                failures.append(f'{page}: outside site: {href}')
                continue
            if dest.is_dir():
                dest = dest / 'index.html'
                local = dest.relative_to(root).as_posix()
            counts['local_links_and_assets'] += 1
            if not dest.is_file():
                failures.append(f'{page}: missing file: {href}')
                continue
            if local in docs and target.fragment:
                counts['local_fragments'] += 1
                if unquote(target.fragment) not in docs[local].ids:
                    failures.append(f'{page}: missing anchor: {href}')
            if local == 'swe_knowledge_graph.html':
                for node_id in parse_qs(target.query).get('node', []):
                    counts['graph_node_links'] += 1
                    if node_id not in node_ids:
                        failures.append(f'{page}: unknown graph node: {href}')
    counts['public_html_files'] = len(public)
    return dict(counts)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def browser_audit(root, executable, failures):
    from playwright.sync_api import sync_playwright

    counts = collections.Counter()
    checked = []

    def require(condition, name):
        if not condition:
            raise AssertionError(name)
        checked.append(name)

    def click(page, locator):
        target = locator.get_attribute('href')
        absolute = urljoin(page.url, target)
        require(absolute.startswith(origin + '/'), f'Click stays on local site: {target}')
        locator.click()
        page.wait_for_url(absolute)

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=root))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    launch_path = executable or shutil.which('chromium') or None
    books = {'v05': ('Loop Engineering for AI Agents', 6, '9781808766404'),
             'v07': ('Engineering Software with Agentic AI', 12, 'B0HSPH86CG')}
    graph = json.loads((root / 'data/graph/knowledge_graph_current.json').read_text())
    lookup = {n['id']: n for n in graph['nodes']}
    review = json.loads((root / 'source/book_chapter_review.json').read_text())
    contents = {b['volume'].lower(): b['chapters'] for b in review['books']}
    reviewed_ids = {n['id'] for n in graph['nodes'] if n.get('atlas_display', {}).get('collection') == 'R'}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=launch_path, args=['--no-sandbox', '--disable-dev-shm-usage'])
            version = browser.version
            for scripts in (False, True):
                ctx = browser.new_context(java_script_enabled=scripts, viewport={'width': 1280, 'height': 960})
                page = ctx.new_page()
                page.set_default_timeout(10000)
                page.on('pageerror', lambda e: failures.append('JavaScript: ' + str(e)))
                page.on('response', lambda r: failures.append(f'HTTP {r.status}: {r.url}') if
                        r.url.startswith(origin + '/') and r.status >= 400 else None)
                for slug, (title, chapter_count, identifier) in books.items():
                    page.goto(origin + '/catalogues/volumes.html')
                    book_link = page.locator(f'main a[href="volumes/{slug}.html"]').filter(has_text=title)
                    click(page, book_link.first)
                    require(title.lower() in page.locator('main h1').inner_text().lower(), title + ' volume heading')
                    require(page.locator(f'main a[href*="{identifier}"]').count() > 0, title + ' edition destination')
                    require(not page.locator('a[href*="B0H9W2ST3F"]').count(), title + ' has current storefront')
                    toc = page.locator('main section').filter(has=page.get_by_role('heading', name='Contents', exact=True))
                    chapters = toc.locator('ol > li > a')
                    require(chapters.count() == chapter_count, title + ' complete numbered contents')
                    volume_url = page.url
                    if scripts:
                        page.set_viewport_size({'width': 390, 'height': 844})
                        require(page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'),
                                title + ' fits a mobile viewport')
                        cover = page.locator('main .book-cover img').first
                        require(cover.evaluate('el => el.complete && el.naturalWidth > 0 && '
                                               'el.getBoundingClientRect().width > 0 && !!el.alt.trim()'),
                                title + ' cover loads with alternative text')
                        counts['mobile_volume_pages'] += 1
                        page.set_viewport_size({'width': 1280, 'height': 960})
                    chapter_links = []
                    for index in range(chapter_count):
                        item = chapters.nth(index)
                        href = urljoin(volume_url, item.get_attribute('href'))
                        rid = unquote(urlsplit(href).fragment)
                        node = lookup[rid]
                        expected = contents[slug][index]
                        require(rid == expected['id'] and node['label'] == expected['title'],
                                title + ' chapter ' + str(index + 1) + ' agrees with the reviewed contents')
                        require(rid in reviewed_ids and node['volume_id'].lower() == slug
                                and int(node['chapter_number']) == index + 1 and item.inner_text().strip() == node['label'],
                                title + ' chapter ' + str(index + 1) + ' matches its ordered source record')
                        chapter_links.append((rid, href))
                    # Every chapter has a permanent anchor, reciprocal parent and topic routes.
                    click(page, chapters.first)
                    if scripts:
                        selector = page.locator('select[name="group"]')
                        selector.select_option(slug.upper())
                        require(page.locator('[data-record]:visible').count() == chapter_count,
                                title + ' catalogue filters to the correct book')
                        selector.select_option('')
                        require(page.locator('[data-record]:visible').count() == len(reviewed_ids),
                                title + ' clearing the catalogue filter restores every chapter')
                    for rid, href in chapter_links:
                        article = page.locator(f'[data-record][id="{rid}"]')
                        require(article.count() == 1, rid + ' exists once')
                        parent = article.locator('.chapter-volume a')
                        require(urljoin(href, parent.get_attribute('href')) == volume_url, rid + ' chapter to parent')
                        topics = article.locator('.chapter-connections a[href*="topics/"]')
                        require(topics.count() > 0, rid + ' chapter to topic')
                        counts['chapter_checks'] += 1
                    rid, href = chapter_links[0]
                    article = page.locator(f'[data-record][id="{rid}"]')
                    topic = article.locator('.chapter-connections a[href*="topics/"]').first
                    click(page, topic)
                    topic_url = page.url
                    reciprocal = page.locator('.chapter-connections a').filter(has_text=lookup[rid]['label'])
                    require(reciprocal.count() > 0 and urljoin(topic_url, reciprocal.first.get_attribute('href')) == href,
                            rid + ' topic to same chapter')
                    # Open an external-corpus record through this topic when present.
                    ext_record = page.locator('main a[href*="polimi.html#"], main a[href*="osmani.html#"], '
                                              'main a[href*="pragmatic-engineer.html#"], main a[href*="fowler.html#"]')
                    if ext_record.count():
                        click(page, ext_record.first)
                        record_id = unquote(urlsplit(page.url).fragment)
                        require(page.locator(f'[data-record][id="{record_id}"]').count() == 1, rid + ' topic to corpus record')
                        counts['topic_to_corpus_record_routes'] += 1
                        record = page.locator(f'[data-record][id="{record_id}"]')
                        topic_path = urlsplit(topic_url).path.split('/')[-1]
                        backlink = record.locator(f'a[href$="topics/{topic_path}"]').first
                        require(backlink.count() == 1, record_id + ' links back to the same topic')
                        if not backlink.is_visible():
                            container = backlink.locator('xpath=ancestor::details[1]')
                            container.locator('summary').first.click()
                        click(page, backlink)
                    click(page, page.locator('.chapter-connections a').filter(has_text=lookup[rid]['label']).first)
                    if scripts:
                        graph_link = article.locator('.record-links a[href*="swe_knowledge_graph.html"]').first
                        click(page, graph_link)
                        page.wait_for_function('id => window.atlasDiagnostics?.().selected === id', arg=rid)
                        diagnostics = page.evaluate('atlasDiagnostics()')
                        require(diagnostics['sourceCounts'].get('R') == len(reviewed_ids)
                                and diagnostics['visibleSources'] == len(reviewed_ids), 'R graph filter isolates reviewed chapters')
                        back = page.locator('#inspectorBody a').filter(has_text='static catalogue')
                        if not back.count():
                            back = page.locator('#inspectorBody a[href*="catalogues/"]').filter(has_text='chapter')
                        require(back.count() > 0 and urljoin(page.url, back.first.get_attribute('href')) == href,
                                rid + ' graph inspector returns to same static record')
                        click(page, back.first)
                        counts['graph_round_trips'] += 1
                    click(page, article.locator('.chapter-volume a'))
                    require(page.url == volume_url, rid + ' book–chapter–topic round trip')
                    counts['book_routes'] += 1
                page.goto(origin + '/catalogues/volumes/v05.html')
                archived = page.locator('a[href$="v05-h.html"]').first
                click(page, archived)
                require('historical edition' in page.locator('main').inner_text().lower(), 'Historical edition labelled')
                click(page, page.locator('main a[href*="books.html#B104"]').first)
                historical = page.locator('[data-record][id="B104"]')
                require(historical.count() == 1 and 'Non-Deterministic' in historical.locator('h2').inner_text(),
                        'Earlier B104 retains original title and anchor')
                counts['historical_routes'] += 1
                if scripts:
                    page.goto(origin + '/swe_knowledge_graph.html')
                    page.locator('#reviewedBooks').click()
                    page.wait_for_function("window.atlasDiagnostics?.().sourceCounts.R === 18")
                    diag = page.evaluate('atlasDiagnostics()')
                    visible = set(diag['visibleNodeIDs'])
                    edges = set(diag['visibleEdgeIDs'])
                    wanted_topics = {t['id'] for t in review['new_topics']}
                    require(diag['visibleSources'] == 18 and diag['grouping'] == 'volume',
                            'Book preset isolates both books’ chapters and groups by volume')
                    require(reviewed_ids | wanted_topics | {'PUB:PACKT', 'PUB:ESA'} <= visible,
                            'Book preset shows every chapter, both editions and all new topics')
                    for relation in ('BOOK_CHAPTER_OF', 'BOOK_CHAPTER_TOPIC'):
                        expected = {e['id'] for e in graph['edges'] if e['relation'] == relation}
                        require(expected and expected <= edges, 'Book preset displays all ' + relation + ' edges')
                        counts[relation.lower() + '_visible_edges'] = len(expected)
                    page.locator('[data-tab="sources"]').click()
                    for node_id in ('PACKT:C01', 'PUB:PACKT'):
                        page.locator('[data-result-node]').get_by_text(node_id, exact=True).click()
                        page.wait_for_function('id => atlasDiagnostics().selected === id', arg=node_id)
                        inspector = page.locator('#inspectorBody')
                        parent = inspector.locator('a[href="catalogues/volumes/v05.html"]')
                        require(parent.count() == 1 and parent.is_visible(), node_id + ' inspector offers parent volume')
                        if node_id == 'PACKT:C01':
                            entry = inspector.locator('a[href="catalogues/reviewed-chapters.html#PACKT%3AC01"]')
                            require(entry.count() == 1 and entry.is_visible(),
                                    'Chapter selected in graph offers its static chapter entry')
                        else:
                            click(page, parent)
                            require('Loop Engineering for AI Agents' in page.locator('main h1').inner_text(),
                                    'Selected Packt graph publication opens its catalogue volume')
                    counts['preset_new_topics'] = len(wanted_topics)
                ctx.close()
            browser.close()
        require(counts['topic_to_corpus_record_routes'] >= 2, 'At least one tested topic opens external-corpus records in both modes')
    finally:
        server.shutdown()
        server.server_close()
    return {'browser': version, 'passed_checks': len(checked), **counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--report', type=Path)
    parser.add_argument('--browser', help='Chromium or Chrome Headless Shell executable')
    parser.add_argument('--static-only', action='store_true')
    args = parser.parse_args()
    root = args.site.resolve()
    failures = []
    report = {'static': static_audit(root, failures)}
    if not args.static_only:
        try:
            report['browser_navigation'] = browser_audit(root, args.browser, failures)
        except Exception as error:
            failures.append('Browser audit: ' + str(error))
    report['failures'] = failures
    report['passed'] = not failures
    result = json.dumps(report, indent=2, ensure_ascii=False)
    print(result)
    if args.report:
        args.report.write_text(result + '\n', encoding='utf-8')
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
