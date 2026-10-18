#!/usr/bin/env node
'use strict';

/**
 * Focused publication-page regression checks for Atlas 13.2.
 * Serves only local files and inspects Amazon link destinations without opening
 * an external page. Optional screenshots must be outside the packaged site.
 *
 * node source/test_publications_browser.js --site /path/to/site
 *   --output /path/to/work/publications_browser.json
 *   --browser /path/to/chrome-headless-shell [--screenshots]
 * Playwright resolves normally or via CODEX_PRIMARY_RUNTIME_NODE_MODULES.
 */

const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const arg = name => {
  const i = process.argv.indexOf('--' + name);
  return i < 0 ? undefined : process.argv[i + 1];
};
const site = path.resolve(arg('site') || '.');
const output = path.resolve(arg('output') || 'publications_browser.json');
const qa = path.dirname(output);
const screenshots = process.argv.includes('--screenshots');
const expectedASINs = {
  V01: 'B0G7LPJBTH', V02: 'B0GHFBNC5Z', V03: 'B0GZZDFMYF',
  V04: 'B0GMCFLH2C', V05: 'B0H9W2ST3F', V06: 'B0HN9J7VZG'
};
const seriesURL = 'https://www.amazon.com/dp/B0GHCXPBRM';
const bookURL = id => 'https://www.amazon.com/dp/' + expectedASINs[id];
const coverContract = {
  'NDseries.png': {
    width: 313, height: 270,
    sha256: 'e04c7dff813fe97935c4412c70c837876290a6ab2c578f6669e4fe9ceb159d08'
  },
  'NDSE2_cover.jpg': {
    width: 1000, height: 1499,
    sha256: 'd567a4293c156dcb7060ccc66800897e27c286736460a088c47cce0de016428e'
  }
};
const checks = [], pageErrors = [], consoleErrors = [], localHTTPFailures = [];
const externalRequests = new Set(), screenshotPaths = [], pageCoverage = [];
let browser, server, page, base, browserVersion, artifactHash, graphHash, siteVersion;
let fatalError = null, complete = false;
const started = new Date();
const sha256 = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');

