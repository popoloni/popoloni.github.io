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
let baselineGraph, baselineHTML, baselineWIDs, baselineOriginalEdges, wIDs, originalEdges, chapterNodes = [], newIDs = [], changes = {}, artifactHash;
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
  baselineWIDs = new Set(baselineGraph.nodes.filter(node => node.collection === 'W').map(node => node.id));
  wIDs = new Set(baselineWIDs);
  const baselineEndpoint = endpoint => typeof endpoint === 'number' ? baselineGraph.nodes[endpoint].id : endpoint;
  originalEdges = baselineGraph.edges.filter(edge => wIDs.has(baselineEndpoint(edge.source)) && wIDs.has(baselineEndpoint(edge.target)) && edge.relation !== 'inferred_topic_similarity').map(edge => edge.id);
  baselineOriginalEdges = [...originalEdges];
  // The separately reviewed W migration extends the current research preset.
  // Ordinary article/practice updates still require the exact baseline preset.
  if (changes.kind === 'atlas_polimi_update/1') {
    const approved = changes.opening_preset?.source_ids;
    const additions = changes.source_additions || [];
    const expected = [...baselineWIDs, ...additions];
    if (!Array.isArray(approved) || !equalIDs(approved, expected) || !equalIDs(approved, graph.nodes.filter(node => node.collection === 'W').map(node => node.id))) {
      throw new Error('W migration preset differs from the baseline plus its reviewed W additions.');
    }
    if (!equalIDs(changes.opening_preset.original_w_ids || [], baselineWIDs)) throw new Error('W migration omitted an original W source.');
    const oldEdgeIDs = new Set(graph.edges.map(edge => edge.id));
    if (!originalEdges.every(id => oldEdgeIDs.has(id))) throw new Error('W migration lost an original visible research relationship.');
    wIDs = new Set(approved);
    originalEdges = graph.edges.filter(edge => wIDs.has(endpointID(edge.source)) && wIDs.has(endpointID(edge.target)) && edge.relation !== 'inferred_topic_similarity').map(edge => edge.id);
  }
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

