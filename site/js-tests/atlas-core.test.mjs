// Unit tests for site/static/assets/atlas-core.js (run: node --test site/js-tests/).
import test from 'node:test';
import assert from 'node:assert/strict';
import { loadCore, parseCsv } from './csv-helper.mjs';

const Core = loadCore();

function feature(props, geometry) {
  return {
    type: 'Feature',
    id: props.site_id,
    geometry: geometry || { type: 'Point', coordinates: [props.longitude, props.latitude] },
    properties: props
  };
}

function baseProps(overrides) {
  return Object.assign({
    site_id: 'vcc-site-a',
    name: 'Alpha Campus',
    country: 'Germany',
    country_iso_a2: 'DE',
    latitude: 50.1,
    longitude: 8.6,
    geometry_type: 'Point',
    official_boundary: false,
    locator_scopes: ['campus_locator'],
    statuses: ['under_construction'],
    newest_status_as_of: '2026-06-01',
    oldest_status_as_of: '2026-06-01',
    project_count: 1,
    projects: [{ project_id: 'p-a', name: 'Alpha Phase 1', status: 'under_construction', status_as_of: '2026-06-01' }],
    status_publishers: ['Alpha GmbH'],
    power_observations: [],
    verification_posture: 'recent_authoritative_physical_observation_plus_reviewed_site_locator',
    independent_imagery_verification: false,
    url: 'https://example.org/atlas/sites/vcc-site-a/',
    api_url: 'https://example.org/atlas/api/v1/sites/vcc-site-a.json'
  }, overrides || {});
}

const square = {
  type: 'Polygon',
  coordinates: [[[10, 50], [10.01, 50], [10.01, 50.01], [10, 50.01], [10, 50]]]
};

function fixtureSites() {
  return Core.prepareSites({
    type: 'FeatureCollection',
    features: [
      feature(baseProps()),
      feature(baseProps({
        site_id: 'vcc-site-b',
        name: 'Mäntsälä Data Centre',
        country: 'Finland',
        country_iso_a2: 'FI',
        latitude: 60.63,
        longitude: 25.32,
        statuses: ['site_preparation'],
        newest_status_as_of: '2026-07-15',
        oldest_status_as_of: '2026-07-15',
        projects: [{ project_id: 'p-b', name: 'Verne Mäntsälä first 70 MW', status: 'site_preparation', status_as_of: '2026-07-15' }],
        status_publishers: ['Verne'],
        power_observations: [{ project_id: 'p-b', metric: 'critical_it_mw', stage: 'planned', low: 70, base: 70, high: 70, unit: 'MW', as_of_date: '2026-07-15' }]
      })),
      feature(baseProps({
        site_id: 'vcc-site-c',
        name: 'Jakarta Campus',
        country: 'Indonesia',
        country_iso_a2: 'ID',
        latitude: 50.005,
        longitude: 10.005,
        geometry_type: 'Polygon',
        official_boundary: true,
        statuses: ['shell', 'under_construction'],
        newest_status_as_of: '2026-08-10',
        oldest_status_as_of: '2026-05-26',
        project_count: 3,
        projects: [
          { project_id: 'p-c1', name: 'Jakarta Phase 1', status: 'under_construction', status_as_of: '2026-05-26' },
          { project_id: 'p-c2', name: 'Jakarta Phase 2', status: 'shell', status_as_of: '2026-08-10' },
          { project_id: 'p-c3', name: 'Jakarta Phase 3', status: 'under_construction', status_as_of: '2026-08-10' }
        ],
        status_publishers: ['STT GDC', 'Ministry']
      }), square),
      feature(baseProps({
        site_id: 'vcc-site-d',
        name: 'alpha two',
        newest_status_as_of: '2026-08-01',
        oldest_status_as_of: '2026-08-01',
        projects: [{ project_id: 'p-d', name: 'Alpha Two', status: 'under_construction', status_as_of: '2026-08-01' }]
      }))
    ]
  });
}

test('module exposes a frozen API and does not need a DOM', () => {
  assert.equal(typeof Core.prepareSites, 'function');
  assert.ok(Object.isFrozen(Core));
  assert.equal(typeof globalThis.window, 'undefined');
});

test('status groups: three validated Okabe-Ito hues plus a neutral fallback', () => {
  assert.deepEqual(Core.STATUS_GROUPS.map((group) => group.color), ['#0072B2', '#D55E00', '#009E73']);
  assert.equal(Core.statusGroup('under_construction').id, 'active');
  assert.equal(Core.statusGroup('foundations').id, 'active');
  assert.equal(Core.statusGroup('mep_electrical').id, 'active');
  assert.equal(Core.statusGroup('announced').id, 'early');
  assert.equal(Core.statusGroup('permitted').id, 'early');
  assert.equal(Core.statusGroup('completed').id, 'late');
  assert.equal(Core.statusGroup('operational').id, 'late');
  assert.equal(Core.statusGroup('no_such_code').id, 'other');
  assert.deepEqual(
    Core.sortStatusCodes(['shell', 'zzz_new', 'under_construction', 'foundations', 'site_preparation', 'shell']),
    ['under_construction', 'site_preparation', 'foundations', 'shell', 'zzz_new']
  );
});

test('planned and retained sites remain separately filterable with stable URLs', () => {
  const codes = ['announced', 'permitted', 'under_construction', 'completed', 'operational'];
  const sites = Core.prepareSites({ type: 'FeatureCollection', features: codes.map((status) =>
    feature(baseProps({
      site_id: `site-${status}`, statuses: [status],
      projects: [{ project_id: `project-${status}`, status, status_as_of: '2026-09-01' }]
    }))) });
  const ctx = Core.buildContext(sites);
  for (const status of codes) {
    const state = Core.normalizeState({ status: [status] }, ctx);
    assert.deepEqual(Core.filterSites(sites, state).map((site) => site.id), [`site-${status}`]);
    assert.equal(Core.serializeState(state), `?status=${status}`);
  }
  assert.notEqual(Core.statusLabel('completed'), Core.statusLabel('operational'));
});

