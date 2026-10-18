#!/usr/bin/env node
'use strict';

/**
 * Reusable real-browser regression checks for any successor Atlas release.
 * Requires Node.js, the Playwright Node package and a Chromium-family browser.
 *
 * Usage:
 *   node browser_check.js --site /path/to/site --output /tmp/browser.json
 *     --baseline /path/to/prior/site --changes /path/to/update_audit.json
 *     --browser /path/to/chrome-headless-shell --playwright /path/to/playwright
 * Playwright resolves normally or via CODEX_PRIMARY_RUNTIME_NODE_MODULES.
 * Optional --screenshots writes images beside the report, outside the site.
 * This script serves local files only; it never deploys or changes graph data.
 */

const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');

function arg(name) {
  const index = process.argv.indexOf(`--${name}`);
  return index < 0 ? undefined : process.argv[index + 1];
}
const site = path.resolve(arg('site') || '.');
const output = path.resolve(arg('output') || 'atlas_browser_checks.json');
const qa = path.dirname(output);
const screenshots = process.argv.includes('--screenshots');
const sorted = values => [...values].sort();
const equalIDs = (left, right) => JSON.stringify(sorted(left)) === JSON.stringify(sorted(right));
let playwright, executablePath, sourceHTML = '', graph = {nodes: [], edges: [], relations: []}, config;
let nodeByID, collections = [], counts = {}, slugs, expectedRelations = [], endpointID;
let baselineGraph, baselineHTML, wIDs, originalEdges, chapterNodes = [], newIDs = [], changes = {}, artifactHash;
const excludedParts = new Set(['__pycache__', '.git', '.pytest_cache', 'node_modules']);
function artifactSHA256(root) {
  const rows = [];
  function walk(dir) {
    for (const name of fs.readdirSync(dir).sort()) {
      const full = path.join(dir, name), rel = path.relative(root, full).split(path.sep).join('/');
      const parts = rel.split('/');
      if (parts.some(p => excludedParts.has(p)) || parts[0] === 'verification' || rel === 'SHA256SUMS.txt' || name === '.DS_Store' || /\.py[co]$/.test(name)) continue;
      const stat = fs.lstatSync(full);
      if (stat.isSymbolicLink()) throw new Error('Artifact has a symbolic link: ' + rel);
      if (stat.isDirectory()) walk(full);
      else if (stat.isFile()) rows.push({path: rel, sha256: crypto.createHash('sha256').update(fs.readFileSync(full)).digest('hex'), size: stat.size});
    }
  }
  walk(root);
  rows.sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0);
  return crypto.createHash('sha256').update(JSON.stringify(rows)).digest('hex');
}
function readGraph(filename) {
  if (fs.statSync(filename).isDirectory()) filename = path.join(filename, 'swe_knowledge_graph.html');
  const text = fs.readFileSync(filename, 'utf8');
  if (/\.html?$/i.test(filename)) {
    const embedded = text.match(/<script\b[^>]*\bid=["']graph-data["'][^>]*>([\s\S]*?)<\/script>/i);
    if (!embedded) throw new Error('Missing embedded graph-data payload in ' + filename);
    return {graph: JSON.parse(embedded[1]), html: text};
  }
  return {graph: JSON.parse(text), html: null};
}
function initialize() {
  if (!arg('site') || !arg('output')) throw new Error('Required: --site /path/to/site --output /path/to/report.json');
  fs.mkdirSync(qa, {recursive: true});
  if (screenshots) {
    const rel = path.relative(site, qa);
    if (rel === '' || (!rel.startsWith('..') && !path.isAbsolute(rel))) throw new Error('Optional screenshots must be outside the distributable site.');
  }
  const explicitModule = arg('playwright') || process.env.ATLAS_PLAYWRIGHT;
  if (explicitModule) playwright = require(path.resolve(explicitModule));
  else {
    try { playwright = require('playwright'); }
    catch (error) {
      if (!process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES) throw new Error('Playwright unavailable. Supply --playwright /path/to/playwright or install the package. Original error: ' + error.message);
      playwright = require(path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, 'playwright'));
    }
  }
  const candidates = [arg('browser'), process.env.ATLAS_BROWSER_EXECUTABLE,
    playwright.chromium.executablePath(), '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome'].filter(Boolean);
  executablePath = candidates.find(filename => fs.existsSync(filename));
  if (!executablePath) throw new Error('Chromium unavailable. Pass --browser /path/to/executable. No browser check has passed.');
  config = JSON.parse(fs.readFileSync(path.join(site, 'source', 'site_config.json'), 'utf8'));
  const loaded = readGraph(path.join(site, config.graph_html || 'swe_knowledge_graph.html'));
  graph = loaded.graph; sourceHTML = loaded.html;
  const original = readGraph(arg('baseline') || path.join(site, config.original_template || 'source/atlas_v12_original.html'));
  baselineGraph = original.graph; baselineHTML = original.html;
  if (arg('changes')) changes = JSON.parse(fs.readFileSync(arg('changes'), 'utf8'));
  nodeByID = new Map(graph.nodes.map(node => [node.id, node]));
  collections = [...new Set(graph.nodes.map(node => node.collection).filter(Boolean))].sort();
  counts = Object.fromEntries(collections.map(code => [code, graph.nodes.filter(node => node.collection === code).length]));
  slugs = Object.fromEntries(config.collections.map(collection => [collection.code, collection.slug]));
  expectedRelations = [...new Set(graph.edges.map(edge => edge.relation))].sort();
  endpointID = endpoint => typeof endpoint === 'number' ? graph.nodes[endpoint].id : endpoint;
  const priorIDs = new Set(baselineGraph.nodes.map(node => node.id));
  const declared = changes.new_source_ids || changes.source_additions || changes.additions || changes.meta?.source_additions;
  newIDs = declared ? declared.map(item => typeof item === 'string' ? item : item.id) : graph.nodes.filter(node => !priorIDs.has(node.id) && ['O', 'P', 'F', 'W'].includes(node.collection)).map(node => node.id);
  const revisions = changes.changed_source_ids || changes.revisions || [];
  newIDs = [...new Set([...newIDs, ...revisions.map(item => typeof item === 'string' ? item : item.id)])];
  if (newIDs.length === 0) newIDs = ['O', 'P', 'F'].map(code => graph.nodes.filter(node => node.collection === code).at(-1)?.id).filter(Boolean);
  chapterNodes = graph.nodes.filter(node => node.collection === 'N');
  const book = JSON.parse(fs.readFileSync(path.join(site, config.book_json || 'source/ndse2_book.json'), 'utf8'));
  if (!equalIDs(book.chapters.map(chapter => chapter.id), chapterNodes.map(node => node.id))) throw new Error('NDSE2 graph chapter IDs differ from the supplied book metadata.');
  wIDs = new Set(baselineGraph.nodes.filter(node => node.collection === 'W').map(node => node.id));
  const baselineEndpoint = endpoint => typeof endpoint === 'number' ? baselineGraph.nodes[endpoint].id : endpoint;
  originalEdges = baselineGraph.edges.filter(edge => wIDs.has(baselineEndpoint(edge.source)) && wIDs.has(baselineEndpoint(edge.target)) && edge.relation !== 'inferred_topic_similarity').map(edge => edge.id);
  artifactHash = artifactSHA256(site);
}
const checks = [];
const pageErrors = [];
const consoleErrors = [];
const failedRequests = [];
const localHTTPFailures = [];
const externalRequests = new Set();
const started = new Date();
let browser, server, page, base, browserVersion;
let fatalError = null;
let relationshipSwitchChecks = [];

function saveProgress() {
  // The final report is always written, including initialization failures.
}
function check(name, passed, detail) {
  const record = {check: name, passed: Boolean(passed)};
  if (detail !== undefined) record.detail = detail;
  checks.push(record);
  saveProgress();
  console.log(`${record.passed ? 'PASS' : 'FAIL'} ${name}`);
  if (!passed) throw new Error(`${name}${detail === undefined ? '' : ': ' + JSON.stringify(detail)}`);
}
function idDifference(actual, expected) {
  const a = new Set(actual), e = new Set(expected);
  return {actual: a.size, expected: e.size,
    missing: [...e].filter(id => !a.has(id)).slice(0, 20),
    unexpected: [...a].filter(id => !e.has(id)).slice(0, 20)};
}
function makeServer() {
  const mime = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8', '.json': 'application/json', '.svg': 'image/svg+xml',
    '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.ico': 'image/x-icon',
    '.pdf': 'application/pdf', '.zip': 'application/zip'};
  return http.createServer((request, response) => {
    try {
      let pathname = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
      // An implicit browser favicon request is not a site resource declaration.
      if (pathname === '/favicon.ico' && !fs.existsSync(path.join(site, 'favicon.ico'))) {
        response.writeHead(204); response.end(); return;
      }
      if (pathname.endsWith('/')) pathname += 'index.html';
      const filename = path.resolve(site, '.' + pathname);
      const relative = path.relative(site, filename);
      if (relative.startsWith('..') || path.isAbsolute(relative)) {
        response.writeHead(403); response.end(); return;
      }
      if (!fs.existsSync(filename) || !fs.statSync(filename).isFile()) {
        response.writeHead(404); response.end('Not found'); return;
      }
      response.writeHead(200, {'Content-Type': mime[path.extname(filename)] || 'application/octet-stream', 'Cache-Control': 'no-store'});
      if (request.method === 'HEAD') response.end(); else fs.createReadStream(filename).pipe(response);
    } catch (error) {
      response.writeHead(400); response.end('Invalid local request');
    }
  });
}
async function load(relative, atlas = false) {
  const target = new URL(relative, base);
  const previous = new URL(page.url());
  const response = await page.goto(target.href, {waitUntil: 'load', timeout: 60000});
  const sameDocument = !response && previous.origin === target.origin && previous.pathname === target.pathname && previous.search === target.search && page.url() === target.href;
  check(`Local page ${relative}`, (response && response.status() === 200) || sameDocument, sameDocument ? 'same-document fragment navigation' : response?.status());
  if (atlas) await page.waitForFunction(() => typeof window.atlasDiagnostics === 'function', null, {timeout: 60000});
}
async function stable() {
  await page.waitForFunction(() => !window.atlasDiagnostics().layoutRunning, null, {timeout: 60000});
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}
async function diagnostics() { return page.evaluate(() => window.atlasDiagnostics()); }
async function overflow() {
  return page.evaluate(() => ({width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth, overflow: document.documentElement.scrollWidth > innerWidth + 2}));
}
async function screenshot(name) { if (screenshots) await page.screenshot({path: path.join(qa, name), fullPage: true}); }
function observe(context) {
  context.on('page', observed => {
    observed.on('pageerror', error => pageErrors.push({url: observed.url(), message: error.message}));
    observed.on('console', message => {
      if (message.type() === 'error') consoleErrors.push({url: observed.url(), message: message.text()});
    });
    observed.on('request', request => {
      if (/^https?:/.test(request.url()) && !request.url().startsWith(base)) externalRequests.add(request.url());
    });
    observed.on('requestfailed', request => {
      if (request.failure()?.errorText !== 'net::ERR_ABORTED') failedRequests.push({url: request.url(), error: request.failure()?.errorText});
    });
    observed.on('response', response => {
      if (response.url().startsWith(base) && response.status() >= 400) localHTTPFailures.push({url: response.url(), status: response.status()});
    });
  });
}

