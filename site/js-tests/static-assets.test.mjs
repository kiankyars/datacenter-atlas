// Guards for the frontend files the builder copies verbatim: the explorer
// template's DOM hooks and tokens, CSP-safe markup and scripts, the CSS status
// palette, and the vendored Leaflet hashes.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { Script } from 'node:vm';
import { loadCore, loadCurrentDatasetFeatures, repoRoot } from './csv-helper.mjs';

const read = (path) => readFileSync(new URL(path, repoRoot), 'utf8');
const template = read('site/templates/explorer.html');
const css = read('site/static/assets/site.css');
const assetDir = 'site/static/assets/';
const scripts = readdirSync(new URL(assetDir, repoRoot)).filter((name) => name.endsWith('.js'));

function elementWithId(id) {
  const match = new RegExp(`<([a-z][a-z0-9]*)\\b[^>]*\\bid="${id}"[^>]*>`, 'i').exec(template);
  assert.ok(match, `#${id} exists in explorer.html`);
  return { tag: match[1].toLowerCase(), html: match[0] };
}

test('explorer.html provides every stable DOM hook (spec 6.1)', () => {
  const hooks = {
    'atlas-search': 'input', 'atlas-country': 'select', 'atlas-status': 'fieldset', 'atlas-locator': 'select',
    'atlas-power': 'input', 'atlas-from': 'select', 'atlas-to': 'select', 'atlas-sort': 'select',
    'atlas-clear': 'button', 'atlas-list': null, 'atlas-map': 'div', 'atlas-detail': null,
    'atlas-detail-title': null, 'atlas-detail-close': 'button', 'atlas-export-csv': 'button',
    'atlas-export-geojson': 'button', 'atlas-copy-link': 'button', 'atlas-error': null,
    'atlas-tab-list': 'button', 'atlas-tab-map': 'button', 'atlas-fit': 'button', 'atlas-count': null
  };
  for (const [id, tag] of Object.entries(hooks)) {
    const el = elementWithId(id);
    if (tag) {
      assert.equal(el.tag, tag, `#${id} is a <${tag}>`);
    }
  }
  assert.match(elementWithId('atlas-power').html, /type="checkbox"/);
  assert.match(elementWithId('atlas-search').html, /type="search"/);
  assert.match(elementWithId('atlas-count').html, /aria-live="polite"/);
  assert.match(elementWithId('atlas-detail').html, /\bhidden\b/);
  assert.match(elementWithId('atlas-detail').html, /aria-labelledby="atlas-detail-title"/);
  assert.match(elementWithId('atlas-detail').html, /role="dialog"/);
  assert.match(elementWithId('atlas-error').html, /\bhidden\b/);
  const locator = template.slice(template.indexOf('id="atlas-locator"'), template.indexOf('</select>', template.indexOf('id="atlas-locator"')));
  assert.deepEqual([...locator.matchAll(/value="([^"]*)"/g)].map((m) => m[1]), ['any', 'official_boundary', 'polygon', 'point']);
  const sort = template.slice(template.indexOf('id="atlas-sort"'), template.indexOf('</select>', template.indexOf('id="atlas-sort"')));
  assert.deepEqual([...sort.matchAll(/value="([^"]*)"/g)].map((m) => m[1]), ['name', 'country', 'newest', 'oldest', 'projects']);
  for (const id of ['atlas-from', 'atlas-to']) {
    const start = template.indexOf(`id="${id}"`);
    const options = template.slice(start, template.indexOf('</select>', start));
    assert.deepEqual([...options.matchAll(/value="([^"]*)"/g)].map((m) => m[1]), [''], `${id} starts with only the empty option`);
  }
});

test('explorer.html ids are unique and it uses only documented tokens', () => {
  const ids = [...template.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(new Set(ids).size, ids.length);
  const allowed = new Set([
    'root', 'site_name', 'tagline', 'base_url', 'repository_url', 'issues_url', 'dataset.id', 'dataset.label',
    'dataset.release_status', 'dataset.checkpoint_date', 'dataset.checkpoint_year', 'dataset.lifecycle_reference_date',
    'dataset.status_window_days', 'dataset.window_start', 'dataset.window_end', 'counts.physical_sites', 'counts.projects',
    'counts.countries', 'counts.evidence', 'counts.non_us_sites', 'counts.official_boundary_projects',
    'counts.polygon_sites', 'counts.power_observation_projects', 'last_preview.label',
    'last_preview.counts.physical_sites', 'versions.count', 'build.commit_short', 'gates_table', 'status_legend'
  ]);
  const tokens = [...template.matchAll(/\{\{\{?\s*([^{}]+?)\s*\}?\}\}/g)].map((m) => m[1]);
  assert.ok(tokens.length > 0);
  for (const token of tokens) {
    assert.ok(allowed.has(token), `token {{${token}}} is documented`);
  }
  const stripped = template.replace(/\{\{\{?[^{}]+\}?\}\}/g, '');
  assert.ok(!stripped.includes('{{') && !stripped.includes('}}'), 'no stray braces');
});

test('explorer.html is CSP-safe and degrades without JavaScript', () => {
  assert.ok(!/\sstyle\s*=/i.test(template), 'no inline style attributes');
  assert.ok(!/\son[a-z]+\s*=/i.test(template), 'no inline event handlers');
  assert.ok(!/<script\b/i.test(template), 'no scripts in the template');
  assert.ok(!/<style\b/i.test(template), 'no style elements');
  assert.ok(!/javascript:/i.test(template));
  for (const href of [...template.matchAll(/\bhref="([^"]*)"/g)].map((m) => m[1])) {
    assert.ok(href.startsWith('{{root}}') || /^https?:\/\//.test(href), `relative-to-root or http(s): ${href}`);
  }
  const noscript = /<noscript>([\s\S]*?)<\/noscript>/i.exec(template);
  assert.ok(noscript, 'has a <noscript> block');
  for (const target of ['sites/', 'countries/', 'data/', 'api/']) {
    assert.ok(noscript[1].includes(`href="{{root}}${target}"`), `noscript links to ${target}`);
  }
  assert.match(elementWithId('atlas-app').html, /\bhidden\b/, 'the interactive app stays hidden without JS');
});

test('scripts parse, avoid HTML sinks and dynamic code', () => {
  assert.deepEqual(scripts.sort(), ['app.js', 'atlas-core.js', 'site-map.js', 'site.js']);
  for (const name of scripts) {
    const source = read(assetDir + name);
    assert.doesNotThrow(() => new Script(source, { filename: name }), `${name} parses`);
    assert.ok(!/\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML|document\.write|\beval\s*\(|new Function\s*\(/.test(source), `${name} has no HTML sinks`);
    assert.ok(!/setAttribute\(\s*['"]style['"]/.test(source), `${name} does not set style attributes`);
    assert.ok(!/\.src\s*=\s*['"]https?:|fetch\(\s*['"]https?:|\bimport\s*\(/.test(source), `${name} loads no script or data from other hosts`);
  }
  const app = read(assetDir + 'app.js');
  assert.match(app, /className: 'atlas-marker /);
  assert.match(app, /className: 'atlas-polygon /);
  assert.match(app, /L\.svg\(/);
  assert.match(app, /data-atlas-ready/);
});

// Leaflet writes strings given to these APIs with innerHTML (Tooltip/Popup
// _updateContent, divIcon html, the attribution control, layer-control
// names). Only DOM nodes and atlas-core constants may reach them.
const LEAFLET_HTML_APIS = /\.(?:bindTooltip|bindPopup|setTooltipContent|setPopupContent)\s*\(|\bdivIcon\s*\(|\bL\.popup\s*\(/;

function leafletSinkProblems(source) {
  const problems = [];
  if (LEAFLET_HTML_APIS.test(source)) {
    problems.push('uses a Leaflet HTML string API');
  }
  for (const match of source.matchAll(/\.setContent\(([^)]*)\)/g)) {
    if (!/^tooltipContent\(/.test(match[1].trim())) {
      problems.push(`setContent(${match[1]}) does not pass a DOM node from tooltipContent()`);
    }
  }
  for (const match of source.matchAll(/\.setPrefix\(([^)]*)\)/g)) {
    if (match[1].trim() !== "'<a href=\"https://leafletjs.com\">Leaflet</a>'") {
      problems.push(`setPrefix(${match[1]}) is not the constant Leaflet link`);
    }
  }
  for (const match of source.matchAll(/\.addAttribution\(([^;]*)\);/g)) {
    if (!/^Core\.dataCredit\(/.test(match[1].trim())) {
      problems.push(`addAttribution(${match[1]}) is not AtlasCore.dataCredit()`);
    }
  }
  return problems;
}

test('scripts give Leaflet\'s HTML string APIs only DOM nodes and constants', () => {
  for (const name of scripts) {
    assert.deepEqual(leafletSinkProblems(read(assetDir + name)), [], name);
  }
  // The guard itself catches the regressions it exists for.
  for (const bad of [
    'S.tooltip.setContent(site.name);', 'marker.bindTooltip(site.name);', 'marker.bindPopup(ev.title);',
    'L.divIcon({html: site.name});', 'map.attributionControl.addAttribution(ev.attribution);',
    "map.attributionControl.setPrefix(boot.site_name);", 'layer.setPopupContent(x);', 'L.popup().setLatLng(p);'
  ]) {
    assert.ok(leafletSinkProblems(bad).length > 0, bad);
  }
  assert.deepEqual(leafletSinkProblems('S.tooltip.setContent(tooltipContent(site));'), []);
  assert.deepEqual(leafletSinkProblems('map.attributionControl.addAttribution(Core.dataCredit(root));'), []);

  // Basemap names and attributions (layer control and attribution control
  // HTML) are literals in atlas-core.js, never values from data or the page.
  const core = read(assetDir + 'atlas-core.js');
  const block = core.slice(core.indexOf('var OSM_COPYRIGHT ='), core.indexOf('var CARTO_KEY_RE'));
  assert.ok(block.length > 500, 'basemap definitions found');
  for (const match of block.matchAll(/\battribution:\s*([^,\n}]+)/g)) {
    assert.match(match[1].trim(), /^(?:OSM_ATTRIBUTION|CARTO_ATTRIBUTION|EOX_ATTRIBUTION)$/, `attribution: ${match[1]}`);
  }
  for (const match of block.matchAll(/\bname:\s*('(?:[^'\\\n]|\\.)*'|[^,\n}]+)/g)) {
    assert.match(match[1].trim(), /^'[A-Za-z0-9 (),-]+'$/, `name: ${match[1]}`);
  }
  const constants = [...block.matchAll(/var (OSM_COPYRIGHT|OSM_ATTRIBUTION|CARTO_ATTRIBUTION|EOX_ATTRIBUTION) = ([\s\S]*?);\n/g)];
  assert.equal(constants.length, 4);
  for (const match of constants) {
    const code = match[2].replace(/'(?:[^'\\]|\\.)*'/g, "''");
    assert.match(code, /^(?:''|OSM_COPYRIGHT|\s|\+)+$/, `${match[1]} is built from string literals only`);
  }
});

test('no script requests CARTO tiles without an API key', () => {
  // The one allowed CARTO URL: built in basemapsFor(), always with ?key=.
  const keyed = /'https:\/\/\{s\}\.basemaps\.cartocdn\.com\/' \+ style\.style \+ '\/\{z\}\/\{x\}\/\{y\}\{r\}\.png\?key=' \+ encodeURIComponent\(key\)/g;
  const core = read(assetDir + 'atlas-core.js');
  assert.equal([...core.matchAll(keyed)].length, 1, 'atlas-core.js builds CARTO URLs with the key');
  for (const name of scripts) {
    const source = read(assetDir + name).replace(keyed, '');
    const literal = /cartocdn\.com/.exec(source);
    assert.equal(literal, null, `${name} has another CARTO tile URL; build it in basemapsFor() with the key`);
  }
  const Core = loadCore();
  assert.ok(Core.BASEMAPS.every((basemap) => !/cartocdn/.test(basemap.url)), 'no CARTO layer without a key');
});

test('site.css: no external resources; palette matches atlas-core; every status has a badge class', () => {
  assert.ok(!/@import/i.test(css));
  assert.ok(!/url\(\s*['"]?(?:https?:)?\/\//i.test(css), 'no external url()');
  const Core = loadCore();
  const tokens = { active: '--st-active', early: '--st-early', late: '--st-late', other: '--st-other' };
  for (const group of Core.STATUS_GROUPS.concat([Core.OTHER_GROUP])) {
    const match = new RegExp(`${tokens[group.id]}:\\s*(#[0-9a-fA-F]{6})`).exec(css);
    assert.ok(match, `${tokens[group.id]} is defined`);
    assert.equal(match[1].toLowerCase(), group.color.toLowerCase(), `${group.id} colour matches`);
    for (const code of group.codes) {
      assert.ok(css.includes(`.status-${code}`), `.status-${code} styled`);
    }
  }
  const { projects } = loadCurrentDatasetFeatures();
  for (const code of new Set(projects.map((row) => row.last_observed_physical_status))) {
    assert.ok(css.includes(`.status-${code}`), `current status ${code} has a badge colour`);
  }
  for (const cls of ['page', 'page-wide', 'lede', 'muted', 'small', 'mono', 'breadcrumbs', 'stats', 'stat', 'stat-value',
    'stat-label', 'badge', 'tag', 'btn', 'btn-primary', 'btn-small', 'card', 'cards', 'grid-2', 'kv', 'table-wrap',
    'data-table', 'num', 'callout', 'callout-warning', 'code', 'copy-btn', 'toc', 'download-list', 'checksum',
    'site-map', 'evidence-list', 'project', 'filter-input', 'sortable', 'hidden-noscript', 'external', 'anchor',
    'skip-link', 'site-header', 'brand', 'site-nav', 'preview-banner', 'site-footer', 'explorer']) {
    assert.ok(new RegExp(`\\.${cls}(?![\\w-])`).test(css), `.${cls} is styled`);
  }
});

test('favicon is a plain SVG', () => {
  const svg = read('site/static/favicon.svg');
  assert.match(svg.trim(), /^<svg [^>]*xmlns="http:\/\/www\.w3\.org\/2000\/svg"[\s\S]*<\/svg>$/);
  assert.ok(!/<script|on[a-z]+=|href=/i.test(svg));
});

// Published SRI values of the official Leaflet 1.9.4 release (leafletjs.com
// download page), pinned here independently of VENDOR.txt so that editing the
// vendored file and its VENDOR.txt row together still fails.
const UPSTREAM_LEAFLET_SRI = {
  'leaflet.js': 'sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=',
  'leaflet.css': 'sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY='
};

test('vendored leaflet.js and leaflet.css are byte-identical to upstream Leaflet 1.9.4', () => {
  for (const [file, sri] of Object.entries(UPSTREAM_LEAFLET_SRI)) {
    const data = readFileSync(new URL(assetDir + 'vendor/leaflet/' + file, repoRoot));
    assert.equal('sha256-' + createHash('sha256').update(data).digest('base64'), sri, file);
  }
});

test('vendored Leaflet matches the hashes recorded in VENDOR.txt', () => {
  const vendor = read(assetDir + 'vendor/leaflet/VENDOR.txt');
  assert.match(vendor, /Version:\s+1\.9\.4/);
  const rows = [...vendor.matchAll(/^([0-9a-f]{64})\s+(\d+)\s+(\S+)\s+sha256-/gm)];
  assert.equal(rows.length, 8);
  for (const [, hex, bytes, path] of rows) {
    const data = readFileSync(new URL(assetDir + 'vendor/leaflet/' + path, repoRoot));
    assert.equal(data.length, Number(bytes), `${path} size`);
    assert.equal(createHash('sha256').update(data).digest('hex'), hex, `${path} sha256`);
  }
  const leaflet = read(assetDir + 'vendor/leaflet/leaflet.js');
  assert.match(leaflet.slice(0, 200), /Leaflet 1\.9\.4/);
});

test('og-image.png is a 1200x630 PNG under 300 KB', () => {
  const png = readFileSync(new URL('site/static/og-image.png', repoRoot));
  assert.deepEqual([...png.subarray(0, 8)], [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  assert.equal(png.toString('ascii', 12, 16), 'IHDR');
  assert.equal(png.readUInt32BE(16), 1200);
  assert.equal(png.readUInt32BE(20), 630);
  assert.ok(png.length < 300 * 1024, `${png.length} bytes`);
});

test('explorer layout defaults keep results and sites visible', () => {
  assert.doesNotMatch(elementWithId('atlas-more').html, /\sopen\b/, 'additional filters start collapsed');
  const moreStart = template.indexOf('<details id="atlas-more"');
  const moreEnd = template.indexOf('</details>', moreStart);
  const more = template.slice(moreStart, moreEnd);
  for (const id of ['atlas-search', 'atlas-country']) {
    assert.ok(template.indexOf(`id="${id}"`) < moreStart, `${id} stays visible above additional filters`);
  }
  for (const id of ['atlas-status', 'atlas-locator', 'atlas-power', 'atlas-from', 'atlas-to']) {
    assert.ok(more.includes(`id="${id}"`), `${id} is an additional filter`);
  }
  assert.doesNotMatch(elementWithId('atlas-legend').html, /\sopen\b/, 'the legend starts folded (one-line key)');
  assert.match(elementWithId('atlas-legend-summary').html, /<summary\b/);
  assert.match(elementWithId('atlas-empty-reason').html, /\bhidden\b/);
  assert.match(elementWithId('atlas-notice').html, /\bhidden\b/);
  assert.match(elementWithId('atlas-list').html, /aria-label="[^"]*Arrow keys[^"]*"/, 'the list says how to move through it');
  assert.match(template, /class="atlas-kbd-hint"/);
  assert.match(template, /href="\{\{root\}\}about\/attribution\/"/, 'exports link to the licence and attribution page');
  assert.match(elementWithId('atlas-copy-embed').html, /\bhidden\b/, 'Embed appears only when the builder publishes embed/');
  const app = read(assetDir + 'app.js');
  assert.match(app, /minZoom: 0,/, 'phones can fit every site');
  assert.match(app, /E\.more\.open = !embedded && filtersOpen === '1'/, 'additional filters open only when requested');
  assert.match(app, /if \(moreFilterCount\(S\.state\) && E\.more/, 'shared links expand only the additional filters they use');
  assert.match(app, /setAttribute\('inert', ''\)/, 'the narrow-screen sheet is modal');
  assert.match(app, /document\.addEventListener\('keydown', trapSheetFocus\)/, 'Tab cycles inside the modal sheet');
});

test('app.js registers WebMCP tools only when supported, and never throws', () => {
  const app = read(assetDir + 'app.js');
  for (const name of ['search_datacenter_sites', 'get_datacenter_site', 'get_datacenter_dataset_info']) {
    assert.match(app, new RegExp(`name: '${name}'`));
  }
  assert.match(app, /typeof candidates\[i\]\.registerTool === 'function'/, 'feature-detects registerTool');
  assert.match(app, /annotations = \{ readOnlyHint: true, untrustedContentHint: true \}/);
  assert.match(app, /try \{\s*var result = lifecycle \? mc\.registerTool\(tool, \{ signal: lifecycle\.signal \}\) : mc\.registerTool\(tool\);\s*Promise\.resolve\(result\)\.catch\(function \(\) \{\}\);\s*\} catch \(error\) \{/);
  assert.match(app, /addEventListener\('pagehide', function \(\) \{ lifecycle\.abort\(\); \}, \{ once: true \}\)/);
});

test('site.css: table links keep their words; drawer key-value overrides win', () => {
  const linkRule = /\.data-table td a,\s*table\.download-list td a\s*\{([^}]*)\}/.exec(css);
  assert.ok(linkRule, 'table link rule exists');
  assert.match(linkRule[1], /overflow-wrap:\s*break-word/);
  assert.doesNotMatch(linkRule[1], /anywhere/, '"anywhere" shrinks link columns to one character');
  assert.match(css, /dl\.kv\.atlas-kv\s*\{[^}]*grid-template-columns/, 'drawer lists outrank dl.kv');
  assert.match(css, /--scroll-shadow:\s*rgba\(255, 255, 255/, 'dark mode has visible scroll shadows');
  assert.match(css, /\.leaflet-container \.leaflet-control-attribution a\s*\{[^}]*text-decoration:\s*underline/);
  assert.match(css, /\.atlas-tiles-dark\s*\{[^}]*filter:/, 'the keyless dark basemap is styled');
  assert.match(css, /\[data-basemap="osm-dark"\]/);
});

test('site-map.js colours like the explorer and leaves one-finger scrolling to the page', () => {
  const src = read(assetDir + 'site-map.js');
  assert.match(src, /Core\.prepareSite\(feature\)/);
  assert.match(src, /prepared\.primaryStatus/, 'same primary-status rule as the explorer');
  assert.match(src, /dragging: !\(L && L\.Browser && L\.Browser\.mobile\)/, 'no touch drag on phones');
  assert.match(src, /Core\.basemapsFor\(\{ cartoKey: container\.getAttribute\('data-carto-key'\) \}\)/);
  assert.match(src, /addAttribution\(Core\.dataCredit\(Core\.rootFromAssetSrc\(/, 'the data credit is permanent');
});