test('vocabulary labels: bootstrap first, then built-in, then humanized code', () => {
  const vocab = { statuses: { shell: { label: 'Building shell', description: 'Envelope' } } };
  assert.equal(Core.statusLabel('shell', vocab), 'Building shell');
  assert.equal(Core.vocabDescription(vocab, 'statuses', 'shell'), 'Envelope');
  assert.equal(Core.statusLabel('mep_electrical', vocab), 'MEP / electrical');
  assert.equal(Core.statusLabel('brand_new_stage', vocab), 'Brand new stage');
  assert.equal(Core.vocabLabel(null, 'evidence_roles', 'typed_metric:critical_it_mw'), 'Typed metric: critical it mw');
  assert.equal(Core.vocabLabel({}, 'statuses', ''), '');
  assert.equal(Core.vocabLabel({ statuses: { __proto__: { label: 'x' } } }, 'statuses', 'toString'), 'ToString');
});

test('normalizeText folds case, diacritics, apostrophes and punctuation', () => {
  assert.equal(Core.normalizeText('Mäntsälä'), 'mantsala');
  assert.equal(Core.normalizeText('  São-Paulo   (Brasil) '), 'sao paulo brasil');
  assert.equal(Core.normalizeText('Straße Ærøskøbing'), 'strasse aeroskobing');
  assert.equal(Core.normalizeText('Latvijas “Valsts” centrs'), 'latvijas valsts centrs');
  assert.equal(Core.normalizeText('O’Brien’s'), 'obriens');
  assert.equal(Core.normalizeText('ＦＵＬＬ width'), 'full width');
  assert.equal(Core.normalizeText(null), '');
  assert.equal(Core.normalizeText(42), '42');
});

test('matchesTokens: word-prefix for Latin, substring for CJK', () => {
  const text = Core.buildSearchText(['Frankfurt Campus', 'Germany', 'DE', ['Phase 2'], ['Example AG']]);
  assert.ok(Core.matchesTokens(text, Core.tokenize('frank')));
  assert.ok(Core.matchesTokens(text, Core.tokenize('campus germ')));
  assert.ok(!Core.matchesTokens(text, Core.tokenize('furt')));
  assert.ok(!Core.matchesTokens(text, Core.tokenize('us')));
  assert.ok(Core.matchesTokens(text, Core.tokenize('de')));
  assert.ok(Core.matchesTokens(text, []));
  const cjk = Core.buildSearchText(['印西データセンター']);
  assert.ok(Core.matchesTokens(cjk, Core.tokenize('データ')));
});

test('prepareSite builds explorer records and tolerates missing fields', () => {
  const sites = fixtureSites();
  assert.equal(sites.length, 4);
  const [alpha, mantsala, jakarta] = sites;
  assert.equal(alpha.id, 'vcc-site-a');
  assert.equal(alpha.iso, 'DE');
  assert.equal(alpha.hasLocation, true);
  assert.equal(alpha.isArea, false);
  assert.deepEqual(alpha.months, ['2026-06']);
  assert.ok(alpha.searchText.includes('alpha gmbh'));
  assert.ok(alpha.searchText.includes('vcc site a'));
  assert.equal(mantsala.hasPower, true);
  assert.ok(Core.matchesTokens(mantsala.searchText, Core.tokenize('mantsala verne')));
  assert.equal(jakarta.isArea, true);
  assert.equal(jakarta.officialBoundary, true);
  assert.deepEqual(jakarta.statuses, ['under_construction', 'shell']);
  assert.equal(jakarta.primaryStatus, 'shell', 'newest project, specific stage beats generic');
  assert.deepEqual(jakarta.months, ['2026-05', '2026-08']);

  const sparse = Core.prepareSite({ type: 'Feature', id: 'x1', geometry: { type: 'Point', coordinates: [1, 2] }, properties: {} });
  assert.equal(sparse.name, 'x1');
  assert.equal(sparse.lat, 2);
  assert.equal(sparse.lon, 1);
  assert.deepEqual(sparse.statuses, []);
  assert.equal(sparse.projectCount, 0);

  const noLocation = Core.prepareSite({ type: 'Feature', id: 'x2', geometry: null, properties: { latitude: 'abc', longitude: 500 } });
  assert.equal(noLocation.hasLocation, false);
  assert.equal(noLocation.lat, null);

  assert.equal(Core.prepareSite(null), null);
  assert.equal(Core.prepareSite({ properties: {} }), null);
  const dupes = Core.prepareSites({ features: [feature(baseProps()), feature(baseProps())] });
  assert.equal(dupes.length, 1);
});

test('buildContext lists countries by name, statuses by group, months contiguously', () => {
  const ctx = Core.buildContext(fixtureSites());
  assert.deepEqual(ctx.countries.map((c) => [c.iso, c.count]), [['FI', 1], ['DE', 2], ['ID', 1]]);
  assert.deepEqual(ctx.countryCodes, ['DE', 'FI', 'ID']);
  assert.deepEqual(ctx.statuses, ['under_construction', 'site_preparation', 'shell']);
  assert.deepEqual(ctx.months, ['2026-05', '2026-06', '2026-07', '2026-08']);
});

test('filterSites applies every filter with AND semantics', () => {
  const sites = fixtureSites();
  const ids = (state) => Core.filterSites(sites, Object.assign(Core.defaultState(), state)).map((s) => s.id);
  assert.deepEqual(ids({}), ['vcc-site-a', 'vcc-site-b', 'vcc-site-c', 'vcc-site-d']);
  assert.deepEqual(ids({ q: 'alpha' }), ['vcc-site-a', 'vcc-site-d']);
  assert.deepEqual(ids({ q: 'ALPHA two' }), ['vcc-site-d']);
  assert.deepEqual(ids({ q: 'mantsälä' }), ['vcc-site-b']);
  assert.deepEqual(ids({ country: 'DE' }), ['vcc-site-a', 'vcc-site-d']);
  assert.deepEqual(ids({ status: ['shell'] }), ['vcc-site-c']);
  assert.deepEqual(ids({ status: ['shell', 'site_preparation'] }), ['vcc-site-b', 'vcc-site-c']);
  assert.deepEqual(ids({ locator: 'official_boundary' }), ['vcc-site-c']);
  assert.deepEqual(ids({ locator: 'polygon' }), ['vcc-site-c']);
  assert.deepEqual(ids({ locator: 'point' }), ['vcc-site-a', 'vcc-site-b', 'vcc-site-d']);
  assert.deepEqual(ids({ power: true }), ['vcc-site-b']);
  assert.deepEqual(ids({ from: '2026-07' }), ['vcc-site-b', 'vcc-site-c', 'vcc-site-d']);
  assert.deepEqual(ids({ to: '2026-05' }), ['vcc-site-c']);
  assert.deepEqual(ids({ from: '2026-06', to: '2026-06' }), ['vcc-site-a']);
  assert.deepEqual(ids({ country: 'DE', q: 'campus' }), ['vcc-site-a']);
  assert.deepEqual(ids({ country: 'FR' }), []);
});