async function run() {
  initialize();
  check('Every selected new or revised source ID exists', newIDs.every(id => nodeByID.has(id)), newIDs);
  check('NDSE2 chapters follow the supplied manuscript metadata', chapterNodes.length === counts.N, counts);
  if (baselineHTML) {
    const before = baselineHTML.match(/const defaultState\s*=.*?;/)?.[0];
    const after = sourceHTML.match(/const defaultState\s*=.*?;/)?.[0];
    check('Baseline defaultState code is unchanged', Boolean(before && before === after));
  }
  check('Every graph source collection has a static catalogue', collections.every(code => slugs[code]), slugs);
  check('Relationship metadata covers the exact graph relation set', equalIDs(graph.relations.map(relation => relation.id), expectedRelations));

  server = makeServer();
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  base = `http://127.0.0.1:${server.address().port}/`;
  browser = await playwright.chromium.launch({executablePath, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage']});
  browserVersion = browser.version();
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, acceptDownloads: true});
  observe(context);
  page = await context.newPage();
  page.setDefaultTimeout(30000);

  await load('index.html');
  check('Landing title identifies the Knowledge Atlas', (await page.title()).includes('Knowledge Atlas'));
  for (const code of collections) {
    const card = page.locator('.collection-card').filter({has: page.locator(`a[href="catalogues/${slugs[code]}.html"]`)}).first();
    check(`Landing ${code} count follows graph data`, await card.locator('.pill').innerText().then(text => Number(text.replace(/[^0-9]/g, '')) === counts[code]));
  }
  check('Desktop home image loads', await page.locator('.hero-visual img').evaluate(image => image.complete && image.naturalWidth > 0));
  check('Desktop home has no horizontal overflow', !(await overflow()).overflow, await overflow());
  await screenshot('home_desktop.png');

  const extraCatalogues = ['practices', 'occurrences'];
  for (const slug of [...new Set([...Object.values(slugs), ...extraCatalogues])]) {
    const dataFile = path.join(site, 'data', 'catalogues', `${slug}.json`);
    const catalogue = JSON.parse(fs.readFileSync(dataFile, 'utf8'));
    const expected = Array.isArray(catalogue) ? catalogue.length : catalogue.records.length;
    await load(`catalogues/${slug}.html`);
    check(`${slug} renders the dynamic record count`, await page.locator('[data-record]').count() === expected, expected);
    const firstID = await page.locator('[data-record]').first().getAttribute('id');
    await page.locator('input[name=q]').fill(firstID);
    check(`${slug} search includes its named record`, await page.locator(`[data-record][id="${firstID}"]`).isVisible());
    await page.locator('input[name=q]').fill('no-source-can-match-this-token-7e962');
    check(`${slug} empty state works`, await page.locator('#emptyState').isVisible() && await page.locator('[data-record]:visible').count() === 0);
    await page.locator('[data-clear]').click();
    check(`${slug} clear restores all records`, await page.locator('[data-record]:visible').count() === expected);
  }

  if (counts.PAT) {
    const practices = graph.nodes.filter(node => node.collection === 'PAT');
    const families = graph.nodes.filter(node => node.kind === 'practice_family');
    await load('catalogues/practices.html');
    const rendered = await page.locator('[data-record]').evaluateAll(rows => rows.map(row => ({
      id: row.id, text: row.textContent,
      href: [...row.querySelectorAll('a')].find(a => a.href.includes('swe_knowledge_graph.html'))?.href
    })));
    const contentErrors = [];
    for (const record of practices) {
      const row = rendered.find(item => item.id === record.id), p = record.attributes.practice;
      const strings = [record.summary, record.limitation, p.purpose, p.example.replace(/^Illustrative example:\s*/i, ''),
        ...p.when_to_use, ...p.when_not_to_use, ...p.prerequisites, ...p.steps, ...p.verification, ...p.outputs, ...p.risks];
      if (!row || strings.some(value => !row.text.includes(value))) contentErrors.push(record.id);
      const destination = row?.href ? new URL(row.href) : null;
      if (!destination || destination.searchParams.get('node') !== record.id || destination.searchParams.get('collection') !== 'PAT') contentErrors.push(record.id + ':link');
    }
    check('All English practice guides render complete operational content and correct Atlas links', !contentErrors.length && rendered.length === practices.length, {practices: practices.length, errors: contentErrors});
    const familyErrors = [];
    for (const family of families) {
      await page.locator('select[name=group]').selectOption(family.id);
      const shown = await page.locator('[data-record]:visible').evaluateAll(rows => rows.map(row => row.id));
      const expected = practices.filter(node => node.families.includes(family.id)).map(node => node.id);
      if (!equalIDs(shown, expected)) familyErrors.push({family: family.id, ...idDifference(shown, expected)});
    }
    check('Every practice-family catalogue filter selects its exact members', familyErrors.length === 0, {families: families.length, errors: familyErrors});
    await page.locator('[data-clear]').click();
    const exampleText = practices[0].attributes.practice.example.replace(/^Illustrative example:\s*/, '').split(/\s+/).slice(0, 7).join(' ');
    await page.locator('input[name=q]').fill(exampleText);
    check('Practice search includes operational details inside the expanded guide', await page.locator(`[data-record][id="${practices[0].id}"]`).isVisible());
    await load('catalogues/practices.html#' + encodeURIComponent(practices[0].id));
    await screenshot('practices_desktop.png');
    const sampleIDs = [...new Set([practices[0].id, practices.at(-1).id,
      ...families.map(f => practices.find(p => p.families.includes(f.id))?.id).filter(Boolean)])];
    for (const id of sampleIDs) {
      const record = nodeByID.get(id);
      await load('catalogues/practices.html#' + encodeURIComponent(id));
      const row = page.locator(`[data-record][id="${id}"]`);
      check(`${id} direct catalogue entry expands its operational guide`, await row.locator(':scope > details').first().evaluate(el => el.open));
      await Promise.all([page.waitForURL(url => url.pathname.endsWith('/swe_knowledge_graph.html')),
        row.locator('a[href*="swe_knowledge_graph.html"]').first().click()]);
      await page.waitForFunction(() => typeof window.atlasDiagnostics === 'function');
      const state = await diagnostics();
      const body = await page.locator('#inspectorBody').innerText();
      check(`${id} catalogue-to-Atlas opens PAT with complete guidance`, state.selected === id && equalIDs(state.visibleNodeIDs, practices.map(n => n.id)) && state.visibleContext === 0 && body.includes(record.attributes.practice.example.replace(/^Illustrative example:\s*/i, '')) && record.attributes.practice.steps.every(step => body.includes(step)) && body.includes(record.attributes.family_name));
      const pane = await page.locator('#inspector').evaluate(el => {
        const bounds = el.getBoundingClientRect(), body = document.getElementById('inspectorBody');
        return {left: bounds.left, right: bounds.right, viewport: window.innerWidth,
          bodyWidth: body.clientWidth, bodyScrollWidth: body.scrollWidth};
      });
      check(`${id} complete inspector fits the viewport and wraps its content`, pane.left >= 0 && pane.right <= pane.viewport + 1 && pane.bodyScrollWidth <= pane.bodyWidth + 1, pane);
      const back = page.locator(`#inspectorBody a[href="catalogues/practices.html#${encodeURIComponent(id)}"]`);
      check(`${id} inspector has a permanent catalogue return link`, await back.count() === 1);
      await Promise.all([page.waitForURL(url => url.pathname.endsWith('/catalogues/practices.html')), back.click()]);
      check(`${id} Atlas-to-catalogue returns to the expanded entry`, decodeURIComponent(new URL(page.url()).hash.slice(1)) === id && await page.locator(`[data-record][id="${id}"] > details`).first().evaluate(el => el.open));
    }
    await load('swe_knowledge_graph.html?node=' + encodeURIComponent(practices[0].id), true);
    let practiceDiag = await diagnostics();
    check('Legacy practice node-only links now select the PAT collection', practiceDiag.selected === practices[0].id && equalIDs(practiceDiag.visibleNodeIDs, practices.map(n => n.id)) && practiceDiag.visibleContext === 0);
    await page.locator('#practicesOnly').click();
    practiceDiag = await diagnostics();
    check('Practices preset selects all descriptors in family view', equalIDs(practiceDiag.visibleNodeIDs, practices.map(n => n.id)) && practiceDiag.grouping === 'family');
    await screenshot('practices_atlas_desktop.png');
    for (const family of families) {
      await page.locator('#noGroups').click();
      await page.locator(`[data-filter-group="${family.id}"]`).check();
      const expected = practices.filter(node => node.families.includes(family.id)).map(node => node.id);
      check(`${family.id} Atlas family filter selects exact practice members`, equalIDs((await diagnostics()).visibleNodeIDs, expected));
    }
    await page.locator('#resetBtn').click();
    check('Reset from the Practices collection restores the exact Polimi view', equalIDs((await diagnostics()).visibleNodeIDs, wIDs));
  }

  await load('swe_knowledge_graph.html', true);
  await stable();
  let diag = await diagnostics();
  check('Bare atlas preserves baseline W sources and visible edges', diag.visibleSources === wIDs.size && diag.visibleContext === 0 && diag.visibleEdgeIDs.length === originalEdges.length, {sources: diag.visibleSources, context: diag.visibleContext, edges: diag.visibleEdgeIDs.length});
  check('Bare atlas preserves exact W IDs', equalIDs(diag.visibleNodeIDs, wIDs));
  check('Bare atlas preserves exact original edge IDs', equalIDs(diag.visibleEdgeIDs, originalEdges));
  check('Atlas diagnostics report current totals', diag.totalNodes === graph.nodes.length && diag.totalEdges === graph.edges.length && diag.totalRelations === expectedRelations.length, {nodes: diag.totalNodes, edges: diag.totalEdges, relationships: diag.totalRelations});
  check('Every current relation has a switch', await page.locator('[data-relation]').count() === expectedRelations.length);
  for (const code of collections) {
    const control = page.locator('label.source-row').filter({has: page.locator(`[data-collection="${code}"]`)});
    check(`${code} source-control label shows the current total`, Number((await control.locator('.count').innerText()).replace(/[^0-9]/g, '')) === counts[code]);
  }
  await screenshot('atlas_desktop.png');

  await page.locator('#ndse2Only').click();
  diag = await diagnostics();
  const ndse2IDs = graph.nodes.filter(node => node.collection === 'N').map(node => node.id);
  check('NDSE2 preset shows exactly the supplied chapter records', diag.visibleContext === 0 && equalIDs(diag.visibleNodeIDs, ndse2IDs), idDifference(diag.visibleNodeIDs, ndse2IDs));
  await stable();
  diag = await diagnostics();
  const canvasBox = await page.locator('#graph').boundingBox();
  const hoverNode = diag.positions.map(position => ({...position,
    screenX: position.x * diag.camera.k + diag.camera.x,
    screenY: position.y * diag.camera.k + diag.camera.y
  })).sort((a, b) => Math.hypot(a.screenX - canvasBox.width / 2, a.screenY - canvasBox.height / 2) - Math.hypot(b.screenX - canvasBox.width / 2, b.screenY - canvasBox.height / 2))[0];
  await page.mouse.move(canvasBox.x + hoverNode.screenX, canvasBox.y + hoverNode.screenY);
  await page.locator('#tooltip.visible').waitFor({state: 'visible'});
  const hoverText = await page.locator('#tooltip').innerText();
  check('NDSE2 canvas hover identifies the chapter and its published provenance', hoverText.includes(hoverNode.id) && hoverText.includes('Published NDSE2 chapter') && !hoverText.includes('undefined'), hoverText);
  await screenshot('ndse2_hover_desktop.png');
  await page.locator('#resetBtn').click();
  check('Reset from NDSE2 restores the Polimi-only preset', equalIDs((await diagnostics()).visibleNodeIDs, wIDs));

  for (const code of collections) {
    await load(`swe_knowledge_graph.html?collection=${code}`, true);
    diag = await diagnostics();
    const expectedIDs = graph.nodes.filter(node => node.collection === code).map(node => node.id);
    check(`${code} collection deep link selects exact current records`, equalIDs(diag.visibleNodeIDs, expectedIDs), idDifference(diag.visibleNodeIDs, expectedIDs));
    check(`${code} diagnostics expose its dynamic count`, diag.sourceCounts[code] === counts[code], diag.sourceCounts);
  }

  for (const id of [...newIDs, ...chapterNodes.map(node => node.id)]) {
    const node = nodeByID.get(id), slug = slugs[node.collection];
    await load(`catalogues/${slug}.html#${encodeURIComponent(id)}`);
    const row = page.locator(`[data-record][id="${id}"]`);
    check(`${id} static anchor opens its details`, await row.locator(':scope > details').first().evaluate(element => element.open));
    const graphLink = row.locator('a[href*="swe_knowledge_graph.html"]').first();
    check(`${id} static record links to the graph`, await graphLink.count() === 1);
    const destination = new URL(await graphLink.getAttribute('href'), page.url());
    check(`${id} graph link carries the correct record and collection`, destination.searchParams.get('node') === id && (destination.searchParams.get('collection') || '').split(',').includes(node.collection));
    if (newIDs.includes(id) || id === chapterNodes[0].id || id === chapterNodes[chapterNodes.length - 1].id) {
      await Promise.all([page.waitForURL(url => url.pathname.endsWith('/swe_knowledge_graph.html')), graphLink.click()]);
      await page.waitForFunction(() => typeof window.atlasDiagnostics === 'function');
      check(`${id} real static-to-graph navigation selects the record`, (await diagnostics()).selected === id);
      const backLink = page.locator(`#inspectorBody a[href="catalogues/${slug}.html#${encodeURIComponent(id)}"]`);
      check(`${id} inspector links back to static record`, await backLink.count() === 1);
      await Promise.all([page.waitForURL(url => url.pathname.endsWith(`/catalogues/${slug}.html`)), backLink.click()]);
      check(`${id} real graph-to-static navigation retains the anchor`, decodeURIComponent(new URL(page.url()).hash.slice(1)) === id && await page.locator(`[data-record][id="${id}"] > details`).first().evaluate(element => element.open));
    }
  }

  // Actual citations are a separate user-selected view, never implied by mappings.
  const sourceCodes = collections.filter(code => code !== 'N' && code !== 'PAT');
  const chapter = graph.chapters.find(item => graph.nodes.some(node => sourceCodes.includes(node.collection) && node.actual.includes(item.id)));
  check('Current citation layer has a chapter with source citations', Boolean(chapter));
  await load(`swe_knowledge_graph.html?collection=${sourceCodes.join(',')}&grouping=chapter`, true);
  await page.locator('#chapterBasis').selectOption('actual');
  await page.locator('#noGroups').click();
  await page.locator(`[data-filter-group="${chapter.id}"]`).check();
  diag = await diagnostics();
  const actualIDs = graph.nodes.filter(node => sourceCodes.includes(node.collection) && node.actual.includes(chapter.id)).map(node => node.id);
  check('Actual-citation UI selects exactly current chapter citations', diag.chapterBasis === 'actual' && equalIDs(diag.visibleNodeIDs, actualIDs), idDifference(diag.visibleNodeIDs, actualIDs));
  const basisText = await page.locator('#chapterBasis option[value=actual]').innerText();
  check('Actual-citation control no longer describes the historical v11 layer', !/\bv11\b/i.test(basisText), basisText);
  const citationURL = `swe_knowledge_graph.html?collection=${sourceCodes.join(',')}&grouping=chapter&group=${encodeURIComponent(chapter.id)}&chapterBasis=actual`;
  await load(citationURL, true);
  diag = await diagnostics();
  check('Actual-citation deep link preserves the selected basis and exact records', diag.chapterBasis === 'actual' && equalIDs(diag.visibleNodeIDs, actualIDs), {basis: diag.chapterBasis, ...idDifference(diag.visibleNodeIDs, actualIDs)});

  await load('swe_knowledge_graph.html?collection=invalid&node=NOT_A_NODE', true);
  check('Invalid deep link preserves the original starting view', equalIDs((await diagnostics()).visibleNodeIDs, wIDs));

  // Exercise actual DOM controls against exact keyed edges, including new types.
  await load('swe_knowledge_graph.html', true);
  await page.locator('#fullGraph').evaluate(element => element.click());
  diag = await diagnostics();
  check('Full graph includes every source and context node', diag.visibleNodeIDs.length === graph.nodes.length && diag.visibleEdgeIDs.length === graph.edges.length, {nodes: diag.visibleNodeIDs.length, edges: diag.visibleEdgeIDs.length});
  await page.locator('#noEdges').evaluate(element => element.click());
  const switchChecks = [];
  for (let offset = 0; offset < expectedRelations.length; offset += 20) {
    const chunk = expectedRelations.slice(offset, offset + 20);
    switchChecks.push(...await page.evaluate(relations => {
      const data = JSON.parse(document.getElementById('graph-data').textContent);
      const controls = new Map([...document.querySelectorAll('[data-relation]')].map(input => [input.dataset.relation, input]));
      return relations.map(relation => {
        const input = controls.get(relation);
        if (!input) return {relation, passed: false, error: 'Missing switch'};
        input.checked = true;
        input.dispatchEvent(new Event('change', {bubbles: true}));
        const actual = window.atlasDiagnostics().visibleEdgeIDs.slice().sort();
        const expected = data.edges.filter(edge => edge.relation === relation).map(edge => edge.id).sort();
        const result = {relation, passed: JSON.stringify(actual) === JSON.stringify(expected), actual: actual.length, expected: expected.length};
        input.checked = false;
        input.dispatchEvent(new Event('change', {bubbles: true}));
        if (window.atlasDiagnostics().visibleEdgeIDs.length !== 0) {result.passed = false; result.disableFailed = true;}
        return result;
      });
    }, chunk));
  }
  relationshipSwitchChecks = switchChecks;
  check('Every relationship switch exposes exact keyed edges and fully disables them', switchChecks.length === expectedRelations.length && switchChecks.every(item => item.passed), {tested: switchChecks.length, failures: switchChecks.filter(item => !item.passed)});
  await page.locator('#resetBtn').evaluate(element => element.click());
  await stable();
  diag = await diagnostics();
  check('Reset after all-switch verification restores exact baseline nodes and edges', equalIDs(diag.visibleNodeIDs, wIDs) && diag.visibleContext === 0 && equalIDs(diag.visibleEdgeIDs, originalEdges));

  // Published catalogues remain useful when JavaScript is unavailable.
  const noJS = await browser.newContext({javaScriptEnabled: false, viewport: {width: 1440, height: 1000}});
  observe(noJS);
  const staticPage = await noJS.newPage();
  for (const code of collections) {
    const response = await staticPage.goto(new URL(`catalogues/${slugs[code]}.html`, base).href, {waitUntil: 'load'});
    check(`${code} catalogue is complete without JavaScript`, response.status() === 200 && await staticPage.locator('[data-record]').count() === counts[code]);
  }
  await noJS.close();

  for (const width of [1440, 390]) {
    await page.setViewportSize({width, height: width === 390 ? 844 : 1000});
    const pages = ['index.html', 'catalogues/index.html', `catalogues/${slugs.N}.html`, 'catalogues/chapters.html', 'catalogues/fowler.html', 'about.html', 'downloads.html', ...(counts.PAT ? ['catalogues/practices.html'] : [])];
    for (const relative of pages) {
      await load(relative);
      const dimensions = await overflow();
      check(`${width}px responsive layout: ${relative}`, dimensions.width === width && !dimensions.overflow, dimensions);
      if (width === 390 && relative === 'index.html') await screenshot('home_mobile.png');
      if (relative === `catalogues/${slugs.N}.html`) await screenshot(`ndse2_${width}.png`);
    }
    await load('swe_knowledge_graph.html', true);
    await stable();
    const dimensions = await overflow();
    check(`${width}px atlas has no page overflow`, dimensions.width === width && !dimensions.overflow, dimensions);
    check(`${width}px atlas retains the original preset`, equalIDs((await diagnostics()).visibleNodeIDs, wIDs) && equalIDs((await diagnostics()).visibleEdgeIDs, originalEdges));
    if (width === 390) {
      await page.locator('#mobileMenu').click();
      check('Mobile source controls can be opened', await page.locator('#mobileMenu').getAttribute('aria-expanded') === 'true');
      check('Mobile NDSE2 collection control is reachable', await page.locator('[data-collection=N]').isVisible());
      const mask = page.locator('#sidebarMask');
      const maskBox = await mask.boundingBox();
      await mask.click({position: {x: maskBox.width - 6, y: Math.min(maskBox.height / 2, 240)}});
      check('Mobile backdrop closes source controls', await page.locator('#mobileMenu').getAttribute('aria-expanded') === 'false');
      await screenshot('atlas_mobile.png');
    }
  }
  check('The tested site file inventory remains unchanged', artifactSHA256(site) === artifactHash);
  check('No unhandled JavaScript errors', pageErrors.length === 0, pageErrors);
  check('No browser console errors', consoleErrors.length === 0, consoleErrors);
  check('No failed local resource requests', failedRequests.length === 0 && localHTTPFailures.length === 0, {failedRequests, localHTTPFailures});
  check('Local site navigation makes no external network requests', externalRequests.size === 0, [...externalRequests]);
}

