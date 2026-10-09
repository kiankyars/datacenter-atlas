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
    'dataset.status_window_days', 'dataset.window_start', 'counts.physical_sites', 'counts.projects',
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