test('facetCounts counts each facet against the other filters only', () => {
  const sites = fixtureSites();
  const all = Core.facetCounts(sites, Core.defaultState());
  assert.equal(all.total, 4);
  assert.deepEqual({ ...all.country }, { DE: 2, FI: 1, ID: 1 });
  assert.deepEqual({ ...all.status }, { under_construction: 3, site_preparation: 1, shell: 1 });
  assert.deepEqual(all.locator, { any: 4, official_boundary: 1, polygon: 1, point: 3 });
  assert.equal(all.power, 1);

  const de = Core.facetCounts(sites, Object.assign(Core.defaultState(), { country: 'DE' }));
  assert.equal(de.total, 2);
  assert.deepEqual({ ...de.country }, { DE: 2, FI: 1, ID: 1 }, 'own facet ignores its own selection');
  assert.deepEqual({ ...de.status }, { under_construction: 2 });
  assert.equal(de.power, 0);
});

test('sortSites orders by each key with deterministic tie-breaks', () => {
  const sites = fixtureSites();
  const order = (key) => Core.sortSites(sites, key).map((s) => s.id);
  assert.deepEqual(order('name'), ['vcc-site-a', 'vcc-site-d', 'vcc-site-c', 'vcc-site-b']);
  assert.deepEqual(order('country'), ['vcc-site-b', 'vcc-site-a', 'vcc-site-d', 'vcc-site-c']);
  assert.deepEqual(order('newest'), ['vcc-site-c', 'vcc-site-d', 'vcc-site-b', 'vcc-site-a']);
  assert.deepEqual(order('oldest'), ['vcc-site-c', 'vcc-site-a', 'vcc-site-b', 'vcc-site-d']);
  assert.deepEqual(order('projects'), ['vcc-site-c', 'vcc-site-a', 'vcc-site-d', 'vcc-site-b']);
  assert.deepEqual(order('bogus'), order('name'));
  const original = sites.map((s) => s.id);
  Core.sortSites(sites, 'newest');
  assert.deepEqual(sites.map((s) => s.id), original, 'input array is not mutated');
  const missing = Core.sortSites([{ id: 'b', name: 'B', newest: '', oldest: '' }, { id: 'a', name: 'A', newest: '2026-01-01', oldest: '2026-01-01' }], 'oldest');
  assert.deepEqual(missing.map((s) => s.id), ['a', 'b'], 'missing dates sort last');
});

test('URL state round-trips through serializeState and parseQuery', () => {
  const state = {
    q: 'Frankfurt am Main & co',
    country: 'DE',
    status: ['under_construction', 'shell'],
    locator: 'polygon',
    power: true,
    from: '2026-05',
    to: '2026-08',
    sort: 'newest'
  };
  const query = Core.serializeState(state);
  assert.equal(query, '?q=Frankfurt+am+Main+%26+co&country=DE&status=under_construction,shell&locator=polygon&power=1&from=2026-05&to=2026-08&sort=newest');
  assert.deepEqual(Core.parseQuery(query), state);
  assert.equal(Core.serializeState(Core.defaultState()), '');
  assert.deepEqual(Core.parseQuery(''), Core.defaultState());
  assert.deepEqual(Core.parseQuery('?q=a%2Bb+c'), Object.assign(Core.defaultState(), { q: 'a+b c' }));
});

test('parseQuery drops malformed values', () => {
  const parsed = Core.parseQuery('?country=Germany&status=SHELL,%3Cscript%3E,,shell&locator=all&power=yes&from=2026-13&to=26-08&sort=random&q=' + 'x'.repeat(500));
  assert.equal(parsed.country, '');
  assert.deepEqual(parsed.status, ['shell']);
  assert.equal(parsed.locator, 'any');
  assert.equal(parsed.power, false);
  assert.equal(parsed.from, '');
  assert.equal(parsed.to, '');
  assert.equal(parsed.sort, 'name');
  assert.equal(parsed.q.length, 200);
  assert.deepEqual(Core.parseQuery('?status=shell&status=foundations').status, ['shell', 'foundations']);
  assert.equal(Core.parseQuery('?country=de').country, 'DE');
});

test('hash state carries only a plausible site id', () => {
  assert.equal(Core.parseHash('#site=vcc-site-52b1e1c3038357306a39'), 'vcc-site-52b1e1c3038357306a39');
  assert.equal(Core.parseHash('site=abc'), 'abc');
  assert.equal(Core.parseHash('#site=%3Cimg%3E'), '');
  assert.equal(Core.parseHash('#map=3/1/2'), '');
  assert.equal(Core.parseHash(''), '');
  assert.equal(Core.buildHash('vcc-site-x'), '#site=vcc-site-x');
  assert.equal(Core.buildHash(''), '');
});

test('normalizeState canonicalises a state without changing what it matches', () => {
  const sites = fixtureSites();
  const ctx = Core.buildContext(sites);
  const state = Core.normalizeState(Object.assign(Core.defaultState(), {
    country: 'de', status: ['shell', 'operational', 'under_construction', 'BAD CODE'], from: '2026-08', to: '2026-06'
  }), ctx);
  assert.equal(state.country, 'DE');
  assert.deepEqual(state.status, ['under_construction', 'shell', 'operational'],
    'known statuses in context order, then codes this dataset lacks; malformed codes dropped');
  assert.equal(state.from, '2026-06', 'a reversed range is swapped');
  assert.equal(state.to, '2026-08');
  const wide = Core.normalizeState(Object.assign(Core.defaultState(), { from: '2025-01', to: '2030-01' }), ctx);
  assert.equal(wide.from, '', 'a bound before the first month excludes nothing and is dropped');
  assert.equal(wide.to, '', 'a bound after the last month excludes nothing and is dropped');
  const inside = Core.normalizeState(Object.assign(Core.defaultState(), { from: '2026-05', to: '2026-08' }), ctx);
  assert.equal(inside.from, '2026-05', 'boundary months are kept as chosen');
  assert.equal(inside.to, '2026-08');
  assert.deepEqual(Core.normalizeState(null, null), Core.defaultState());

  // Values that match nothing stay, so a shared link that matches nothing shows nothing.
  const none = (extra) => Core.normalizeState(Object.assign(Core.defaultState(), extra), ctx);
  const later = none({ from: '2026-09' });
  assert.equal(later.from, '2026-09');
  assert.deepEqual(Core.filterSites(sites, later), []);
  const earlier = none({ to: '2026-04' });
  assert.equal(earlier.to, '2026-04');
  assert.deepEqual(Core.filterSites(sites, earlier), []);
  const country = none({ country: 'XX' });
  assert.equal(country.country, 'XX');
  assert.deepEqual(Core.filterSites(sites, country), []);
  const status = none({ status: ['operational'] });
  assert.deepEqual(status.status, ['operational']);
  assert.deepEqual(Core.filterSites(sites, status), []);
  assert.equal(Core.serializeState(status), '?status=operational', 'the URL keeps what was asked for');
});

