// Pure helpers of site/static/assets/site.js (static pages).
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { loadCore } from './csv-helper.mjs';

const require = createRequire(import.meta.url);
const Site = require('../static/assets/site.js');
const Core = loadCore();

test('site.js loads in node without touching a DOM', () => {
  assert.equal(typeof Site.init, 'function');
  assert.equal(typeof globalThis.document, 'undefined');
});

test('normalizeText matches AtlasCore.normalizeText', () => {
  const samples = [
    'Mäntsälä', 'São Paulo', 'Straße', 'Ærøskøbing', 'O’Brien', 'ＦＵＬＬ', '  a--b  ', '印西データセンター',
    'Valsts akciju sabiedrība “Latvijas Valsts radio un televīzijas centrs”', 'İstanbul', 'Łódź', '', null, 42
  ];
  for (const sample of samples) {
    assert.equal(Site.normalizeText(sample), Core.normalizeText(sample), JSON.stringify(sample));
  }
});

test('rowMatches requires every query word', () => {
  const row = Site.normalizeText('Frankfurt Campus | Germany | Under construction | 2026-06-01');
  assert.ok(Site.rowMatches(row, ''));
  assert.ok(Site.rowMatches(row, 'frank'));
  assert.ok(Site.rowMatches(row, 'germany under'));
  assert.ok(Site.rowMatches(row, '2026 06'));
  assert.ok(!Site.rowMatches(row, 'germany shell'));
});

test('parseNumber reads counts, decimals, signs and file sizes', () => {
  assert.equal(Site.parseNumber('1,234'), 1234);
  assert.equal(Site.parseNumber(' 5.28 MW'), 5.28);
  assert.equal(Site.parseNumber('−3.5'), -3.5);
  assert.equal(Site.parseNumber('12 KB'), 12000);
  assert.equal(Site.parseNumber('1.5 MiB'), 1.5 * 1048576);
  assert.equal(Site.parseNumber('897'), 897);
  assert.equal(Site.parseNumber('n/a'), null);
  assert.equal(Site.parseNumber(''), null);
});

test('sortEntries is stable and keeps empty cells last in both directions', () => {
  const entries = [
    { index: 0, key: Site.sortKey('10', true) },
    { index: 1, key: Site.sortKey('—', true) },
    { index: 2, key: Site.sortKey('2', true) },
    { index: 3, key: Site.sortKey('10', true) },
    { index: 4, key: Site.sortKey('', true) }
  ];
  assert.deepEqual(Site.sortEntries(entries, false).map((e) => e.index), [2, 0, 3, 1, 4]);
  assert.deepEqual(Site.sortEntries(entries, true).map((e) => e.index), [0, 3, 2, 1, 4]);
  const text = ['Zeta', 'alpha', 'Beta 10', 'Beta 9'].map((value, index) => ({ index, key: Site.sortKey(value, false) }));
  assert.deepEqual(Site.sortEntries(text, false).map((e) => e.index), [1, 3, 2, 0]);
  const dates = ['2026-08-01', '2026-05-26', '2026-07-15'].map((value, index) => ({ index, key: Site.sortKey(value, false) }));
  assert.deepEqual(Site.sortEntries(dates, true).map((e) => e.index), [0, 2, 1]);
});