// Same path/hash/size inventory and exclusions as automation/atlas_validate.py.
function artifactSHA256(root) {
  const rows = [], excluded = new Set(['__pycache__', '.git', '.pytest_cache', 'node_modules']);
  function walk(dir) {
    for (const name of fs.readdirSync(dir).sort()) {
      const full = path.join(dir, name), rel = path.relative(root, full).split(path.sep).join('/');
      const parts = rel.split('/');
      if (parts.some(p => excluded.has(p)) || parts[0] === 'verification' || rel === 'SHA256SUMS.txt'
          || name === '.DS_Store' || /\.py[co]$/.test(name)) continue;
      const stat = fs.lstatSync(full);
      if (stat.isSymbolicLink()) throw new Error('Artifact has a symbolic link: ' + rel);
      if (stat.isDirectory()) walk(full);
      else if (stat.isFile()) rows.push({path: rel, sha256: sha256(full), size: stat.size});
    }
  }
  walk(root);
  rows.sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0);
  return crypto.createHash('sha256').update(JSON.stringify(rows)).digest('hex');
}
function check(name, passed, detail) {
  const row = {check: name, passed: Boolean(passed)};
  if (detail !== undefined) row.detail = detail;
  checks.push(row);
  console.log(`${passed ? 'PASS' : 'FAIL'} ${name}`);
  return Boolean(passed);
}
function makeServer() {
  const mime = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8', '.json': 'application/json',
    '.jpg': 'image/jpeg', '.png': 'image/png', '.svg': 'image/svg+xml', '.webp': 'image/webp'};
  return http.createServer((request, response) => {
    try {
      let pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
      if (pathname === '/favicon.ico' && !fs.existsSync(path.join(site, 'favicon.ico'))) {
        response.writeHead(204); response.end(); return;
      }
      if (pathname.endsWith('/')) pathname += 'index.html';
      const file = path.resolve(site, '.' + pathname), rel = path.relative(site, file);
      if (rel.startsWith('..') || path.isAbsolute(rel)) {
        response.writeHead(403); response.end(); return;
      }
      if (!fs.existsSync(file) || !fs.statSync(file).isFile()) {
        response.writeHead(404); response.end('Not found'); return;
      }
      response.writeHead(200, {'Content-Type': mime[path.extname(file)] || 'application/octet-stream',
        'Cache-Control': 'no-store'});
      if (request.method === 'HEAD') response.end(); else fs.createReadStream(file).pipe(response);
    } catch (error) { response.writeHead(400); response.end('Invalid local request'); }
  });
}
async function load(relative, atlas = false) {
  const target = new URL(relative, base), previous = page.url();
  const response = await page.goto(target.href, {waitUntil: 'load', timeout: 45000});
  const sameDocument = !response && previous.split('#')[0] === target.href.split('#')[0];
  if (!check('Local page ' + relative, response?.status() === 200 || sameDocument, response?.status())) {
    throw new Error('Unable to load required local page: ' + relative);
  }
  if (atlas) await page.waitForFunction(() => typeof window.atlasDiagnostics === 'function');
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}
async function screenshot(name, selector) {
  if (screenshots) {
    const filename = path.join(qa, name);
    if (selector) await page.locator(selector).first().screenshot({path: filename});
    else await page.screenshot({path: filename, fullPage: false});
    screenshotPaths.push(filename);
  }
}
async function overflow(label) {
  const info = await page.evaluate(() => ({viewport: innerWidth,
    document: document.documentElement.scrollWidth, body: document.body.scrollWidth}));
  check(label + ' has no horizontal overflow', info.document <= info.viewport + 2 && info.body <= info.viewport + 2, info);
}
async function checkAmazonLink(url, label, locator = page.locator('main'), requireAmazonLabel = true) {
  const links = requireAmazonLabel ? locator.locator('a').filter({hasText: /Amazon/i}) : locator.locator('a');
  const matches = await links.evaluateAll((els, href) => els.filter(a => a.href === href).map(a => ({
    href: a.href, text: a.textContent.trim(), target: a.target, rel: a.rel,
    width: a.getBoundingClientRect().width, height: a.getBoundingClientRect().height
  })), url);
  check(label + (requireAmazonLabel ? ' has an explicit Amazon.com action' : ' has the direct Amazon.com destination'),
    matches.some(a => a.width > 0 && a.height > 0), matches);
  check(label + ' external new-tab action is safe', matches.every(a => a.target !== '_blank' || a.rel.includes('noopener')), matches);
}
async function checkCovers(label, required = []) {
  const infos = await page.locator('main img[src*="assets/books/"]').evaluateAll(async images => {
    await Promise.all(images.map(img => img.decode().catch(() => undefined)));
    return images.map(img => {
      const r = img.getBoundingClientRect(), cs = getComputedStyle(img), clipping = [];
      for (let parent = img.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
        const ps = getComputedStyle(parent), pr = parent.getBoundingClientRect();
        if ((['hidden', 'clip'].includes(ps.overflowX) && (r.left < pr.left - 2 || r.right > pr.right + 2)) ||
            (['hidden', 'clip'].includes(ps.overflowY) && (r.top < pr.top - 2 || r.bottom > pr.bottom + 2))) {
          clipping.push(parent.tagName + '.' + parent.className);
        }
      }
      return {file: new URL(img.src).pathname.split('/').at(-1), alt: img.alt,
        naturalWidth: img.naturalWidth, naturalHeight: img.naturalHeight, complete: img.complete,
        width: r.width, height: r.height, left: r.left, right: r.right, viewport: innerWidth,
        objectFit: cs.objectFit, clipping};
    });
  });
  check(label + ' includes its supplied cover artwork', required.every(file => infos.some(img => img.file === file)), {required, images: infos});
  for (const img of infos) {
    const contract = coverContract[img.file];
    check(label + ' image ' + img.file + ' loads at the original dimensions', contract && img.complete &&
      img.naturalWidth === contract.width && img.naturalHeight === contract.height, img);
    const naturalRatio = img.naturalWidth / img.naturalHeight, drawnRatio = img.width / img.height;
    check(label + ' image ' + img.file + ' is uncropped and keeps its proportions',
      img.width > 0 && img.height > 0 && img.left >= -2 && img.right <= img.viewport + 2 &&
      img.objectFit !== 'cover' && !img.clipping.length &&
      (['contain', 'scale-down'].includes(img.objectFit) || Math.abs(drawnRatio / naturalRatio - 1) < 0.01), img);
    check(label + ' image ' + img.file + ' has informative alternative text',
      img.alt.length >= 30 && /Non-Deterministic/i.test(img.alt) && /Enrico Papalini/i.test(img.alt), img.alt);
  }
}
async function catalogueSearch(relative, count, firstID, label) {
  await load(relative);
  const rows = page.locator('[data-record]');
  check(label + ' retains all ' + count + ' historical or chapter records', await rows.count() === count, await rows.count());
  await page.locator('input[name=q]').fill(firstID);
  check(label + ' search finds ' + firstID, await page.locator(`[data-record][id="${firstID}"]`).isVisible() &&
    await page.locator('[data-record]:visible').count() < count, await page.locator('[data-record]:visible').count());
  await page.locator('input[name=q]').fill('missing-publication-record-13-2-qa');
  check(label + ' empty search state works', await page.locator('#emptyState').isVisible() && await page.locator('[data-record]:visible').count() === 0);
  await page.locator('[data-clear]').click();
  check(label + ' clear restores all records', await page.locator('[data-record]:visible').count() === count);
}
async function localClick(link, expectedPath, label) {
  const href = await link.getAttribute('href');
  if (!href || new URL(href, page.url()).origin !== new URL(base).origin) throw new Error('Refusing non-local navigation: ' + href);
  await Promise.all([page.waitForURL(url => url.pathname.endsWith(expectedPath)), link.click()]);
  check(label, new URL(page.url()).pathname.endsWith(expectedPath), page.url());
}