test('unmatchedFilters names the values this dataset does not contain', () => {
  const ctx = Core.buildContext(fixtureSites());
  const state = Core.normalizeState(Object.assign(Core.defaultState(), {
    country: 'XX', status: ['shell', 'operational'], from: '2026-09', to: '2026-10'
  }), ctx);
  assert.deepEqual(Core.unmatchedFilters(state, ctx), { country: 'XX', statuses: ['operational'], from: '2026-09', to: '' });
  assert.deepEqual(Core.unmatchedFilters(Object.assign(Core.defaultState(), { to: '2026-04' }), ctx).to, '2026-04');
  assert.deepEqual(Core.unmatchedFilters(Core.defaultState(), ctx), { country: '', statuses: [], from: '', to: '' });
});

test('status and month filters must be met by the same project', () => {
  const twoPhase = Core.prepareSites({
    features: [feature(baseProps({
      site_id: 'vcc-site-two',
      name: 'Two-phase campus',
      statuses: ['shell', 'under_construction'],
      newest_status_as_of: '2026-08-10',
      oldest_status_as_of: '2026-05-25',
      project_count: 2,
      projects: [
        { project_id: 'p-1', name: 'Phase A', status: 'shell', status_as_of: '2026-05-25' },
        { project_id: 'p-2', name: 'Phase B', status: 'under_construction', status_as_of: '2026-08-10' }
      ]
    }))]
  });
  const ids = (state) => Core.filterSites(twoPhase, Object.assign(Core.defaultState(), state)).map((s) => s.id);
  assert.deepEqual(ids({ status: ['shell'], from: '2026-08', to: '2026-08' }), [], 'shell was observed in May, not August');
  assert.deepEqual(ids({ status: ['shell'], from: '2026-05', to: '2026-05' }), ['vcc-site-two']);
  assert.deepEqual(ids({ status: ['under_construction'], from: '2026-08' }), ['vcc-site-two']);
  assert.deepEqual(ids({ status: ['shell'] }), ['vcc-site-two'], 'without a month range any project counts');
  assert.deepEqual(ids({ from: '2026-08' }), ['vcc-site-two'], 'without a status any project date counts');
  const facets = Core.facetCounts(twoPhase, Object.assign(Core.defaultState(), { from: '2026-08', to: '2026-08' }));
  assert.deepEqual({ ...facets.status }, { under_construction: 1 }, 'status facet counts only statuses observed in range');
  assert.deepEqual(Core.statusesInRange(twoPhase[0], '', ''), ['under_construction', 'shell']);
});

test('activeFilterCount ignores sort and blank search', () => {
  assert.equal(Core.activeFilterCount(Core.defaultState()), 0);
  assert.equal(Core.activeFilterCount(Object.assign(Core.defaultState(), { q: '  ', sort: 'newest' })), 0);
  assert.equal(Core.activeFilterCount(Object.assign(Core.defaultState(), {
    q: 'x', country: 'DE', status: ['shell'], locator: 'point', power: true, from: '2026-06'
  })), 6);
});

test('month helpers', () => {
  assert.deepEqual(Core.monthRange('2025-11', '2026-02'), ['2025-11', '2025-12', '2026-01', '2026-02']);
  assert.deepEqual(Core.monthRange('2026-02', '2026-01'), []);
  assert.deepEqual(Core.monthRange('2026-02', '2026-02'), ['2026-02']);
  assert.deepEqual(Core.monthRange('bad', '2026-01'), []);
  assert.equal(Core.monthOf('2026-08-20T10:00:00Z'), '2026-08');
  assert.equal(Core.monthOf('20-08-2026'), '');
  assert.equal(Core.formatMonth('2026-05'), 'May 2026');
  assert.equal(Core.formatMonth('2026-5'), '');
  assert.equal(Core.isoDateMinusDays('2026-08-20', 90), '2026-05-22');
  assert.equal(Core.isoDateMinusDays('2024-03-01', 1), '2024-02-29');
  assert.equal(Core.isoDateMinusDays('nope', 1), '');
});

test('csvField: RFC 4180 quoting and formula neutralisation for text only', () => {
  assert.equal(Core.csvField('plain'), 'plain');
  assert.equal(Core.csvField('a,b'), '"a,b"');
  assert.equal(Core.csvField('say "hi"'), '"say ""hi"""');
  assert.equal(Core.csvField('line\nbreak'), '"line\nbreak"');
  assert.equal(Core.csvField('cr\rhere'), '"cr\rhere"');
  assert.equal(Core.csvField('=HYPERLINK("x")'), '"\'=HYPERLINK(""x"")"');
  assert.equal(Core.csvField('+1 555'), "'+1 555");
  assert.equal(Core.csvField('-Minus'), "'-Minus");
  assert.equal(Core.csvField('@SUM(A1)'), "'@SUM(A1)");
  assert.equal(Core.csvField('\tTab'), "'\tTab");
  assert.equal(Core.csvField('\rCR'), '"\'\rCR"');
  assert.equal(Core.csvField('a=b'), 'a=b');
  assert.equal(Core.csvField(-77.5), '-77.5', 'numbers are never neutralised');
  assert.equal(Core.csvField(18.6467083333), '18.6467083333');
  assert.equal(Core.csvField(0), '0');
  assert.equal(Core.csvField(NaN), '');
  assert.equal(Core.csvField(true), 'true');
  assert.equal(Core.csvField(false), 'false');
  assert.equal(Core.csvField(null), '');
  assert.equal(Core.csvField(undefined), '');
});

