// atlas-core.js against the current dataset (site/config.json current_dataset).
// Expectations are derived from the CSVs, never hard-coded, so a new
// checkpoint does not break these tests.
import test from 'node:test';
import assert from 'node:assert/strict';
import { loadCore, loadCurrentDatasetFeatures, parseCsv } from './csv-helper.mjs';

const Core = loadCore();
const data = loadCurrentDatasetFeatures();
const sites = Core.prepareSites({ type: 'FeatureCollection', features: data.features });

test('every dataset site becomes an explorer record with a location', () => {
  assert.equal(sites.length, data.sites.length);
  assert.equal(new Set(sites.map((site) => site.id)).size, sites.length);
  for (const site of sites) {
    assert.ok(site.hasLocation, `${site.id} has coordinates`);
    assert.ok(site.name.length > 0);
    assert.match(site.iso, /^[A-Z]{2}$/);
    assert.ok(site.statuses.length >= 1, `${site.id} has a status`);
    assert.ok(site.months.length >= 1, `${site.id} has a status month`);
    assert.ok(site.searchText.length > 0);
    if (site.isArea) {
      assert.ok(Core.geometryLatLngs(site.geometry), `${site.id} polygon converts`);
      assert.ok(Core.geometryBounds(site.geometry), `${site.id} polygon has bounds`);
    }
  }
});

test('context and facet counts agree with the CSVs', () => {
  const ctx = Core.buildContext(sites);
  const countries = new Set(data.sites.map((row) => row.country_iso_a2));
  assert.equal(ctx.countries.length, countries.size);
  const projectStatuses = new Set(data.projects.map((row) => row.last_observed_physical_status));
  assert.deepEqual(new Set(ctx.statuses), projectStatuses);
  const months = data.projects.map((row) => row.status_as_of.slice(0, 7)).sort();
  assert.equal(ctx.months[0], months[0]);
  assert.equal(ctx.months[ctx.months.length - 1], months[months.length - 1]);

  const facets = Core.facetCounts(sites, Core.defaultState());
  assert.equal(facets.total, data.sites.length);
  const countrySum = Object.values(facets.country).reduce((a, b) => a + b, 0);
  assert.equal(countrySum, data.sites.length);
  assert.equal(facets.locator.polygon + facets.locator.point, data.sites.length);
  const polygonRows = data.sites.filter((row) => row.geometry_type !== 'Point').length;
  assert.equal(facets.locator.polygon, polygonRows);
  const powerSites = new Set(data.projects
    .filter((row) => JSON.parse(row.power_observations_json).length > 0)
    .map((row) => row.site_id));
  assert.equal(facets.power, powerSites.size);
  const officialSites = new Set(data.projects
    .filter((row) => row.geometry_use_scope === 'official_boundary')
    .map((row) => row.site_id));
  assert.equal(facets.locator.official_boundary, officialSites.size);

  for (const country of ctx.countries) {
    const filtered = Core.filterSites(sites, Object.assign(Core.defaultState(), { country: country.iso }));
    assert.equal(filtered.length, country.count);
    assert.equal(filtered.length, facets.country[country.iso]);
  }
  for (const code of ctx.statuses) {
    const filtered = Core.filterSites(sites, Object.assign(Core.defaultState(), { status: [code] }));
    assert.equal(filtered.length, facets.status[code]);
  }
});

test('month filters partition the sites without losing any', () => {
  const ctx = Core.buildContext(sites);
  const seen = new Set();
  for (const month of ctx.months) {
    for (const site of Core.filterSites(sites, Object.assign(Core.defaultState(), { from: month, to: month }))) {
      seen.add(site.id);
    }
  }
  assert.equal(seen.size, sites.length);
});

test('search finds every site by its own name, and diacritics fold', () => {
  for (const site of sites) {
    const found = Core.filterSites(sites, Object.assign(Core.defaultState(), { q: site.name }));
    assert.ok(found.some((match) => match.id === site.id), `"${site.name}" finds itself`);
  }
  const accented = sites.find((site) => /[^\x00-\x7f]/.test(site.name) && Core.normalizeText(site.name) !== site.name.toLowerCase());
  if (accented) {
    const ascii = accented.name.normalize('NFKD').replace(/[\u0300-\u036f]/g, '');
    const found = Core.filterSites(sites, Object.assign(Core.defaultState(), { q: ascii }));
    assert.ok(found.some((match) => match.id === accented.id), `ASCII "${ascii}" finds "${accented.name}"`);
  }
});

test('every sort order is a permutation with a stable, total order', () => {
  for (const key of Core.SORTS) {
    const sorted = Core.sortSites(sites, key);
    assert.equal(sorted.length, sites.length);
    assert.equal(new Set(sorted.map((site) => site.id)).size, sites.length);
    const again = Core.sortSites(sorted.slice().reverse(), key);
    assert.deepEqual(again.map((site) => site.id), sorted.map((site) => site.id), `${key} is order-independent`);
  }
  const newest = Core.sortSites(sites, 'newest');
  for (let i = 1; i < newest.length; i++) {
    assert.ok(newest[i - 1].newest >= newest[i].newest);
  }
});

test('full CSV export round-trips every site', () => {
  const datasetId = data.config.current_dataset.split('/').pop();
  const text = Core.sitesToCsv(Core.sortSites(sites, 'name'), { datasetId });
  const rows = parseCsv(text);
  assert.equal(rows.length, sites.length + 1);
  const column = (name) => Core.CSV_COLUMNS.indexOf(name);
  const byId = new Map(data.sites.map((row) => [row.site_id, row]));
  const featureById = new Map(data.features.map((feature) => [feature.id, feature]));
  for (const row of rows.slice(1)) {
    assert.equal(row.length, Core.CSV_COLUMNS.length);
    const source = byId.get(row[0]);
    assert.ok(source, `${row[0]} exists in sites.csv`);
    assert.equal(row[column('name')], source.name);
    assert.equal(row[column('country')], source.country);
    assert.equal(Number(row[column('latitude')]), Number(source.latitude));
    assert.equal(Number(row[column('longitude')]), Number(source.longitude));
    assert.deepEqual(JSON.parse(row[column('statuses_json')]), JSON.parse(source.statuses_json));
    assert.equal(row[column('newest_status_as_of')], source.newest_status_as_of);
    assert.equal(row[column('project_count')], source.project_count);
    assert.deepEqual(JSON.parse(row[column('status_publishers_json')]),
      featureById.get(row[0]).properties.status_publishers, `${row[0]} publishers round-trip`);
    assert.equal(row[column('dataset_id')], datasetId);
  }
});

test('GeoJSON export preserves every feature', () => {
  const fc = JSON.parse(Core.sitesToGeoJSON(sites, { dataset: { id: 'x' }, query: '' }));
  assert.equal(fc.features.length, data.features.length);
  const polygonCount = fc.features.filter((f) => f.geometry.type !== 'Point').length;
  assert.equal(polygonCount, data.sites.filter((row) => row.geometry_type !== 'Point').length);
});

test('external links exist for every site and stay on the expected hosts', () => {
  for (const site of sites) {
    const links = Core.externalMapLinks(site.lat, site.lon);
    assert.equal(links.length, 4);
    for (const link of links) {
      const url = new URL(link.url);
      assert.equal(url.protocol, 'https:');
      assert.ok(['www.openstreetmap.org', 'www.google.com', 'www.bing.com', 'browser.dataspace.copernicus.eu'].includes(url.hostname));
    }
  }
});