async function run() {
  if (!arg('site') || !arg('output')) throw new Error('Required arguments: --site and --output.');
  fs.mkdirSync(qa, {recursive: true});
  const qaRelative = path.relative(site, qa);
  if (screenshots && (qaRelative === '' || (!qaRelative.startsWith('..') && !path.isAbsolute(qaRelative)))) {
    throw new Error('Screenshots must remain outside the distributable site.');
  }
  let playwright;
  try { playwright = require(arg('playwright') || 'playwright'); }
  catch (error) { playwright = require(path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, 'playwright')); }
  const candidates = [arg('browser'), process.env.ATLAS_BROWSER_EXECUTABLE, playwright.chromium.executablePath(),
    '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome'].filter(Boolean);
  const executablePath = candidates.find(candidate => fs.existsSync(candidate));
  if (!executablePath) throw new Error('Chromium unavailable. Supply --browser /path/to/executable.');
  artifactHash = artifactSHA256(site);
  const config = JSON.parse(fs.readFileSync(path.join(site, 'source/site_config.json'), 'utf8'));
  siteVersion = config.site_version;
  graphHash = sha256(path.join(site, config.graph_html || 'swe_knowledge_graph.html'));
  for (const [file, contract] of Object.entries(coverContract)) {
    check('Supplied ' + file + ' bytes are unchanged', sha256(path.join(site, 'assets/books', file)) === contract.sha256);
  }
  server = makeServer();
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  base = `http://127.0.0.1:${server.address().port}/`;
  browser = await playwright.chromium.launch({executablePath, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage']});
  browserVersion = browser.version();
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
  await context.route('**/*', route => {
    const url = route.request().url();
    if (/^https?:/.test(url) && !url.startsWith(base)) { externalRequests.add(url); return route.abort(); }
    return route.continue();
  });
  page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on('pageerror', error => pageErrors.push({url: page.url(), message: error.message}));
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push({url: page.url(), message: message.text()}); });
  page.on('response', response => { if (response.url().startsWith(base) && response.status() >= 400) localHTTPFailures.push({url: response.url(), status: response.status()}); });

  const pages = [
    {relative: 'catalogues/books.html', covers: ['NDseries.png'], series: true},
    {relative: 'catalogues/volumes.html', covers: ['NDseries.png'], series: true, allBooks: true},
    {relative: 'catalogues/ndse2.html', covers: ['NDSE2_cover.jpg'], volume: 'V06'},
    ...Object.keys(expectedASINs).map(id => ({relative: `catalogues/volumes/${id.toLowerCase()}.html`,
      volume: id, covers: id === 'V06' ? ['NDSE2_cover.jpg'] : ['NDseries.png']}))
  ];
  for (const viewport of [{label: 'desktop', width: 1440, height: 1000}, {label: 'mobile', width: 390, height: 844}]) {
    await page.setViewportSize({width: viewport.width, height: viewport.height});
    for (const item of pages) {
      await load(item.relative);
      const label = viewport.label + ' ' + item.relative;
      pageCoverage.push({page: item.relative, viewport});
      await overflow(label);
      await checkCovers(label, item.covers);
      if (item.series) await checkAmazonLink(seriesURL, label + ' series');
      if (item.volume) await checkAmazonLink(bookURL(item.volume), label + ' ' + item.volume);
      if (item.allBooks) for (const id of Object.keys(expectedASINs)) await checkAmazonLink(bookURL(id), label + ' ' + id);
      if (['catalogues/books.html', 'catalogues/ndse2.html', 'catalogues/volumes.html'].includes(item.relative)) {
        await screenshot(item.relative.replace('catalogues/', '').replace('.html', '') + '_' + viewport.label + '.png',
          viewport.label === 'mobile' ? 'main .book-feature' : undefined);
      }
    }
    await catalogueSearch('catalogues/books.html', 111, 'B001', viewport.label + ' earlier-books catalogue');
    await catalogueSearch('catalogues/ndse2.html', 13, 'NDSE2:C07', viewport.label + ' NDSE2 catalogue');
  }

  await page.setViewportSize({width: 1440, height: 1000});
  await load('catalogues/ndse2.html#NDSE2%3AC07');
  const chapterRow = page.locator('[data-record][id="NDSE2:C07"]');
  await localClick(chapterRow.locator('a[href="chapters/c07.html"]').first(), '/catalogues/chapters/c07.html', 'NDSE2 chapter guide navigation works');
  check('Chapter 7 guide retains learning goals and source citations', /Learning goals/i.test(await page.locator('main').innerText()) && /cited/i.test(await page.locator('main').innerText()));
  await load('catalogues/practices.html#PAT%3A027');
  const practice = page.locator('[data-record][id="PAT:027"]');
  check('Maker-Checker practice guide is expanded at its permanent link', await practice.locator(':scope > details').first().evaluate(el => el.open));
  await localClick(practice.locator('a[href*="swe_knowledge_graph.html"]').first(), '/swe_knowledge_graph.html', 'Practice-to-Atlas navigation works');
  await page.waitForFunction(() => typeof window.atlasDiagnostics === 'function');
  const practiceState = await page.evaluate(() => window.atlasDiagnostics());
  check('Practice still selects PAT:027 in its 84-practice collection', practiceState.selected === 'PAT:027' && practiceState.visibleNodeIDs.length === 84, practiceState);
  const back = page.locator('#inspectorBody a[href="catalogues/practices.html#PAT%3A027"]');
  if (check('Practice inspector retains its catalogue return link', await back.count() === 1)) {
    await localClick(back, '/catalogues/practices.html', 'Atlas-to-practice return navigation works');
  }
  await load('swe_knowledge_graph.html?node=PUB%3ANDSE2', true);
  const editionState = await page.evaluate(() => window.atlasDiagnostics());
  check('NDSE2 published-book Atlas node remains directly selectable', editionState.selected === 'PUB:NDSE2', editionState.selected);
  await checkAmazonLink(bookURL('V06'), 'NDSE2 Atlas inspector purchase link', page.locator('#inspectorBody'), false);
  await screenshot('ndse2_atlas_inspector_desktop.png');
  check('No external page was requested or opened', externalRequests.size === 0, [...externalRequests]);
  check('Visited pages have no JavaScript runtime errors', pageErrors.length === 0, pageErrors);
  check('Visited pages have no console errors', consoleErrors.length === 0, consoleErrors);
  check('Visited pages have no local HTTP failures', localHTTPFailures.length === 0, localHTTPFailures);
  check('Site contents stayed unchanged during browser verification', artifactSHA256(site) === artifactHash);
  complete = true;
}