test('sitesToCsv writes the documented columns and parses back exactly', () => {
  const sites = fixtureSites();
  sites[0].name = '=cmd|"/c calc"!A1, "quoted"\nnext line';
  sites[2].publishers = ['STT GDC; joint announcement', 'Ministry, Jakarta'];
  sites[2].properties.geometry_licenses = ['ODbL-1.0'];
  const text = Core.sitesToCsv(sites, { datasetId: '2026-08-20-v0.18-draft' });
  assert.ok(text.endsWith('\r\n'));
  assert.ok(!text.includes('\n\n'));
  const rows = parseCsv(text);
  assert.deepEqual(rows[0], [
    'site_id', 'name', 'country', 'country_iso_a2', 'latitude', 'longitude', 'statuses_json',
    'newest_status_as_of', 'oldest_status_as_of', 'project_count', 'official_boundary', 'geometry_type',
    'status_publishers_json', 'geometry_licenses_json', 'url', 'api_url', 'dataset_id'
  ]);
  assert.deepEqual(rows[0], Core.CSV_COLUMNS);
  const col = (name) => Core.CSV_COLUMNS.indexOf(name);
  assert.equal(rows.length, sites.length + 1);
  assert.equal(rows[1][col('name')], '\'=cmd|"/c calc"!A1, "quoted"\nnext line');
  assert.equal(rows[1][col('latitude')], '50.1');
  assert.equal(rows[1][col('longitude')], '8.6');
  const jakarta = rows.find((row) => row[0] === 'vcc-site-c');
  assert.equal(jakarta[col('statuses_json')], '["shell","under_construction"]', 'compact JSON, dataset order');
  assert.equal(jakarta[col('project_count')], '3');
  assert.equal(jakarta[col('official_boundary')], 'true');
  assert.equal(jakarta[col('geometry_type')], 'Polygon');
  assert.deepEqual(JSON.parse(jakarta[col('status_publishers_json')]), ['STT GDC; joint announcement', 'Ministry, Jakarta'],
    'publisher names with separators survive the round trip');
  assert.equal(jakarta[col('geometry_licenses_json')], '["ODbL-1.0"]');
  assert.equal(rows[1][col('geometry_licenses_json')], '', 'no geometry_licenses in the data: unknown, not "[]"');
  for (const row of rows) {
    assert.equal(row.length, 17);
  }
  assert.deepEqual(rows.slice(1).map((row) => row[col('dataset_id')]), sites.map(() => '2026-08-20-v0.18-draft'));
  assert.equal(Core.sitesToCsv([]), Core.CSV_COLUMNS.join(',') + '\r\n');
  assert.equal(parseCsv(Core.sitesToCsv(sites.slice(0, 1)))[1][col('dataset_id')], '', 'dataset_id is empty without meta');
});

test('licence links: known codes only; OpenStreetMap credit detection', () => {
  assert.equal(Core.licenseUrl('ODbL-1.0'), 'https://opendatacommons.org/licenses/odbl/1-0/');
  assert.equal(Core.licenseUrl(' CC-BY-4.0 '), 'https://creativecommons.org/licenses/by/4.0/');
  assert.equal(Core.licenseUrl('CC-BY-SA-2.0'), 'https://creativecommons.org/licenses/by-sa/2.0/');
  for (const code of ['all-rights-reserved', 'toString', '__proto__', '', null, 'CC-BY-version-unspecified']) {
    assert.equal(Core.licenseUrl(code), '', String(code));
  }
  assert.ok(Core.isOpenStreetMapCredit('ODbL-1.0', ''));
  assert.ok(Core.isOpenStreetMapCredit('', '\u00a9 OpenStreetMap contributors'));
  assert.ok(!Core.isOpenStreetMapCredit('CC-BY-4.0', 'City of Example'));
  assert.equal(Core.OSM_COPYRIGHT_URL, 'https://www.openstreetmap.org/copyright');
});

test('embedSnippet builds an escaped iframe for http(s) views only', () => {
  const snippet = Core.embedSnippet('https://example.org/atlas/embed/?country=DE&status=shell', 'Atlas "map" <x>');
  assert.equal(snippet, '<iframe src="https://example.org/atlas/embed/?country=DE&amp;status=shell" ' +
    'title="Atlas &quot;map&quot; &lt;x&gt;" width="100%" height="560" style="border:0" loading="lazy" ' +
    'referrerpolicy="strict-origin-when-cross-origin"></iframe>');
  assert.match(Core.embedSnippet('https://example.org/embed/'), /title="Data Center Atlas map"/);
  for (const bad of ['javascript:alert(1)', '/embed/', '', null, 'data:text/html,x']) {
    assert.equal(Core.embedSnippet(bad), '', String(bad));
  }
});

test('rootFromAssetSrc reads the relative root from a script src', () => {
  assert.equal(Core.rootFromAssetSrc('../../assets/site-map.js'), '../../');
  assert.equal(Core.rootFromAssetSrc('./assets/app.js'), './');
  assert.equal(Core.rootFromAssetSrc('assets/app.js'), './');
  assert.equal(Core.rootFromAssetSrc('../assets/site-map.js?v=2'), '../');
  for (const src of ['https://evil.example/assets/site-map.js', '/assets/site-map.js', '../x/assets/a.js', '', null]) {
    assert.equal(Core.rootFromAssetSrc(src), '', String(src));
  }
});

test('sitesToGeoJSON keeps geometry, original summaries and the terms of use', () => {
  const sites = fixtureSites();
  const terms = Core.exportTerms(null, {
    site_name: 'Data Center Atlas', base_url: 'https://example.org/atlas/', dataset: { id: 'd1' }
  });
  const text = Core.sitesToGeoJSON(sites.slice(1, 3), Object.assign({
    dataset: { id: 'd1' },
    query: '?status=shell',
    source_url: 'https://example.org/atlas/api/v1/sites.geojson',
    view_url: 'https://example.org/atlas/?status=shell',
    caveats: Core.AGENT_CAVEATS
  }, terms));
  assert.ok(text.endsWith('\n'));
  const fc = JSON.parse(text);
  assert.equal(fc.type, 'FeatureCollection');
  assert.deepEqual(Object.keys(fc), [
    'type', 'name', 'dataset', 'query', 'license', 'attribution', 'attribution_url', 'source_url', 'view_url', 'caveats',
    'features'
  ]);
  assert.deepEqual(fc.caveats, Core.AGENT_CAVEATS, 'the file says how to read statuses and locators');
  assert.equal(fc.query, '?status=shell');
  assert.deepEqual(fc.license, Core.DEFAULT_EXPORT_LICENSE);
  assert.equal(fc.license.data.id, 'CC-BY-4.0');
  assert.equal(fc.license.openstreetmap_geometries.id, 'ODbL-1.0');
  assert.match(fc.attribution, /^Data Center Atlas, https:\/\/example\.org\/atlas\/ \(dataset d1\)\. Includes data © OpenStreetMap contributors \(ODbL 1\.0\)/);
  assert.equal(fc.attribution_url, 'https://example.org/atlas/about/attribution/');
  assert.equal(fc.source_url, 'https://example.org/atlas/api/v1/sites.geojson');
  assert.equal(fc.view_url, 'https://example.org/atlas/?status=shell');
  assert.deepEqual(fc.features.map((f) => f.id), ['vcc-site-b', 'vcc-site-c']);
  assert.equal(fc.features[1].geometry.type, 'Polygon');
  assert.equal(fc.features[0].properties.name, 'Mäntsälä Data Centre');
  const empty = JSON.parse(Core.sitesToGeoJSON([], {}));
  assert.deepEqual(empty.features, []);
  assert.equal(empty.dataset, null);
  assert.equal(empty.license, null);
  assert.equal(empty.caveats, null);
});