(async () => {
  try {
    await run();
  } catch (error) {
    fatalError = {message: error.message, stack: error.stack};
    console.error(error.stack);
    if (page && !page.isClosed()) {
      try { await screenshot('browser_failure.png'); } catch (_) { /* Preserve the original failure. */ }
    }
    process.exitCode = 1;
  } finally {
    try { if (browser) await browser.close(); } catch (error) { fatalError ||= {message: error.message}; process.exitCode = 1; }
    try { if (server) await new Promise(resolve => server.close(resolve)); } catch (error) { fatalError ||= {message: error.message}; process.exitCode = 1; }
    const report = {schema_version: 1, kind: 'atlas_browser_validation', started: started.toISOString(), finished: new Date().toISOString(),
      passed: checks.filter(item => item.passed).length, failed: checks.filter(item => !item.passed).length + (fatalError && !checks.some(item => !item.passed) ? 1 : 0),
      complete: fatalError === null, browser: browserVersion || null, navigation: 'real local HTTP navigation and real DOM controls',
      nativeSafariTested: false, githubDeployed: false, siteSourceModified: false,
      graph_html_sha256: sourceHTML ? crypto.createHash('sha256').update(sourceHTML).digest('hex') : null,
      graphHTMLSHA256: sourceHTML ? crypto.createHash('sha256').update(sourceHTML).digest('hex') : null,
      artifact_sha256: artifactHash || null,
      artifact_scope: 'All site file paths, SHA-256 and sizes except verification/, SHA256SUMS.txt and development caches.',
      baseline_default: {source_ids: wIDs ? [...wIDs] : [], edge_ids: originalEdges || []},
      relationship_switch_checks: relationshipSwitchChecks,
      graphNodes: graph.nodes.length, graphEdges: graph.edges.length, graphRelations: expectedRelations.length,
      dynamicSourceCounts: counts, checks, pageErrors, consoleErrors, failedRequests, localHTTPFailures,
      externalNetworkRequests: [...externalRequests], fatalError};
    try { fs.mkdirSync(qa, {recursive: true}); fs.writeFileSync(output, JSON.stringify(report, null, 2) + '\n'); }
    catch (error) { console.error('Could not write browser report:', error.message); process.exitCode = 1; }
    console.log(`BROWSER TOTAL ${report.passed} passed / ${report.failed} failed; complete=${report.complete}`);
    console.log(`Report: ${output}`);
  }
})();