(async () => {
  try { await run(); }
  catch (error) { fatalError = {type: error.name, message: error.message, stack: error.stack}; check('Browser verification completed', false, fatalError); }
  finally {
    if (browser) await browser.close();
    if (server) await new Promise(resolve => server.close(resolve));
    fs.mkdirSync(qa, {recursive: true});
    const report = {schema_version: 1, kind: 'atlas_publications_browser_validation',
      complete: complete && fatalError === null, checked_at: new Date().toISOString(),
      started_at: started.toISOString(), site_version: siteVersion, browser_version: browserVersion,
      passed: checks.filter(c => c.passed).length, failed: checks.filter(c => !c.passed).length,
      artifact_sha256: artifactHash, graph_html_sha256: graphHash,
      artifact_scope: 'All site file paths, SHA-256 and sizes except verification/, SHA256SUMS.txt and development caches.',
      external_urls_live_checked: false, external_navigation_performed: false,
      page_coverage: pageCoverage, screenshots: screenshotPaths, checks, error: fatalError};
    fs.writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify({complete: report.complete, passed: report.passed, failed: report.failed,
      artifact_sha256: artifactHash, graph_html_sha256: graphHash, output}));
    process.exitCode = report.complete && report.failed === 0 ? 0 : 1;
  }
})();