test('exportTerms prefers the data, then the page bootstrap, then the default', () => {
  const fromData = { data: { id: 'X-1' } };
  const fromPage = { data: { id: 'Y-1' } };
  const boot = { license: fromPage, attribution: 'Atlas (Someone), https://example.org/', attribution_url: 'https://example.org/credits/' };
  assert.equal(Core.exportTerms({ license: fromData, attribution: 'From data' }, boot).license, fromData);
  assert.equal(Core.exportTerms({ license: fromData, attribution: 'From data' }, boot).attribution, 'From data');
  assert.equal(Core.exportTerms({}, boot).license, fromPage);
  assert.equal(Core.exportTerms({}, boot).attribution, 'Atlas (Someone), https://example.org/');
  assert.equal(Core.exportTerms({}, boot).attribution_url, 'https://example.org/credits/');
  assert.equal(Core.exportTerms(null, null).license, Core.DEFAULT_EXPORT_LICENSE);
  assert.equal(Core.exportTerms(null, { attribution_url: 'javascript:alert(1)' }).attribution_url, '');
  assert.equal(Core.exportTerms({ license: ['not', 'an', 'object'] }, null).license, Core.DEFAULT_EXPORT_LICENSE);
});

test('agent tools: schemas from the data and strict input validation', () => {
  const sites = fixtureSites();
  const ctx = Core.buildContext(sites);
  const schemas = Core.agentToolSchemas(ctx);
  assert.deepEqual(schemas.search.properties.country.enum, ['DE', 'FI', 'ID']);
  assert.deepEqual(schemas.search.properties.statuses.items.enum, ['under_construction', 'site_preparation', 'shell']);
  assert.equal(schemas.search.additionalProperties, false);
  assert.deepEqual(schemas.site.required, ['site_id']);
  assert.doesNotThrow(() => JSON.stringify(schemas));

  const ok = Core.toolInputToState({
    query: ' Alpha  ', country: 'de', statuses: ['under_construction'], locator: 'point', has_power: false,
    from: '2026-06', to: '2026-08', sort: 'newest', limit: 5
  }, ctx);
  assert.deepEqual(ok.state, {
    q: 'Alpha', country: 'DE', status: ['under_construction'], locator: 'point', power: false,
    from: '2026-06', to: '2026-08', sort: 'newest'
  });
  assert.equal(Core.toolInputToState({ to: '2030-01' }, ctx).state.to, '', 'a bound past the data is dropped');
  assert.equal(ok.limit, 5);
  assert.deepEqual(Core.toolInputToState(undefined, ctx), { state: Core.defaultState(), limit: 50 });
  assert.deepEqual(Core.filterSites(sites, ok.state).map((s) => s.id), ['vcc-site-a', 'vcc-site-d']);

  const bad = [
    [[], /object/], ['x', /object/], [{ nope: 1 }, /Unknown option "nope"/], [{ query: 5 }, /query/],
    [{ query: 'x'.repeat(201) }, /query/], [{ country: 'XX' }, /country/], [{ statuses: 'shell' }, /array/],
    [{ statuses: ['operational'] }, /Unknown status "operational"/], [{ locator: 'all' }, /locator/],
    [{ has_power: 'yes' }, /has_power/], [{ from: '2026-13' }, /from/], [{ from: '2026-08', to: '2026-06' }, /later/],
    [{ sort: 'random' }, /sort/], [{ limit: 0 }, /limit/], [{ limit: 2.5 }, /limit/], [{ limit: 201 }, /limit/]
  ];
  for (const [input, message] of bad) {
    assert.throws(() => Core.toolInputToState(input, ctx), message, JSON.stringify(input));
  }
  assert.equal(Core.toolSiteId({ site_id: 'vcc-site-52b1e1c3038357306a39' }), 'vcc-site-52b1e1c3038357306a39');
  assert.throws(() => Core.toolSiteId({ site_id: '../../etc' }), /site_id/);
  assert.throws(() => Core.toolSiteId({}), /site_id/);
  assert.throws(() => Core.toolSiteId({ site_id: 'vcc-site-52b1e1c3038357306a39', extra: true }), /Unknown option/);

  const summary = Core.toolSiteSummary(sites[2]);
  assert.equal(summary.site_id, 'vcc-site-c');
  assert.deepEqual(summary.statuses, ['shell', 'under_construction'], 'dataset order');
  assert.equal(summary.official_boundary, true);
  assert.equal(summary.project_count, 3);
  assert.equal(summary.geometry_licenses, null, 'unknown, not an empty list');
  sites[2].properties.geometry_licenses = ['ODbL-1.0', 'ODbL-1.0'];
  assert.deepEqual(Core.toolSiteSummary(sites[2]).geometry_licenses, ['ODbL-1.0']);
  assert.equal(Core.AGENT_CAVEATS.length, 4);
  assert.ok(Core.AGENT_CAVEATS.some((text) => /not the status today/.test(text)));
});

test('prepared polygon sites carry their bounds for map fits', () => {
  const [alpha, , jakarta] = fixtureSites();
  assert.equal(alpha.bounds, null);
  assert.deepEqual(jakarta.bounds, [[50, 10], [50.01, 10.01]]);
});