async function checkPracticeRelationships() {
  const sourceCodes = ['W','O','P','F','B','N'];
  const edges = graph.edges.filter(e => e.family === 'practice');
  const associations = edges.map(e => ({source:endpointID(e.source), practice:endpointID(e.target),
    collection:nodeByID.get(endpointID(e.source)).collection, relation:e.relation}));
  const pair = r => `${r.source}|${r.practice}|${r.relation}`;
  const expectedPairs = associations.map(pair);
  const sourceIDs = graph.nodes.filter(n => sourceCodes.includes(n.collection)).map(n => n.id);
  const practiceIDs = graph.nodes.filter(n => n.collection === 'PAT').map(n => n.id);
  const mappedIDs = [...new Set(associations.map(r => r.source))];
  const excluded = graph.meta.practice_links.exclusions;
  const excludedIDs = excluded.map(r => r.source);
  const flat = JSON.parse(fs.readFileSync(path.join(site, 'data/practice_links.json'), 'utf8'));
  const coverage = JSON.parse(fs.readFileSync(path.join(site, 'data/practice_coverage.json'), 'utf8'));
  check('Practice download contains exactly the graph classifications', equalIDs(flat.relationships.map(pair), expectedPairs));
  check('Coverage partitions every source with no overlap or unreviewed records',
    equalIDs([...mappedIDs, ...excludedIDs], sourceIDs) && !mappedIDs.some(id => excludedIDs.includes(id)) && coverage.unreviewed_source_ids.length === 0 &&
    coverage.source_count === sourceIDs.length && coverage.mapped_source_count === mappedIDs.length && coverage.excluded_source_count === excludedIDs.length && coverage.link_count === edges.length);
  check('Every practice is linked and every mapped source has exactly one primary reading',
    equalIDs(new Set(associations.map(r => r.practice)), practiceIDs) && mappedIDs.every(id => edges.filter(e => endpointID(e.source) === id && e.attributes.primary).length === 1));
  const edgeByID = new Map(edges.map(e => [e.id,e]));
  check('Practice download retains reviewed rationales, bases and component boundaries', flat.relationships.every(r => {
    const e = edgeByID.get(r.edge_id);
    return e && r.rationale === e.attributes.rationale && r.primary === e.attributes.primary &&
      JSON.stringify(r.basis) === JSON.stringify(e.attributes.basis) && r.evaluated_component === e.attributes.evaluated_component;
  }));
  for (const code of sourceCodes) {
    const data = JSON.parse(fs.readFileSync(path.join(site, 'data/catalogues', slugs[code] + '.json'), 'utf8'));
    const wanted = associations.filter(r => r.collection === code);
    check(`${code} JSON exposes its exact source-practice pairs`, equalIDs(data.practice_relationships.map(pair), wanted.map(pair)));
    await load(`catalogues/${slugs[code]}.html`);
    const rows = await page.locator('[data-record]').evaluateAll(items => items.map(el => ({
      id:el.id, text:el.textContent, status:JSON.parse(el.dataset.reviewStatus),
      connections:JSON.parse(el.dataset.practiceConnections),
      targets:[...el.querySelectorAll('.practice-chip')].map(a => decodeURIComponent(new URL(a.href).hash.slice(1)))
    })));
    const errors = rows.filter(r => {
      const expected = wanted.filter(a => a.source === r.id), disposition = excluded.find(e => e.source === r.id);
      return !equalIDs(r.connections.map(pair), expected.map(pair)) || !equalIDs(r.targets, expected.map(a => a.practice)) ||
        (expected.length ? r.status !== 'mapped' : r.status !== 'excluded' || !disposition || !r.text.includes(disposition.reason));
    }).map(r => r.id);
    check(`${code} source cards expose exact reciprocal links or their review reason`, errors.length === 0, errors);
    const sample = wanted[0];
    await page.locator('select[name=practice]').selectOption(sample.practice);
    check(`${code} practice filter selects exact related sources`, equalIDs(await page.locator('[data-record]:visible').evaluateAll(rows => rows.map(r => r.id)), wanted.filter(r => r.practice === sample.practice).map(r => r.source)));
  }
  await load('catalogues/practices.html');
  const practiceRows = await page.locator('[data-record]').evaluateAll(rows => rows.map(el => ({
    id:el.id, connections:JSON.parse(el.dataset.practiceConnections),
    rendered:[...el.querySelectorAll('[data-practice-link]')].map(li => ({...JSON.parse(li.dataset.practiceLinkData),
      href:decodeURIComponent(new URL(li.querySelector('.practice-source-title a').href).hash.slice(1))}))
  })));
  check('All practice cards render exactly the reciprocal source associations',
    equalIDs(practiceRows.flatMap(r => r.connections.map(pair)), expectedPairs) &&
    equalIDs(practiceRows.flatMap(r => r.rendered.map(pair)), expectedPairs) &&
    practiceRows.every(r => r.rendered.every(a => a.practice === r.id && a.href === a.source)));
  const stats = await page.locator('.practice-coverage-stats strong').allTextContents();
  check('Displayed practice coverage agrees with the audited graph after all source exports',
    equalIDs(stats, [`${sourceIDs.length}/${sourceIDs.length}`, String(mappedIDs.length), `${practiceIDs.length}/${practiceIDs.length}`, String(edges.length)]), stats);
  const roles = [...new Set(associations.map(r => r.relation))];
  const combinations = await page.evaluate(({codes,roles}) => {
    const result = [], collection = document.querySelector('[name=sourceCollection]'), relation = document.querySelector('[name=linkRelation]');
    for (const code of codes) for (const role of roles) {
      collection.value = code; relation.value = role;
      relation.dispatchEvent(new Event('change', {bubbles:true}));
      const rows = [...document.querySelectorAll('[data-record]')].filter(r => !r.hidden);
      result.push({code,role,practiceIDs:rows.map(r => r.id), links:rows.flatMap(r => [...r.querySelectorAll('[data-practice-link]')].filter(li => !li.hidden).map(li => JSON.parse(li.dataset.practiceLinkData)))});
    }
    return result;
  }, {codes:sourceCodes,roles});
  const filterErrors = combinations.filter(r => {
    const wanted = associations.filter(a => a.collection === r.code && a.relation === r.role);
    return !equalIDs(r.practiceIDs, new Set(wanted.map(a => a.practice))) || !equalIDs(r.links.map(pair), wanted.map(pair));
  });
  check('Combined practice collection and relationship filters match the same association', filterErrors.length === 0, {combinations:combinations.length, errors:filterErrors});
  const focus = associations.find(r => r.relation === 'EVALUATES_PRACTICE') || associations[0];
  await page.locator('input[name=q]').fill('no-match-before-anchor-4a8e');
  await page.evaluate(id => {location.hash = encodeURIComponent(id);}, focus.practice);
  await page.waitForFunction(id => !document.getElementById(id).hidden && document.getElementById(id).querySelector('.practice-details').open, focus.practice);
  check('Practice anchor clears conflicting filters and opens guidance plus source reading',
    await page.locator(`[id="${focus.practice}"] .practice-sources`).evaluate(el => el.open) && await page.locator('input[name=q]').inputValue() === '' && await page.locator('[name=sourceCollection]').inputValue() === '');
  await load(`catalogues/${slugs[focus.collection]}.html?practice=${encodeURIComponent(focus.practice)}`);
  check('Source catalogue URL carries the exact practice prefilter',
    equalIDs(await page.locator('[data-record]:visible').evaluateAll(rows => rows.map(r => r.id)), associations.filter(r => r.collection === focus.collection && r.practice === focus.practice).map(r => r.source)));
  await load('catalogues/practice-map.html');
  check('Corpus review page contains every source disposition', await page.locator('[data-record]').count() === sourceIDs.length);
  await page.locator('[name=reviewStatus]').selectOption('excluded');
  check('Corpus review filter exposes exactly the explicitly excluded records', equalIDs(await page.locator('[data-record]:visible').evaluateAll(rows => rows.map(r => r.id.replace(/^map-/,''))), excludedIDs));
  await page.locator('[name=sourceCollection]').selectOption('W');
  check('Excluded records remain selectable by collection without a fabricated practice link',
    equalIDs(await page.locator('[data-record]:visible').evaluateAll(rows => rows.map(r => r.id.replace(/^map-/,''))), excludedIDs.filter(id => nodeByID.get(id).collection === 'W')));
  await page.locator('[data-clear]').click();
  await page.locator('[name=reviewStatus]').focus();
  await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter');
  check('Review-status filter is operable by keyboard', await page.locator('[name=reviewStatus]').inputValue() === 'mapped' && await page.locator('[data-record]:visible').count() === mappedIDs.length);
  await load('swe_knowledge_graph.html?practice=all', true);
  let pd = await page.evaluate(() => window.atlasPracticeDiagnostics());
  check('Complete practice graph reveals every mapped source and every classified edge',
    pd.mode === 'all' && equalIDs(pd.visibleSourceIDs,mappedIDs) && equalIDs(pd.visiblePracticeIDs,practiceIDs) && equalIDs(pd.visiblePracticeEdgeIDs,edges.map(e => e.id)));
  check('Complete practice graph leaves excluded records in their ordinary collections', !pd.visibleSourceIDs.some(id => excludedIDs.includes(id)));
  await load(`swe_knowledge_graph.html?practice=${encodeURIComponent(focus.practice)}`, true);
  pd = await page.evaluate(() => window.atlasPracticeDiagnostics());
  const focused = associations.filter(r => r.practice === focus.practice);
  check('Focused practice graph shows the exact source neighborhood', pd.mode === focus.practice && equalIDs(pd.visibleSourceIDs,focused.map(r => r.source)) && equalIDs(pd.visiblePracticeIDs,[focus.practice]));
  await page.locator('[data-practice-connections] summary').click();
  const focusEdge = edges.find(e => endpointID(e.source) === focus.source && endpointID(e.target) === focus.practice);
  check('Actual practice graph inspector exposes the reviewed rationale and component',
    await page.locator('[data-practice-connections]').innerText().then(t => t.includes(focusEdge.attributes.rationale) && (!focusEdge.attributes.evaluated_component || t.includes(focusEdge.attributes.evaluated_component))));
  await load(`swe_knowledge_graph.html?collection=${focus.collection}&node=${encodeURIComponent(focus.source)}`, true);
  await page.locator('[data-practice-connections] summary').click();
  await page.locator(`[data-practice-view="${focus.practice}"]`).click();
  check('Source inspector action opens the reciprocal practice neighborhood',
    (await page.evaluate(() => window.atlasPracticeDiagnostics())).mode === focus.practice);
  await page.setViewportSize({width:390,height:844});
  check('Focused practice graph fits a mobile viewport', !(await overflow()).overflow, await overflow());
  await page.setViewportSize({width:1440,height:1000});
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
      const correctTarget = config.practice_links_update
        ? destination?.searchParams.get('practice') === record.id
        : destination?.searchParams.get('node') === record.id && destination?.searchParams.get('collection') === 'PAT';
      if (!correctTarget) contentErrors.push(record.id + ':link');
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
      const expectedPracticeView = config.practice_links_update
        ? [id, ...graph.edges.filter(e => e.family === 'practice' && endpointID(e.target) === id).map(e => endpointID(e.source))]
        : practices.map(n => n.id);
      check(`${id} catalogue-to-Atlas opens its intended view with complete guidance`, state.selected === id && equalIDs(state.visibleNodeIDs, expectedPracticeView) && state.visibleContext === 0 && body.includes(record.attributes.practice.example.replace(/^Illustrative example:\s*/i, '')) && record.attributes.practice.steps.every(step => body.includes(step)) && body.includes(record.attributes.family_name));
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
  check('Bare atlas matches expected W sources and visible edges', diag.visibleSources === wIDs.size && diag.visibleContext === 0 && diag.visibleEdgeIDs.length === originalEdges.length, {sources: diag.visibleSources, context: diag.visibleContext, edges: diag.visibleEdgeIDs.length});
  check('Bare atlas matches exact reviewed W IDs', equalIDs(diag.visibleNodeIDs, wIDs));
  check('Bare atlas matches exact expected opening edge IDs', equalIDs(diag.visibleEdgeIDs, originalEdges));
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
    const graphLink = row.locator('.record-links a[href*="swe_knowledge_graph.html"]').first();
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
  check('Reset after all-switch verification restores exact expected nodes and edges', equalIDs(diag.visibleNodeIDs, wIDs) && diag.visibleContext === 0 && equalIDs(diag.visibleEdgeIDs, originalEdges));

  if (config.practice_links_update) await checkPracticeRelationships();

  // Published catalogues remain useful when JavaScript is unavailable.
  const noJS = await browser.newContext({javaScriptEnabled: false, viewport: {width: 1440, height: 1000}});
  observe(noJS);
  const staticPage = await noJS.newPage();
  for (const code of collections) {
    const response = await staticPage.goto(new URL(`catalogues/${slugs[code]}.html`, base).href, {waitUntil: 'load'});
    check(`${code} catalogue is complete without JavaScript`, response.status() === 200 && await staticPage.locator('[data-record]').count() === counts[code]);
  }
  if (config.practice_links_update) {
    await staticPage.goto(new URL('catalogues/practices.html', base).href, {waitUntil: 'load'});
    check('Every practice association remains present without JavaScript', await staticPage.locator('[data-practice-link]').count() === graph.edges.filter(e => e.family === 'practice').length);
    await staticPage.goto(new URL('catalogues/practice-map.html', base).href, {waitUntil: 'load'});
    check('Complete corpus review remains readable without JavaScript', await staticPage.locator('[data-record]').count() === graph.nodes.filter(n => ['W','O','P','F','B','N'].includes(n.collection)).length);
  }
  await noJS.close();

  for (const width of [1440, 390]) {
    await page.setViewportSize({width, height: width === 390 ? 844 : 1000});
    const pages = ['index.html', 'catalogues/index.html', `catalogues/${slugs.N}.html`, 'catalogues/chapters.html', 'catalogues/fowler.html', 'about.html', 'downloads.html', ...(counts.PAT ? ['catalogues/practices.html'] : []), ...(config.practice_links_update ? ['catalogues/practice-map.html'] : [])];
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
      baseline_default: {source_ids: baselineWIDs ? [...baselineWIDs] : [], edge_ids: baselineOriginalEdges || []},
      expected_opening_view: {source_ids: wIDs ? [...wIDs] : [], edge_ids: originalEdges || [], migration_kind: changes.kind || null},
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