test('site-page colour rule matches the explorer: newest project, specific stage on a tie', () => {
  // STT Jakarta's shape: three projects on the same day, one shell, two under construction.
  const tie = Core.prepareSite(feature(baseProps({
    statuses: ['shell', 'under_construction'],
    projects: [
      { project_id: 'p1', name: 'Phase 1', status: 'under_construction', status_as_of: '2026-06-10' },
      { project_id: 'p2', name: 'Phase 2', status: 'shell', status_as_of: '2026-06-10' },
      { project_id: 'p3', name: 'Phase 3', status: 'under_construction', status_as_of: '2026-06-10' }
    ]
  })));
  assert.equal(tie.primaryStatus, 'shell');
  assert.equal(Core.statusGroup(tie.primaryStatus).id, 'active');
  assert.equal(Core.sortStatusCodes(tie.statuses)[0], 'under_construction');
});

test('exportFilename is filesystem-safe', () => {
  assert.equal(Core.exportFilename('2026-08-20-v0.18-draft', true, 'csv'), 'datacenter-atlas-2026-08-20-v0.18-draft-sites-filtered.csv');
  assert.equal(Core.exportFilename('a/b c', false, 'geojson'), 'datacenter-atlas-a-b-c-sites.geojson');
  assert.equal(Core.exportFilename('', false, 'csv'), 'datacenter-atlas-sites.csv');
});

test('safeHttpUrl accepts only absolute http(s) URLs', () => {
  assert.equal(Core.safeHttpUrl('https://example.org/a b'), 'https://example.org/a%20b');
  assert.equal(Core.safeHttpUrl(' http://example.org '), 'http://example.org/');
  assert.equal(Core.safeHttpUrl('javascript:alert(1)'), '');
  assert.equal(Core.safeHttpUrl('JaVaScRiPt:alert(1)'), '');
  assert.equal(Core.safeHttpUrl('data:text/html,x'), '');
  assert.equal(Core.safeHttpUrl('//example.org'), '');
  assert.equal(Core.safeHttpUrl('/relative'), '');
  assert.equal(Core.safeHttpUrl('https://'), '');
  assert.equal(Core.safeHttpUrl(null), '');
});

test('externalMapLinks use the documented URL patterns at 6 dp', () => {
  const links = Core.externalMapLinks(18.6467083333, -73.8072666667);
  assert.deepEqual(links.map((l) => l.id), ['osm', 'google', 'bing', 'copernicus']);
  assert.equal(links[0].url, 'https://www.openstreetmap.org/?mlat=18.646708&mlon=-73.807267#map=16/18.646708/-73.807267');
  assert.equal(links[1].url, 'https://www.google.com/maps/search/?api=1&query=18.646708,-73.807267');
  assert.equal(links[2].url, 'https://www.bing.com/maps?cp=18.646708~-73.807267&lvl=17&style=a');
  assert.equal(links[3].url, 'https://browser.dataspace.copernicus.eu/?zoom=15&lat=18.646708&lng=-73.807267');
  assert.deepEqual(Core.externalMapLinks(95, 0), []);
  assert.deepEqual(Core.externalMapLinks('x', 0), []);
  assert.equal(Core.formatCoordinate(18.6467083333, 5), '18.64671');
});

test('correctionUrl targets the correction issue form', () => {
  assert.equal(
    Core.correctionUrl('https://github.com/o/r/issues', 'Mäntsälä & Co', 'vcc-site-b'),
    'https://github.com/o/r/issues/new?template=correction.yml&title=Correction%3A%20M%C3%A4nts%C3%A4l%C3%A4%20%26%20Co&site_id=vcc-site-b'
  );
  assert.equal(Core.correctionUrl('https://github.com/o/r/issues/', 'X', 'y'), 'https://github.com/o/r/issues/new?template=correction.yml&title=Correction%3A%20X&site_id=y');
  assert.equal(Core.correctionUrl('javascript:alert(1)', 'X', 'y'), '');
});

test('relative URL helpers', () => {
  assert.equal(Core.joinRoot('./', 'sites/x/'), './sites/x/');
  assert.equal(Core.joinRoot('../..', '/api/v1/index.json'), '../../api/v1/index.json');
  assert.equal(Core.joinRoot('', 'data/'), './data/');
  assert.equal(Core.fillTemplate('api/v1/sites/{site_id}.json', { site_id: 'a b/c' }), 'api/v1/sites/a%20b%2Fc.json');
  assert.equal(Core.fillTemplate('x/{other}', { site_id: 'a' }), 'x/{other}');
});

test('formatPowerValue shows a range only when bounds differ', () => {
  assert.equal(Core.formatPowerValue({ low: 5.28, base: 5.28, high: 5.28, unit: 'MW' }), '5.28 MW');
  assert.equal(Core.formatPowerValue({ low: 10, base: 20, high: 30, unit: 'MW' }), '10–30 MW');
  assert.equal(Core.formatPowerValue({ low: null, base: 1.4, high: null, unit: 'ratio' }), '1.4 ratio');
  assert.equal(Core.formatPowerValue({ low: 1200, base: null, high: null, unit: 'MWh/year' }), '1,200 MWh/year');
  assert.equal(Core.formatPowerValue({}), '');
  assert.equal(Core.formatNumber('x'), '');
  assert.equal(Core.plural(1, 'site'), '1 site');
  assert.equal(Core.plural(2, 'site'), '2 sites');
  assert.equal(Core.plural(0, 'entry', 'entries'), '0 entries');
});

test('geometry helpers convert GeoJSON to Leaflet order and bounds', () => {
  assert.deepEqual(Core.geometryLatLngs(square)[0][0], [50, 10]);
  const multi = { type: 'MultiPolygon', coordinates: [square.coordinates, square.coordinates] };
  const latlngs = Core.geometryLatLngs(multi);
  assert.equal(latlngs.length, 2);
  assert.deepEqual(latlngs[1][0][2], [50.01, 10.01]);
  assert.equal(Core.geometryLatLngs({ type: 'Point', coordinates: [1, 2] }), null);
  assert.equal(Core.geometryLatLngs({ type: 'Polygon', coordinates: [[[1, 2], [3]]] }), null);
  assert.deepEqual(Core.geometryBounds(square), [[50, 10], [50.01, 10.01]]);
  assert.deepEqual(Core.geometryBounds({ type: 'Point', coordinates: [8.6, 50.1] }), [[50.1, 8.6], [50.1, 8.6]]);
  assert.equal(Core.geometryBounds({ type: 'LineString', coordinates: [[0, 0], [1, 1]] }), null);
  assert.equal(Core.validGeometry({ type: 'Point', coordinates: [NaN, 1] }), null);
  assert.equal(Core.validGeometry(null), null);
});

test('nearestPoint finds the closest point within the radius', () => {
  const points = [{ x: 0, y: 0, id: 'a' }, { x: 10, y: 0, id: 'b' }, { x: 30, y: 30, id: 'c' }];
  assert.equal(Core.nearestPoint(points, 7, 1, 12), 'b');
  assert.equal(Core.nearestPoint(points, 2, 0, 12), 'a');
  assert.equal(Core.nearestPoint(points, 100, 100, 12), null);
  assert.equal(Core.nearestPoint([], 0, 0, 12), null);
});

// Leaflet writes basemap names and attributions with innerHTML: allow only
// fixed text, entities and links to https URLs.
const SAFE_ATTRIBUTION = /^(?:[^<>&]|&(?:copy|middot|amp);|<a href="(?:https:\/\/[^"<>\s]+|(?:\.\/|(?:\.\.\/)+)about\/attribution\/)">[^<>]+<\/a>)+$/;

test('basemaps: keyless OpenStreetMap and EOX by default, CARTO only with a key', () => {
  assert.deepEqual(Core.BASEMAPS.map((b) => b.id), ['osm', 'osm-dark', 'satellite']);
  const keyed = Core.basemapsFor({ cartoKey: 'Ab3_dEf-9.x~K' });
  assert.deepEqual(keyed.map((b) => b.id), ['light', 'dark', 'osm', 'satellite']);
  for (const basemap of [...Core.BASEMAPS, ...keyed]) {
    assert.match(basemap.url, /^https:\/\/(?:\{s\}\.basemaps\.cartocdn\.com|tile\.openstreetmap\.org|tiles\.maps\.eox\.at)\//);
    assert.match(basemap.name, /^[A-Za-z0-9 (),-]+$/, `${basemap.id} name is plain text`);
    assert.match(basemap.options.attribution, SAFE_ATTRIBUTION, `${basemap.id} attribution`);
    if (/cartocdn/.test(basemap.url)) {
      assert.match(basemap.url, /\?key=Ab3_dEf-9\.x~K$/, 'every CARTO tile URL carries the key');
    }
  }
  assert.deepEqual(Core.basemapsFor({ cartoKey: 'short' }).map((b) => b.id), Core.BASEMAPS.map((b) => b.id), 'implausible keys are ignored');
  assert.deepEqual(Core.basemapsFor({ cartoKey: 'abcdefgh"><img src=x>' }).map((b) => b.id), Core.BASEMAPS.map((b) => b.id));
  assert.equal(Core.cartoKey('  abcdefgh12  '), 'abcdefgh12');
  assert.notEqual(Core.basemapsFor({}), Core.basemapsFor({}), 'callers get fresh objects');

  assert.match(Core.findBasemap('light', keyed).options.attribution, /OpenStreetMap.*CARTO/);
  assert.match(Core.findBasemap('osm').options.attribution, /href="https:\/\/www\.openstreetmap\.org\/fixthemap">Report a map issue</);
  assert.equal(Core.findBasemap('osm-dark').options.className, 'atlas-tiles-dark');
  assert.equal(Core.findBasemap('osm-dark').url, Core.findBasemap('osm').url, 'the dark variant reuses the cached OSM tiles');
  const eox = Core.findBasemap('satellite').options.attribution;
  assert.equal(eox, '<a href="https://cloudless.eox.at">EOxCloudless</a> <a href="https://cloudless.eox.at">https://cloudless.eox.at</a> by ' +
    '<a href="https://eox.at">EOX IT Services GmbH</a> (Contains modified Copernicus Sentinel data 2025), ' +
    '<a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">CC BY-NC-SA 4.0</a>');
  assert.equal(Core.findBasemap('satellite').options.maxNativeZoom, 18);
  assert.equal(Core.findBasemap('osm').options.maxZoom, 19);

  assert.equal(Core.chooseBasemap('', true), 'osm-dark');
  assert.equal(Core.chooseBasemap('', false), 'osm');
  assert.equal(Core.chooseBasemap('', true, keyed), 'dark');
  assert.equal(Core.chooseBasemap('', false, keyed), 'light');
  assert.equal(Core.chooseBasemap('satellite', true), 'satellite');
  assert.equal(Core.chooseBasemap('dark', false), 'osm-dark', 'a stored CARTO choice keeps its role without a key');
  assert.equal(Core.chooseBasemap('light', true), 'osm');
  assert.equal(Core.chooseBasemap('osm-dark', false, keyed), 'dark');
  assert.equal(Core.chooseBasemap('evil', false), 'osm');

  const store = new Map();
  const storage = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, v) };
  assert.equal(Core.readStoredBasemap(storage), '');
  assert.equal(Core.storeBasemap(storage, 'satellite'), true);
  assert.equal(Core.readStoredBasemap(storage), 'satellite');
  assert.equal(Core.storeBasemap(storage, 'nope'), false);
  store.set(Core.BASEMAP_STORAGE_KEY, 'dark');
  assert.equal(Core.readStoredBasemap(storage), 'dark', 'choices stored before a key change are still read');
  store.set(Core.BASEMAP_STORAGE_KEY, '<b>');
  assert.equal(Core.readStoredBasemap(storage), '');
  const throwing = { getItem() { throw new Error('denied'); }, setItem() { throw new Error('denied'); } };
  assert.equal(Core.readStoredBasemap(throwing), '');
  assert.equal(Core.storeBasemap(throwing, 'osm'), false);
  assert.equal(Core.readStoredBasemap(null), '');
});

test('dataCredit links the attribution page only through a relative root', () => {
  for (const root of ['./', '../', '../../']) {
    const credit = Core.dataCredit(root);
    assert.match(credit, SAFE_ATTRIBUTION);
    assert.ok(credit.includes(`<a href="${root}about/attribution/">Data Center Atlas</a>`), credit);
    assert.match(credit, /CC BY 4\.0/);
    assert.match(credit, /OpenStreetMap<\/a> contributors \(ODbL\)/);
  }
  for (const root of ['https://evil.example/', '"><script>', '/', '', null, '.././', '../x/']) {
    const credit = Core.dataCredit(root);
    assert.ok(!credit.includes('about/attribution'), String(root));
    assert.match(credit, SAFE_ATTRIBUTION);
  }
});
