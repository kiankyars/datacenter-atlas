/*
 * Data Center Atlas: pure logic shared by the explorer (app.js), the site-page
 * map (site-map.js) and the node unit tests (site/js-tests).
 *
 * No DOM access happens here. In a browser the API is attached to
 * window.AtlasCore; in node it is module.exports. Every dataset value is
 * treated as untrusted text: nothing here builds HTML from data.
 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module && module.exports) {
    module.exports = api;
  }
  if (typeof window !== 'undefined' && root === window) {
    window.AtlasCore = api;
  }
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict';

  var hasOwn = function (obj, key) {
    return obj !== null && typeof obj === 'object' && Object.prototype.hasOwnProperty.call(obj, key);
  };

  // ---------------------------------------------------------------------------
  // Status vocabulary and colour groups
  // ---------------------------------------------------------------------------

  // Lifecycle order from datacenter_atlas/models.py (LifecycleStatus).
  var LIFECYCLE_ORDER = [
    'lead', 'candidate', 'announced', 'proposed', 'site_control', 'permitting', 'permitted',
    'site_preparation', 'clearing', 'civil_works', 'foundations', 'shell', 'mep_electrical',
    'under_construction', 'commissioning', 'operational', 'expansion', 'paused', 'cancelled',
    'repurposed', 'decommissioned', 'demolished', 'unknown'
  ];

  // A map is an "all pairs" chart form: any two markers can sit side by side,
  // and only three categorical hues stay pairwise distinguishable under
  // protanopia/deuteranopia. Statuses are therefore coloured in three groups
  // (Okabe-Ito blue / vermillion / bluish green, validated in light and dark
  // mode), and the exact status is always written out in text. These hex
  // values must match the --st-* tokens in site.css.
  var STATUS_GROUPS = [
    {
      id: 'active',
      label: 'Under construction',
      note: 'Source reports construction without a narrower stage',
      color: '#0072B2',
      codes: ['under_construction']
    },
    {
      id: 'early',
      label: 'Early works',
      note: 'Site preparation, clearing, civil works, foundations',
      color: '#D55E00',
      codes: ['site_preparation', 'clearing', 'civil_works', 'foundations']
    },
    {
      id: 'late',
      label: 'Building & fit-out',
      note: 'Shell, MEP / electrical, commissioning',
      color: '#009E73',
      codes: ['shell', 'mep_electrical', 'commissioning']
    }
  ];
  var OTHER_GROUP = {
    id: 'other',
    label: 'Other status',
    note: 'Any status outside the construction stages',
    color: '#767676',
    codes: []
  };

  var GROUP_BY_CODE = Object.create(null);
  STATUS_GROUPS.forEach(function (group) {
    group.codes.forEach(function (code) { GROUP_BY_CODE[code] = group; });
  });

  function statusGroup(code) {
    return GROUP_BY_CODE[String(code)] || OTHER_GROUP;
  }

  function statusRank(code) {
    var group = statusGroup(code);
    var groupIndex = group === OTHER_GROUP ? STATUS_GROUPS.length : STATUS_GROUPS.indexOf(group);
    var lifecycle = LIFECYCLE_ORDER.indexOf(String(code));
    return groupIndex * 100 + (lifecycle === -1 ? 99 : lifecycle);
  }

  /** Sort status codes by colour group, then lifecycle order, then code. */
  function sortStatusCodes(codes) {
    return uniqueStrings(codes).sort(function (a, b) {
      return (statusRank(a) - statusRank(b)) || compareRaw(a, b);
    });
  }

  // Fallback labels; the bootstrap vocabularies (site/vocabulary.json) win.
  var BUILTIN_LABELS = {
    statuses: {
      lead: 'Lead', candidate: 'Candidate', announced: 'Announced', proposed: 'Proposed',
      site_control: 'Site control', permitting: 'Permitting', permitted: 'Permitted',
      site_preparation: 'Site preparation', clearing: 'Clearing', civil_works: 'Civil works',
      foundations: 'Foundations', shell: 'Shell', mep_electrical: 'MEP / electrical',
      under_construction: 'Under construction', commissioning: 'Commissioning',
      operational: 'Operational', expansion: 'Expansion', paused: 'Paused', cancelled: 'Cancelled',
      repurposed: 'Repurposed', decommissioned: 'Decommissioned', demolished: 'Demolished',
      unknown: 'Unknown'
    },
    power_metrics: {
      grid_connection_mw: 'Grid connection', gross_facility_mw: 'Gross facility load',
      critical_it_mw: 'Critical IT load', generation_nameplate_mw: 'Generation nameplate',
      annual_energy_mwh: 'Annual energy', pue: 'PUE'
    },
    workloads: {
      ai_specialized_unspecified: 'AI (unspecified)', ai_training: 'AI training',
      ai_inference: 'AI inference', hpc: 'HPC', general_cloud: 'General cloud',
      enterprise_it: 'Enterprise IT', content_delivery: 'Content delivery',
      crypto_mining: 'Crypto mining', mixed: 'Mixed', unknown: 'Unknown'
    },
    operating_models: {
      hyperscaler: 'Hyperscaler', hyperscale_self_build: 'Hyperscale self-build',
      hyperscale_lease: 'Hyperscale lease', colocation: 'Colocation',
      wholesale_colocation: 'Wholesale colocation', retail_colocation: 'Retail colocation',
      neocloud: 'Neocloud', enterprise_private: 'Enterprise private',
      government_research: 'Government research', sovereign_research: 'Sovereign research',
      edge: 'Edge', telecom_edge: 'Telecom edge', unknown: 'Unknown'
    }
  };

  /** "under_construction" -> "Under construction"; "a:b_c" -> "A: b c". */
  function humanizeCode(code) {
    var text = String(code === null || code === undefined ? '' : code)
      .replace(/_/g, ' ')
      .replace(/\s*:\s*/g, ': ')
      .replace(/\s+/g, ' ')
      .trim();
    return text ? text.charAt(0).toUpperCase() + text.slice(1) : '';
  }

  function vocabEntry(vocab, kind, code) {
    var table = vocab && hasOwn(vocab, kind) ? vocab[kind] : null;
    return table && hasOwn(table, code) ? table[code] : null;
  }

  /** Label for a coded value: bootstrap vocabulary, then built-in, then humanized code. */
  function vocabLabel(vocab, kind, code) {
    if (code === null || code === undefined || code === '') {
      return '';
    }
    var key = String(code);
    var entry = vocabEntry(vocab, kind, key);
    if (entry && typeof entry === 'object' && typeof entry.label === 'string' && entry.label) {
      return entry.label;
    }
    if (typeof entry === 'string' && entry) {
      return entry;
    }
    var builtin = BUILTIN_LABELS[kind];
    if (builtin && hasOwn(builtin, key)) {
      return builtin[key];
    }
    return humanizeCode(key);
  }

  function vocabDescription(vocab, kind, code) {
    var entry = vocabEntry(vocab, kind, String(code));
    return entry && typeof entry === 'object' && typeof entry.description === 'string' ? entry.description : '';
  }

  function statusLabel(code, vocab) {
    return vocabLabel(vocab, 'statuses', code);
  }

  // ---------------------------------------------------------------------------
  // Small value helpers
  // ---------------------------------------------------------------------------

  function str(value) {
    if (value === null || value === undefined) {
      return '';
    }
    return typeof value === 'string' ? value : String(value);
  }

  function num(value) {
    if (typeof value === 'number') {
      return isFinite(value) ? value : null;
    }
    if (typeof value === 'string' && value.trim() !== '') {
      var parsed = Number(value);
      return isFinite(parsed) ? parsed : null;
    }
    return null;
  }

  function compareRaw(a, b) {
    return a < b ? -1 : (a > b ? 1 : 0);
  }

  function uniqueStrings(values) {
    var out = [];
    var seen = Object.create(null);
    (Array.isArray(values) ? values : []).forEach(function (value) {
      if (typeof value !== 'string' || value === '' || seen[value]) {
        return;
      }
      seen[value] = true;
      out.push(value);
    });
    return out;
  }

  var DATE_RE = /^(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])/;
  var MONTH_RE = /^(\d{4})-(0[1-9]|1[0-2])$/;

  /** "2026-06-01" or "2026-06-01T00:00:00Z" -> "2026-06-01"; anything else -> "". */
  function isoDate(value) {
    var match = DATE_RE.exec(str(value));
    return match ? match[0] : '';
  }

  function isMonth(value) {
    return typeof value === 'string' && MONTH_RE.test(value);
  }

  function monthOf(value) {
    var date = isoDate(value);
    return date ? date.slice(0, 7) : '';
  }

  /** Inclusive list of YYYY-MM months from `start` to `end`. */
  function monthRange(start, end) {
    if (!isMonth(start) || !isMonth(end) || start > end) {
      return [];
    }
    var out = [];
    var year = Number(start.slice(0, 4));
    var month = Number(start.slice(5, 7));
    var guard = 0;
    for (;;) {
      var ym = year + '-' + (month < 10 ? '0' : '') + month;
      out.push(ym);
      if (ym === end || guard++ > 2400) {
        break;
      }
      month += 1;
      if (month > 12) {
        month = 1;
        year += 1;
      }
    }
    return out;
  }

  var MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  function formatMonth(ym) {
    if (!isMonth(ym)) {
      return '';
    }
    return MONTH_NAMES[Number(ym.slice(5, 7)) - 1] + ' ' + ym.slice(0, 4);
  }

  /** ISO date minus `days` days (UTC), e.g. ("2026-08-20", 90) -> "2026-05-22". */
  function isoDateMinusDays(value, days) {
    var date = isoDate(value);
    if (!date || !isFinite(days)) {
      return '';
    }
    var ms = Date.UTC(Number(date.slice(0, 4)), Number(date.slice(5, 7)) - 1, Number(date.slice(8, 10)));
    return new Date(ms - Math.round(days) * 86400000).toISOString().slice(0, 10);
  }

  var numberFormat = (typeof Intl !== 'undefined' && Intl.NumberFormat)
    ? new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })
    : null;

  function formatNumber(value) {
    var n = num(value);
    if (n === null) {
      return '';
    }
    return numberFormat ? numberFormat.format(n) : String(Math.round(n * 100) / 100);
  }

  function plural(count, singular, pluralForm) {
    return count + ' ' + (count === 1 ? singular : (pluralForm || singular + 's'));
  }

  // ---------------------------------------------------------------------------
  // Search text
  // ---------------------------------------------------------------------------

  // Latin letters that Unicode decomposition does not reduce to ASCII.
  var TRANSLITERATE = {
    '\u00df': 'ss', '\u00e6': 'ae', '\u0153': 'oe', '\u00f8': 'o', '\u0142': 'l', '\u0111': 'd', '\u00f0': 'd',
    '\u00fe': 'th', '\u0131': 'i', '\u0127': 'h', '\u0167': 't', '\u014b': 'ng'
  };
  var TRANSLITERATE_RE = /[\u00df\u00e6\u0153\u00f8\u0142\u0111\u00f0\u00fe\u0131\u0127\u0167\u014b]/g;
  var CJK_RE = /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]/;

  /**
   * Lower-case, strip Latin diacritics, drop apostrophes, and reduce every run
   * of other punctuation/whitespace to a single space.
   */
  function normalizeText(value) {
    if (value === null || value === undefined) {
      return '';
    }
    return String(value)
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(TRANSLITERATE_RE, function (ch) { return TRANSLITERATE[ch]; })
      .replace(/['\u2019\u02bc`\u00b4]/g, '')
      .replace(/[^\p{L}\p{N}\p{M}]+/gu, ' ')
      .trim();
  }

  function tokenize(query) {
    var text = normalizeText(query);
    return text ? text.split(' ') : [];
  }

  /**
   * Every token must start a word of the search text (so "frank" finds
   * "Frankfurt" but "us" does not find "campus"). Tokens containing CJK
   * characters, which are not space-separated, match anywhere.
   */
  function matchesTokens(searchText, tokens) {
    if (!tokens.length) {
      return true;
    }
    var haystack = ' ' + searchText;
    for (var i = 0; i < tokens.length; i++) {
      var token = tokens[i];
      if (CJK_RE.test(token)) {
        if (searchText.indexOf(token) === -1) {
          return false;
        }
      } else if (haystack.indexOf(' ' + token) === -1) {
        return false;
      }
    }
    return true;
  }

  /** Search text from name, country, ISO code, project names, status publishers and site id. */
  function buildSearchText(parts) {
    var pieces = [];
    (Array.isArray(parts) ? parts : [parts]).forEach(function (part) {
      if (Array.isArray(part)) {
        part.forEach(function (inner) { pieces.push(str(inner)); });
      } else {
        pieces.push(str(part));
      }
    });
    return normalizeText(pieces.join(' '));
  }

  // ---------------------------------------------------------------------------
  // Geometry
  // ---------------------------------------------------------------------------

  function isPosition(value) {
    return Array.isArray(value) && value.length >= 2 &&
      typeof value[0] === 'number' && isFinite(value[0]) &&
      typeof value[1] === 'number' && isFinite(value[1]);
  }

  function isRing(ring) {
    return Array.isArray(ring) && ring.length >= 3 && ring.every(isPosition);
  }

  function isPolygonCoords(coords) {
    return Array.isArray(coords) && coords.length >= 1 && coords.every(isRing);
  }

  /** Returns the geometry when it is a well-formed Point/Polygon/MultiPolygon, else null. */
  function validGeometry(geometry) {
    if (!geometry || typeof geometry !== 'object') {
      return null;
    }
    var coords = geometry.coordinates;
    switch (geometry.type) {
      case 'Point':
        return isPosition(coords) ? geometry : null;
      case 'Polygon':
        return isPolygonCoords(coords) ? geometry : null;
      case 'MultiPolygon':
        return Array.isArray(coords) && coords.length >= 1 && coords.every(isPolygonCoords) ? geometry : null;
      default:
        return null;
    }
  }

  function ringToLatLngs(ring) {
    return ring.map(function (pos) { return [pos[1], pos[0]]; });
  }

  /** Leaflet-ready [lat, lng] nesting for Polygon/MultiPolygon; null otherwise. */
  function geometryLatLngs(geometry) {
    var geom = validGeometry(geometry);
    if (!geom || geom.type === 'Point') {
      return null;
    }
    if (geom.type === 'Polygon') {
      return geom.coordinates.map(ringToLatLngs);
    }
    return geom.coordinates.map(function (polygon) { return polygon.map(ringToLatLngs); });
  }

  /** [[south, west], [north, east]] of any supported geometry, or null. */
  function geometryBounds(geometry) {
    var geom = validGeometry(geometry);
    if (!geom) {
      return null;
    }
    var south = Infinity;
    var west = Infinity;
    var north = -Infinity;
    var east = -Infinity;
    var visit = function (pos) {
      if (pos[1] < south) { south = pos[1]; }
      if (pos[1] > north) { north = pos[1]; }
      if (pos[0] < west) { west = pos[0]; }
      if (pos[0] > east) { east = pos[0]; }
    };
    if (geom.type === 'Point') {
      visit(geom.coordinates);
    } else {
      var polygons = geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates;
      polygons.forEach(function (polygon) {
        polygon.forEach(function (ring) { ring.forEach(visit); });
      });
    }
    return [[south, west], [north, east]];
  }

  /** Nearest point within `maxDistance` pixels: points are {x, y, id}. */
  function nearestPoint(points, x, y, maxDistance) {
    var best = null;
    var bestDistance = maxDistance * maxDistance;
    for (var i = 0; i < points.length; i++) {
      var dx = points[i].x - x;
      var dy = points[i].y - y;
      var distance = dx * dx + dy * dy;
      if (distance <= bestDistance) {
        bestDistance = distance;
        best = points[i].id;
      }
    }
    return best;
  }

  // ---------------------------------------------------------------------------
  // Site preparation (sites.geojson feature -> explorer record)
  // ---------------------------------------------------------------------------

  /**
   * Colour status for a site: the status of its most recently observed
   * project; on a tie the more specific stage beats the generic
   * "under_construction", then the later lifecycle stage wins.
   */
  function primaryStatus(projects, statuses) {
    var candidates = (projects || []).filter(function (project) { return project.status; });
    if (!candidates.length) {
      return sortStatusCodes(statuses)[0] || '';
    }
    candidates = candidates.slice().sort(function (a, b) {
      var byDate = compareRaw(b.statusAsOf || '', a.statusAsOf || '');
      if (byDate) {
        return byDate;
      }
      var generic = (a.status === 'under_construction') - (b.status === 'under_construction');
      if (generic) {
        return generic;
      }
      return LIFECYCLE_ORDER.indexOf(b.status) - LIFECYCLE_ORDER.indexOf(a.status) || compareRaw(a.status, b.status);
    });
    return candidates[0].status;
  }

  function prepareSite(feature) {
    if (!feature || typeof feature !== 'object') {
      return null;
    }
    var props = feature.properties && typeof feature.properties === 'object' ? feature.properties : {};
    var id = str(props.site_id) || str(feature.id);
    if (!id) {
      return null;
    }
    var geometry = validGeometry(feature.geometry);
    var lat = num(props.latitude);
    var lon = num(props.longitude);
    if ((lat === null || lon === null) && geometry && geometry.type === 'Point') {
      lon = geometry.coordinates[0];
      lat = geometry.coordinates[1];
    }
    var hasLocation = lat !== null && lon !== null && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
    var projects = (Array.isArray(props.projects) ? props.projects : [])
      .filter(function (project) { return project && typeof project === 'object'; })
      .map(function (project) {
        return {
          id: str(project.project_id),
          name: str(project.name),
          status: str(project.status),
          statusAsOf: isoDate(project.status_as_of)
        };
      });
    var statuses = uniqueStrings(props.statuses);
    if (!statuses.length) {
      statuses = uniqueStrings(projects.map(function (project) { return project.status; }));
    }
    var projectDates = projects.map(function (project) { return project.statusAsOf; }).filter(Boolean).sort();
    var newest = isoDate(props.newest_status_as_of) || projectDates[projectDates.length - 1] || '';
    var oldest = isoDate(props.oldest_status_as_of) || projectDates[0] || '';
    var months = uniqueStrings(projectDates.map(monthOf));
    if (!months.length) {
      months = uniqueStrings([monthOf(oldest), monthOf(newest)]);
    }
    var power = (Array.isArray(props.power_observations) ? props.power_observations : [])
      .filter(function (obs) { return obs && typeof obs === 'object'; });
    var publishers = uniqueStrings(props.status_publishers);
    var geometryType = str(props.geometry_type) || (geometry ? geometry.type : 'Point');
    var projectCount = num(props.project_count);
    var name = str(props.name) || id;
    var country = str(props.country);
    var iso = str(props.country_iso_a2).toUpperCase();
    return {
      id: id,
      name: name,
      country: country,
      iso: iso,
      lat: hasLocation ? lat : null,
      lon: hasLocation ? lon : null,
      hasLocation: hasLocation,
      geometry: geometry,
      geometryType: geometryType,
      isArea: geometryType === 'Polygon' || geometryType === 'MultiPolygon',
      // [[south, west], [north, east]] of a polygon locator, so map fits keep the whole outline in view.
      bounds: geometry && geometry.type !== 'Point' ? geometryBounds(geometry) : null,
      officialBoundary: props.official_boundary === true,
      locatorScopes: uniqueStrings(props.locator_scopes),
      statuses: sortStatusCodes(statuses),
      primaryStatus: primaryStatus(projects, statuses),
      newest: newest,
      oldest: oldest,
      months: months,
      projectCount: projectCount === null ? projects.length : projectCount,
      projects: projects,
      publishers: publishers,
      power: power,
      hasPower: power.length > 0,
      verificationPosture: str(props.verification_posture),
      imageryVerified: props.independent_imagery_verification === true,
      url: str(props.url),
      apiUrl: str(props.api_url),
      searchText: buildSearchText([
        name, country, iso,
        projects.map(function (project) { return project.name; }),
        publishers, id
      ]),
      properties: props
    };
  }

  /** Prepare every feature of a sites.geojson FeatureCollection (duplicates dropped). */
  function prepareSites(collection) {
    var features = collection && Array.isArray(collection.features) ? collection.features : [];
    var out = [];
    var seen = Object.create(null);
    features.forEach(function (feature) {
      var site = prepareSite(feature);
      if (site && !seen[site.id]) {
        seen[site.id] = true;
        out.push(site);
      }
    });
    return out;
  }

  /** Filter domains derived from the data: countries, statuses and months. */
  function buildContext(sites) {
    var countries = Object.create(null);
    var statusCounts = Object.create(null);
    var minMonth = '';
    var maxMonth = '';
    (sites || []).forEach(function (site) {
      if (site.iso) {
        if (!countries[site.iso]) {
          countries[site.iso] = { iso: site.iso, name: site.country || site.iso, count: 0 };
        }
        countries[site.iso].count += 1;
      }
      site.statuses.forEach(function (code) {
        statusCounts[code] = (statusCounts[code] || 0) + 1;
      });
      site.months.forEach(function (month) {
        if (!minMonth || month < minMonth) { minMonth = month; }
        if (!maxMonth || month > maxMonth) { maxMonth = month; }
      });
    });
    var countryList = Object.keys(countries).map(function (key) { return countries[key]; });
    countryList.sort(function (a, b) { return compareText(a.name, b.name) || compareRaw(a.iso, b.iso); });
    return {
      countries: countryList,
      countryCodes: Object.keys(countries).sort(),
      statuses: sortStatusCodes(Object.keys(statusCounts)),
      statusCounts: statusCounts,
      months: minMonth ? monthRange(minMonth, maxMonth) : []
    };
  }

  // ---------------------------------------------------------------------------
  // Filter state
  // ---------------------------------------------------------------------------

  var LOCATORS = ['any', 'official_boundary', 'polygon', 'point'];
  var SORTS = ['name', 'country', 'newest', 'oldest', 'projects'];
  var STATUS_CODE_RE = /^[a-z][a-z0-9_]{0,63}$/;
  var SITE_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
  var MAX_QUERY_LENGTH = 200;

  function defaultState() {
    return { q: '', country: '', status: [], locator: 'any', power: false, from: '', to: '', sort: 'name' };
  }

  function cleanQuery(value) {
    return str(value).replace(/\s+/g, ' ').trim().slice(0, MAX_QUERY_LENGTH);
  }

  /** Parse "?q=...&country=..." into a syntactically valid state (unknown values dropped). */
  function parseQuery(search) {
    var params = new URLSearchParams(str(search).replace(/^\?/, ''));
    var state = defaultState();
    state.q = cleanQuery(params.get('q'));
    var country = str(params.get('country')).trim().toUpperCase();
    if (/^[A-Z]{2}$/.test(country)) {
      state.country = country;
    }
    var statuses = [];
    params.getAll('status').forEach(function (value) {
      value.split(',').forEach(function (code) {
        code = code.trim().toLowerCase();
        if (STATUS_CODE_RE.test(code)) {
          statuses.push(code);
        }
      });
    });
    state.status = uniqueStrings(statuses);
    var locator = params.get('locator');
    if (LOCATORS.indexOf(locator) !== -1) {
      state.locator = locator;
    }
    var power = params.get('power');
    state.power = power === '1' || power === 'true';
    var from = params.get('from');
    var to = params.get('to');
    if (isMonth(from)) { state.from = from; }
    if (isMonth(to)) { state.to = to; }
    var sort = params.get('sort');
    if (SORTS.indexOf(sort) !== -1) {
      state.sort = sort;
    }
    return state;
  }

  /** "#site=<id>" -> "<id>" when it is a plausible site id, else "". */
  function parseHash(hash) {
    var params = new URLSearchParams(str(hash).replace(/^#/, ''));
    var id = params.get('site');
    return id && SITE_ID_RE.test(id) ? id : '';
  }

  function buildHash(siteId) {
    return siteId ? '#site=' + encodeURIComponent(siteId) : '';
  }

  /** Canonical query string ("" for the default view); fixed parameter order. */
  function serializeState(state) {
    var s = state || defaultState();
    var parts = [];
    var q = cleanQuery(s.q);
    if (q) {
      parts.push('q=' + encodeURIComponent(q).replace(/%20/g, '+'));
    }
    if (s.country) {
      parts.push('country=' + encodeURIComponent(s.country));
    }
    if (s.status && s.status.length) {
      parts.push('status=' + s.status.map(encodeURIComponent).join(','));
    }
    if (s.locator && s.locator !== 'any') {
      parts.push('locator=' + encodeURIComponent(s.locator));
    }
    if (s.power) {
      parts.push('power=1');
    }
    if (s.from) {
      parts.push('from=' + encodeURIComponent(s.from));
    }
    if (s.to) {
      parts.push('to=' + encodeURIComponent(s.to));
    }
    if (s.sort && s.sort !== 'name') {
      parts.push('sort=' + encodeURIComponent(s.sort));
    }
    return parts.length ? '?' + parts.join('&') : '';
  }

  /**
   * Make a state well-formed and canonical without changing what it asks
   * for. A reversed from/to pair is swapped, and bounds that exclude nothing
   * (a "from" before the first month of the data, a "to" after the last) are
   * dropped. Anything that matches no site is kept, so a shared link that
   * matches nothing shows nothing rather than other sites: a country or
   * status code that is not in this dataset, a "from" after the last month,
   * a "to" before the first. Known statuses come first in context order.
   * Returns a new object.
   */
  function normalizeState(state, context) {
    var base = defaultState();
    var s = state || base;
    var ctx = context || {};
    var country = str(s.country).toUpperCase();
    var out = {
      q: typeof s.q === 'string' ? s.q.slice(0, MAX_QUERY_LENGTH) : '',
      country: /^[A-Z]{2}$/.test(country) ? country : '',
      status: [],
      locator: LOCATORS.indexOf(s.locator) !== -1 ? s.locator : base.locator,
      power: s.power === true,
      from: isMonth(s.from) ? s.from : '',
      to: isMonth(s.to) ? s.to : '',
      sort: SORTS.indexOf(s.sort) !== -1 ? s.sort : base.sort
    };
    var known = ctx.statuses || [];
    var wanted = uniqueStrings(s.status).filter(function (code) { return STATUS_CODE_RE.test(code); });
    out.status = known.filter(function (code) { return wanted.indexOf(code) !== -1; })
      .concat(wanted.filter(function (code) { return known.indexOf(code) === -1; }));
    if (out.from && out.to && out.from > out.to) {
      var swap = out.from;
      out.from = out.to;
      out.to = swap;
    }
    var months = ctx.months || [];
    if (months.length) {
      if (out.from && out.from < months[0]) { out.from = ''; }
      if (out.to && out.to > months[months.length - 1]) { out.to = ''; }
    }
    return out;
  }

  /**
   * Values of a state that this dataset does not contain (so they match no
   * site): {country, statuses, from, to}; empty strings/arrays when fine.
   */
  function unmatchedFilters(state, context) {
    var s = withDefaults(state);
    var ctx = context || {};
    var months = ctx.months || [];
    var first = months[0] || '';
    var last = months[months.length - 1] || '';
    return {
      country: s.country && (ctx.countryCodes || []).indexOf(s.country) === -1 ? s.country : '',
      statuses: s.status.filter(function (code) { return (ctx.statuses || []).indexOf(code) === -1; }),
      from: s.from && last && s.from > last ? s.from : '',
      to: s.to && first && s.to < first ? s.to : ''
    };
  }

  /** Number of active filters (search, country, statuses, locator, power, months). */
  function activeFilterCount(state) {
    var s = state || defaultState();
    var count = 0;
    if (cleanQuery(s.q)) { count += 1; }
    if (s.country) { count += 1; }
    if (s.status && s.status.length) { count += 1; }
    if (s.locator && s.locator !== 'any') { count += 1; }
    if (s.power) { count += 1; }
    if (s.from || s.to) { count += 1; }
    return count;
  }

  function matchesLocator(site, locator) {
    switch (locator) {
      case 'official_boundary':
        return site.officialBoundary;
      case 'polygon':
        return site.isArea;
      case 'point':
        return !site.isArea;
      default:
        return true;
    }
  }

  function monthInRange(month, from, to) {
    return !!month && (!from || month >= from) && (!to || month <= to);
  }

  function matchesMonths(months, from, to) {
    for (var i = 0; i < months.length; i++) {
      if (monthInRange(months[i], from, to)) {
        return true;
      }
    }
    return false;
  }

  /** Projects carry their own status and date; only then can both filters be checked per project. */
  function hasProjectStatuses(site) {
    return site.projects.length > 0 && site.projects.every(function (project) { return project.status; });
  }

  /**
   * Status codes of a site that were observed inside the month range: with a
   * range, one project must have both the status and a date in range (a
   * site whose shell observation is from May does not count as "shell in
   * August" because another project was observed in August).
   */
  function statusesInRange(site, from, to) {
    if ((!from && !to) || !hasProjectStatuses(site)) {
      return site.statuses;
    }
    return site.statuses.filter(function (code) {
      return site.projects.some(function (project) {
        return project.status === code && monthInRange(monthOf(project.statusAsOf), from, to);
      });
    });
  }

  function siteMatches(site, state, tokens, skip) {
    if (skip !== 'q' && tokens.length && !matchesTokens(site.searchText, tokens)) {
      return false;
    }
    if (skip !== 'country' && state.country && site.iso !== state.country) {
      return false;
    }
    var monthsActive = skip !== 'months' && !!(state.from || state.to);
    if (skip !== 'status' && state.status.length) {
      var codes = monthsActive ? statusesInRange(site, state.from, state.to) : site.statuses;
      var hit = false;
      for (var i = 0; i < codes.length && !hit; i++) {
        hit = state.status.indexOf(codes[i]) !== -1;
      }
      if (!hit) {
        return false;
      }
    }
    if (skip !== 'locator' && !matchesLocator(site, state.locator)) {
      return false;
    }
    if (skip !== 'power' && state.power && !site.hasPower) {
      return false;
    }
    if (monthsActive && !matchesMonths(site.months, state.from, state.to)) {
      return false;
    }
    return true;
  }

  function withDefaults(state) {
    var base = defaultState();
    var s = state || {};
    return {
      q: str(s.q),
      country: str(s.country),
      status: Array.isArray(s.status) ? s.status : [],
      locator: s.locator || base.locator,
      power: s.power === true,
      from: str(s.from),
      to: str(s.to),
      sort: s.sort || base.sort
    };
  }

  /** Sites matching every filter, in input order. */
  function filterSites(sites, state) {
    var s = withDefaults(state);
    var tokens = tokenize(s.q);
    return (sites || []).filter(function (site) { return siteMatches(site, s, tokens, null); });
  }

  /**
   * Disjunctive facet counts: each facet counts the sites that match every
   * *other* filter, so the numbers say what choosing that option would give.
   */
  function facetCounts(sites, state) {
    var s = withDefaults(state);
    var tokens = tokenize(s.q);
    var result = {
      total: 0,
      country: Object.create(null),
      status: Object.create(null),
      locator: { any: 0, official_boundary: 0, polygon: 0, point: 0 },
      power: 0
    };
    (sites || []).forEach(function (site) {
      if (siteMatches(site, s, tokens, null)) {
        result.total += 1;
      }
      if (siteMatches(site, s, tokens, 'country') && site.iso) {
        result.country[site.iso] = (result.country[site.iso] || 0) + 1;
      }
      if (siteMatches(site, s, tokens, 'status')) {
        statusesInRange(site, s.from, s.to).forEach(function (code) {
          result.status[code] = (result.status[code] || 0) + 1;
        });
      }
      if (siteMatches(site, s, tokens, 'locator')) {
        result.locator.any += 1;
        if (site.officialBoundary) { result.locator.official_boundary += 1; }
        if (site.isArea) { result.locator.polygon += 1; } else { result.locator.point += 1; }
      }
      if (siteMatches(site, s, tokens, 'power') && site.hasPower) {
        result.power += 1;
      }
    });
    return result;
  }

  // ---------------------------------------------------------------------------
  // Sorting
  // ---------------------------------------------------------------------------

  var collator = (typeof Intl !== 'undefined' && Intl.Collator)
    ? new Intl.Collator('en', { sensitivity: 'base', numeric: true })
    : null;

  function compareText(a, b) {
    return collator ? collator.compare(str(a), str(b)) : compareRaw(str(a).toLowerCase(), str(b).toLowerCase());
  }

  function byName(a, b) {
    return compareText(a.name, b.name) || compareRaw(a.id, b.id);
  }

  // Missing dates always sort last.
  function compareDates(a, b, descending) {
    if (!a || !b) {
      return (a ? 0 : 1) - (b ? 0 : 1);
    }
    return descending ? compareRaw(b, a) : compareRaw(a, b);
  }

  var SORTERS = {
    name: byName,
    country: function (a, b) { return compareText(a.country, b.country) || byName(a, b); },
    newest: function (a, b) { return compareDates(a.newest, b.newest, true) || byName(a, b); },
    oldest: function (a, b) { return compareDates(a.oldest, b.oldest, false) || byName(a, b); },
    projects: function (a, b) { return (b.projectCount - a.projectCount) || byName(a, b); }
  };

  /** New array sorted by one of name/country/newest/oldest/projects (ties by name, then id). */
  function sortSites(sites, key) {
    var sorter = hasOwn(SORTERS, key) ? SORTERS[key] : SORTERS.name;
    return (sites || []).slice().sort(sorter);
  }

  // ---------------------------------------------------------------------------
  // Export (CSV per RFC 4180, GeoJSON)
  // ---------------------------------------------------------------------------

  // The columns of the published per-country CSV files (the builder's
  // CSV_EXPORT_COLUMNS), plus dataset_id: the version the rows come from.
  // List columns hold compact JSON arrays: some publisher names contain ";"
  // or ",", so a joined string could not be split back.
  var CSV_COLUMNS = [
    'site_id', 'name', 'country', 'country_iso_a2', 'latitude', 'longitude', 'statuses_json',
    'newest_status_as_of', 'oldest_status_as_of', 'project_count', 'official_boundary', 'geometry_type',
    'status_publishers_json', 'geometry_licenses_json', 'url', 'api_url', 'dataset_id'
  ];

  // Characters that make a spreadsheet treat a cell as a formula (OWASP).
  var FORMULA_RE = /^[=+\-@\t\r]/;

  /** Prefix text that a spreadsheet would evaluate with an apostrophe. Text only. */
  function neutralizeFormula(text) {
    return FORMULA_RE.test(text) ? "'" + text : text;
  }

  /**
   * One CSV field. Numbers and booleans are written as-is (a negative
   * longitude stays a number); every string is formula-neutralised; fields
   * containing a quote, comma, CR or LF are quoted with doubled quotes.
   */
  function csvField(value) {
    var text;
    if (value === null || value === undefined) {
      text = '';
    } else if (typeof value === 'number') {
      text = isFinite(value) ? String(value) : '';
    } else if (typeof value === 'boolean') {
      text = value ? 'true' : 'false';
    } else {
      text = neutralizeFormula(String(value));
    }
    if (/[",\r\n]/.test(text)) {
      text = '"' + text.replace(/"/g, '""') + '"';
    }
    return text;
  }

  function csvRow(values) {
    return values.map(csvField).join(',');
  }

  function siteCsvValues(site, datasetId) {
    // Exports keep the dataset's own status order (display order is by colour group).
    var props = site.properties || {};
    var statuses = Array.isArray(props.statuses) ? uniqueStrings(props.statuses) : site.statuses;
    // Data without geometry_licenses leaves the cell empty: unknown, not "none".
    var licenses = Array.isArray(props.geometry_licenses) ? JSON.stringify(uniqueStrings(props.geometry_licenses)) : null;
    return [
      site.id,
      site.name,
      site.country,
      site.iso,
      site.lat,
      site.lon,
      JSON.stringify(statuses),
      site.newest,
      site.oldest,
      site.projectCount,
      site.officialBoundary,
      site.geometryType,
      JSON.stringify(site.publishers),
      licenses,
      site.url,
      site.apiUrl,
      datasetId
    ];
  }

  /**
   * CSV text (CRLF line endings, header row first) of prepared sites.
   * meta.datasetId fills the dataset_id column.
   */
  function sitesToCsv(sites, meta) {
    var datasetId = str(meta && meta.datasetId);
    var lines = [csvRow(CSV_COLUMNS)];
    (sites || []).forEach(function (site) { lines.push(csvRow(siteCsvValues(site, datasetId))); });
    return lines.join('\r\n') + '\r\n';
  }

  // Used only when neither sites.geojson nor the page bootstrap carries the
  // dataset's licence object (it mirrors DATA_LICENSE.md).
  var DEFAULT_EXPORT_LICENSE = {
    data: { id: 'CC-BY-4.0', url: 'https://creativecommons.org/licenses/by/4.0/' },
    openstreetmap_geometries: { id: 'ODbL-1.0', url: 'https://opendatacommons.org/licenses/odbl/1-0/' },
    third_party: 'Third-party facts, titles, URLs and geometries keep their source terms (each evidence record\'s license and attribution).'
  };

  function plainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value) ? value : null;
  }

  /**
   * Licence and attribution for an export, from the loaded sites.geojson
   * first, then the page bootstrap, then the built-in default. The
   * attribution names the dataset version and the attribution page.
   */
  function exportTerms(collection, boot) {
    var data = plainObject(collection) || {};
    var page = plainObject(boot) || {};
    var dataset = plainObject(page.dataset) || {};
    var base = safeHttpUrl(page.base_url);
    var license = plainObject(data.license) || plainObject(page.license) || DEFAULT_EXPORT_LICENSE;
    var attributionUrl = safeHttpUrl(page.attribution_url) || (base ? base.replace(/\/?$/, '/') + 'about/attribution/' : '');
    var attribution = typeof data.attribution === 'string' && data.attribution ? data.attribution
      : (typeof page.attribution === 'string' && page.attribution ? page.attribution : '');
    if (!attribution) {
      attribution = str(page.site_name || 'Data Center Atlas') + (base ? ', ' + base : '') +
        (dataset.id ? ' (dataset ' + str(dataset.id) + ')' : '') +
        '. Includes data © OpenStreetMap contributors (ODbL 1.0)' +
        (attributionUrl ? '; other source terms: ' + attributionUrl : '') + '.';
    }
    return { license: license, attribution: attribution, attribution_url: attributionUrl };
  }

  /**
   * GeoJSON FeatureCollection text of prepared sites with their original
   * summaries. Foreign members say what the file is and under which terms:
   * dataset, query, license, attribution, attribution_url, source_url (the
   * full collection), view_url (the explorer view that was exported) and
   * caveats (how to read the statuses and locators).
   */
  function sitesToGeoJSON(sites, meta) {
    var info = meta || {};
    var collection = {
      type: 'FeatureCollection',
      name: 'datacenter-atlas-sites',
      dataset: info.dataset || null,
      query: str(info.query),
      license: plainObject(info.license),
      attribution: str(info.attribution) || null,
      attribution_url: str(info.attribution_url) || null,
      source_url: str(info.source_url) || null,
      view_url: str(info.view_url) || null,
      caveats: Array.isArray(info.caveats) ? info.caveats.filter(function (text) { return typeof text === 'string'; }) : null,
      features: (sites || []).map(function (site) {
        var geometry = site.geometry || (site.hasLocation ? { type: 'Point', coordinates: [site.lon, site.lat] } : null);
        return { type: 'Feature', id: site.id, geometry: geometry, properties: site.properties };
      })
    };
    return JSON.stringify(collection) + '\n';
  }

  // ---------------------------------------------------------------------------
  // Agent tools (WebMCP): schemas, strict input validation, result records
  // ---------------------------------------------------------------------------

  var AGENT_CAVEATS = [
    'Each status is the last observed physical status as of a dated source (status_as_of), not the status today.',
    'Locators place a site on the map; they are not building footprints or construction extents.',
    'Unknown or missing values are unknown, not zero.',
    'This is a reviewed preview dataset, not a census of all data-centre construction.'
  ];
  var TOOL_SEARCH_KEYS = ['query', 'country', 'statuses', 'locator', 'has_power', 'from', 'to', 'sort', 'limit'];
  var TOOL_DEFAULT_LIMIT = 50;
  var TOOL_MAX_LIMIT = 200;
  var TOOL_SITE_ID_RE = /^vcc-site-[0-9a-f]{20}$/;

  /** JSON Schemas of the explorer's agent tools, with enums taken from the loaded data. */
  function agentToolSchemas(context) {
    var ctx = context || {};
    var month = { type: 'string', pattern: '^[0-9]{4}-(0[1-9]|1[0-2])$' };
    return {
      search: {
        type: 'object',
        properties: {
          query: { type: 'string', maxLength: MAX_QUERY_LENGTH, description: 'Words that must all start a word of the site name, country, country code, project names, status sources or site id (case and accents ignored).' },
          country: { type: 'string', enum: (ctx.countryCodes || []).slice(), description: 'ISO 3166-1 alpha-2 country code.' },
          statuses: { type: 'array', items: { type: 'string', enum: (ctx.statuses || []).slice() }, uniqueItems: true, description: 'Last observed physical status codes; a site matches when any of its projects has one.' },
          locator: { type: 'string', enum: LOCATORS.slice(), description: 'official_boundary, polygon (Polygon or MultiPolygon locator) or point.' },
          has_power: { type: 'boolean', description: 'Only sites with a reported power observation.' },
          from: { type: 'string', pattern: month.pattern, description: 'Earliest status_as_of month, YYYY-MM.' },
          to: { type: 'string', pattern: month.pattern, description: 'Latest status_as_of month, YYYY-MM.' },
          sort: { type: 'string', enum: SORTS.slice(), description: 'name (default), country, newest, oldest or projects.' },
          limit: { type: 'integer', minimum: 1, maximum: TOOL_MAX_LIMIT, default: TOOL_DEFAULT_LIMIT, description: 'Maximum number of sites returned.' }
        },
        additionalProperties: false
      },
      site: {
        type: 'object',
        properties: {
          site_id: { type: 'string', pattern: TOOL_SITE_ID_RE.source, description: 'Site id, e.g. from search_datacenter_sites.' }
        },
        required: ['site_id'],
        additionalProperties: false
      },
      dataset: { type: 'object', properties: {}, additionalProperties: false }
    };
  }

  function toolError(message) {
    return new Error(message);
  }

  function checkToolObject(input, allowed) {
    var value = input === undefined || input === null ? {} : input;
    if (typeof value !== 'object' || Array.isArray(value)) {
      throw toolError('Input must be a JSON object.');
    }
    Object.keys(value).forEach(function (key) {
      if (allowed.indexOf(key) === -1) {
        throw toolError('Unknown option "' + key + '". Allowed: ' + (allowed.join(', ') || 'none') + '.');
      }
    });
    return value;
  }

  /**
   * Validate search_datacenter_sites input strictly and turn it into an
   * explorer state plus a result limit. Unknown keys, codes outside the data
   * and malformed months are errors (agents get a reason, not a guess).
   */
  function toolInputToState(input, context) {
    var ctx = context || {};
    var value = checkToolObject(input, TOOL_SEARCH_KEYS);
    var state = defaultState();
    if (value.query !== undefined) {
      if (typeof value.query !== 'string' || value.query.length > MAX_QUERY_LENGTH) {
        throw toolError('query must be a string of at most ' + MAX_QUERY_LENGTH + ' characters.');
      }
      state.q = cleanQuery(value.query);
    }
    if (value.country !== undefined) {
      var country = typeof value.country === 'string' ? value.country.trim().toUpperCase() : '';
      if ((ctx.countryCodes || []).indexOf(country) === -1) {
        throw toolError('country must be one of the ISO codes in this dataset: ' + (ctx.countryCodes || []).join(', ') + '.');
      }
      state.country = country;
    }
    if (value.statuses !== undefined) {
      if (!Array.isArray(value.statuses)) {
        throw toolError('statuses must be an array of status codes.');
      }
      value.statuses.forEach(function (code) {
        if ((ctx.statuses || []).indexOf(code) === -1) {
          throw toolError('Unknown status "' + str(code) + '". Statuses in this dataset: ' + (ctx.statuses || []).join(', ') + '.');
        }
      });
      state.status = uniqueStrings(value.statuses);
    }
    if (value.locator !== undefined) {
      if (LOCATORS.indexOf(value.locator) === -1) {
        throw toolError('locator must be one of: ' + LOCATORS.join(', ') + '.');
      }
      state.locator = value.locator;
    }
    if (value.has_power !== undefined) {
      if (typeof value.has_power !== 'boolean') {
        throw toolError('has_power must be true or false.');
      }
      state.power = value.has_power;
    }
    ['from', 'to'].forEach(function (key) {
      if (value[key] !== undefined) {
        if (!isMonth(value[key])) {
          throw toolError(key + ' must be a month written YYYY-MM.');
        }
        state[key] = value[key];
      }
    });
    if (state.from && state.to && state.from > state.to) {
      throw toolError('from must not be later than to.');
    }
    if (value.sort !== undefined) {
      if (SORTS.indexOf(value.sort) === -1) {
        throw toolError('sort must be one of: ' + SORTS.join(', ') + '.');
      }
      state.sort = value.sort;
    }
    var limit = TOOL_DEFAULT_LIMIT;
    if (value.limit !== undefined) {
      if (typeof value.limit !== 'number' || Math.floor(value.limit) !== value.limit || value.limit < 1 || value.limit > TOOL_MAX_LIMIT) {
        throw toolError('limit must be a whole number from 1 to ' + TOOL_MAX_LIMIT + '.');
      }
      limit = value.limit;
    }
    return { state: normalizeState(state, ctx), limit: limit };
  }

  /** Validate get_datacenter_site input; returns the site id. */
  function toolSiteId(input) {
    var value = checkToolObject(input, ['site_id']);
    if (typeof value.site_id !== 'string' || !TOOL_SITE_ID_RE.test(value.site_id)) {
      throw toolError('site_id must look like vcc-site- followed by 20 hexadecimal characters.');
    }
    return value.site_id;
  }

  /** Compact, JSON-safe record of a prepared site for agent results. */
  function toolSiteSummary(site) {
    var props = site.properties || {};
    return {
      site_id: site.id,
      name: site.name,
      country: site.country,
      country_iso_a2: site.iso,
      latitude: site.lat,
      longitude: site.lon,
      statuses: Array.isArray(props.statuses) ? uniqueStrings(props.statuses) : site.statuses.slice(),
      newest_status_as_of: site.newest || null,
      oldest_status_as_of: site.oldest || null,
      project_count: site.projectCount,
      geometry_type: site.geometryType,
      official_boundary: site.officialBoundary,
      has_power_observation: site.hasPower,
      status_publishers: site.publishers.slice(),
      // Terms of the locator geometry (e.g. ODbL-1.0 for OpenStreetMap); null when the data does not say.
      geometry_licenses: Array.isArray(props.geometry_licenses) ? uniqueStrings(props.geometry_licenses) : null,
      url: site.url || null,
      api_url: site.apiUrl || null
    };
  }

  /** "datacenter-atlas-<dataset>-sites[-filtered].<ext>", safe for any OS. */
  function exportFilename(datasetId, filtered, extension) {
    var safe = str(datasetId).replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '');
    return 'datacenter-atlas-' + (safe ? safe + '-' : '') + 'sites' + (filtered ? '-filtered' : '') + '.' + extension;
  }

  // ---------------------------------------------------------------------------
  // Links
  // ---------------------------------------------------------------------------

  /** The URL when it is absolute http(s), normalised; otherwise "". */
  function safeHttpUrl(value) {
    if (typeof value !== 'string') {
      return '';
    }
    var text = value.trim();
    if (!/^https?:\/\//i.test(text)) {
      return '';
    }
    try {
      var url = new URL(text);
      return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : '';
    } catch (error) {
      return '';
    }
  }

  function formatCoordinate(value, digits) {
    var n = num(value);
    return n === null ? '' : n.toFixed(digits === undefined ? 6 : digits);
  }

  /** "View location" links (same patterns as the static site pages; 6 dp). */
  function externalMapLinks(lat, lon) {
    var la = num(lat);
    var lo = num(lon);
    if (la === null || lo === null || Math.abs(la) > 90 || Math.abs(lo) > 180) {
      return [];
    }
    var y = la.toFixed(6);
    var x = lo.toFixed(6);
    return [
      { id: 'osm', label: 'OpenStreetMap', url: 'https://www.openstreetmap.org/?mlat=' + y + '&mlon=' + x + '#map=16/' + y + '/' + x },
      { id: 'google', label: 'Google Maps', url: 'https://www.google.com/maps/search/?api=1&query=' + y + ',' + x },
      { id: 'bing', label: 'Bing aerial', url: 'https://www.bing.com/maps?cp=' + y + '~' + x + '&lvl=17&style=a' },
      { id: 'copernicus', label: 'Copernicus Browser', url: 'https://browser.dataspace.copernicus.eu/?zoom=15&lat=' + y + '&lng=' + x }
    ];
  }

  /** GitHub issue-form link for a correction to one site ("" if issuesUrl is not http(s)). */
  function correctionUrl(issuesUrl, siteName, siteId) {
    var base = safeHttpUrl(issuesUrl);
    if (!base) {
      return '';
    }
    return base.replace(/\/+$/, '') + '/new?template=correction.yml&title=' +
      encodeURIComponent('Correction: ' + str(siteName)) + '&site_id=' + encodeURIComponent(str(siteId));
  }

  // Canonical pages of the licence codes used in evidence records. Codes that
  // are not listed (custom or descriptive terms) stay plain text.
  var LICENSE_URLS = {
    'ODbL-1.0': 'https://opendatacommons.org/licenses/odbl/1-0/',
    'CC-BY-4.0': 'https://creativecommons.org/licenses/by/4.0/',
    'CC-BY-3.0': 'https://creativecommons.org/licenses/by/3.0/',
    'CC-BY-SA-2.0': 'https://creativecommons.org/licenses/by-sa/2.0/',
    'CC-BY-SA-4.0': 'https://creativecommons.org/licenses/by-sa/4.0/',
    'CC0-1.0': 'https://creativecommons.org/publicdomain/zero/1.0/',
    'Public-Domain-Mark-1.0': 'https://creativecommons.org/publicdomain/mark/1.0/',
    'dl-de/by-2-0': 'https://www.govdata.de/dl-de/by-2-0'
  };
  var OSM_COPYRIGHT_URL = 'https://www.openstreetmap.org/copyright';

  /** Canonical URL of a licence code, or "" when the code is not a known licence. */
  function licenseUrl(code) {
    var key = str(code).trim();
    return hasOwn(LICENSE_URLS, key) ? LICENSE_URLS[key] : '';
  }

  /** True when a licence/attribution pair is OpenStreetMap's (ODbL credit needed). */
  function isOpenStreetMapCredit(license, attribution) {
    return str(license).trim() === 'ODbL-1.0' || /openstreetmap/i.test(str(attribution));
  }

  /**
   * Relative prefix to the site root from a script's own src attribute
   * ("../../assets/site-map.js" -> "../../", "assets/app.js" -> "./"); ""
   * when the src is not a plain relative asset path (e.g. absolute).
   */
  function rootFromAssetSrc(src) {
    var match = /^(\.\/|(?:\.\.\/){1,8})?assets\/[A-Za-z0-9._-]+\.js(?:[?#].*)?$/.exec(str(src));
    return match ? (match[1] || './') : '';
  }

  function escapeAttribute(value) {
    return str(value).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  /**
   * HTML snippet (text to copy, never inserted into this page) that embeds
   * an explorer view in another page. "" unless src is an http(s) URL.
   */
  function embedSnippet(src, title) {
    var url = safeHttpUrl(src);
    if (!url) {
      return '';
    }
    return '<iframe src="' + escapeAttribute(url) + '" title="' + escapeAttribute(title || 'Data Center Atlas map') +
      '" width="100%" height="560" style="border:0" loading="lazy" referrerpolicy="strict-origin-when-cross-origin"></iframe>';
  }

  /** Relative URL under the site root, e.g. ("../", "sites/x/") -> "../sites/x/". */
  function joinRoot(root, path) {
    var prefix = str(root) || './';
    if (prefix.charAt(prefix.length - 1) !== '/') {
      prefix += '/';
    }
    return prefix + str(path).replace(/^\/+/, '');
  }

  /** Replace {name} placeholders with URL-encoded values; unknown placeholders stay. */
  function fillTemplate(template, values) {
    return str(template).replace(/\{([a-z0-9_]+)\}/gi, function (match, key) {
      return hasOwn(values, key) ? encodeURIComponent(str(values[key])) : match;
    });
  }

  // ---------------------------------------------------------------------------
  // Power observations
  // ---------------------------------------------------------------------------

  /** "low-high unit" when the bounds differ, else the single value with its unit. */
  function formatPowerValue(observation) {
    var obs = observation || {};
    var low = num(obs.low);
    var base = num(obs.base);
    var high = num(obs.high);
    var unit = str(obs.unit);
    var text;
    if (low !== null && high !== null && low !== high) {
      text = formatNumber(low) + '\u2013' + formatNumber(high);
    } else if (base !== null) {
      text = formatNumber(base);
    } else if (low !== null) {
      text = formatNumber(low);
    } else if (high !== null) {
      text = formatNumber(high);
    } else {
      return '';
    }
    return unit ? text + ' ' + unit : text;
  }

  // ---------------------------------------------------------------------------
  // Basemaps (shared by the explorer and the site-page map)
  // ---------------------------------------------------------------------------

  // Every name and attribution below is a constant: Leaflet writes both with
  // innerHTML (layer control, attribution control). Nothing from the dataset
  // or the page may reach them; site/js-tests/static-assets.test.mjs checks.
  var OSM_COPYRIGHT = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
  // The OSM tile usage policy asks for a "Report a map issue" link.
  var OSM_ATTRIBUTION = OSM_COPYRIGHT + ' &middot; <a href="https://www.openstreetmap.org/fixthemap">Report a map issue</a>';
  var CARTO_ATTRIBUTION = OSM_COPYRIGHT + ' &copy; <a href="https://carto.com/attributions">CARTO</a>';
  // EOX's required attribution for the 2025 layer, with EOX's own links,
  // plus the licence (layers from 2018 on are CC BY-NC-SA 4.0).
  var EOX_ATTRIBUTION = '<a href="https://cloudless.eox.at">EOxCloudless</a> ' +
    '<a href="https://cloudless.eox.at">https://cloudless.eox.at</a> by ' +
    '<a href="https://eox.at">EOX IT Services GmbH</a> (Contains modified Copernicus Sentinel data 2025), ' +
    '<a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">CC BY-NC-SA 4.0</a>';

  var OSM_BASEMAP = {
    id: 'osm',
    name: 'OpenStreetMap',
    role: 'light',
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    dark: false,
    options: {
      maxZoom: 19,
      attribution: OSM_ATTRIBUTION
    }
  };
  // The same OpenStreetMap tiles, darkened in the browser by a CSS filter
  // (.atlas-tiles-dark in site.css): a dark map that needs no API key.
  var OSM_DARK_BASEMAP = {
    id: 'osm-dark',
    name: 'OpenStreetMap, dark',
    role: 'dark',
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    dark: true,
    options: {
      maxZoom: 19,
      className: 'atlas-tiles-dark',
      attribution: OSM_ATTRIBUTION
    }
  };
  var SATELLITE_BASEMAP = {
    // Newest s2cloudless layer in the EOX WMTS capabilities (checked
    // 2026-10-09): tiles exist up to z18, z19+ return 404.
    id: 'satellite',
    name: 'Satellite (Sentinel-2 cloudless)',
    role: '',
    url: 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2025_3857/default/g/{z}/{y}/{x}.jpg',
    dark: true,
    options: {
      maxZoom: 19,
      maxNativeZoom: 18,
      attribution: EOX_ATTRIBUTION
    }
  };
  // CARTO raster basemaps need an API key (keyless requests get "API KEY
  // REQUIRED" watermark tiles), so they are offered only when the page
  // passes one. Keys are referrer-restricted public keys; only URL-safe
  // characters are accepted, and the key only ever goes into the tile URL.
  var CARTO_STYLES = [
    { id: 'light', name: 'Light (CARTO)', role: 'light', style: 'light_all', dark: false },
    { id: 'dark', name: 'Dark (CARTO)', role: 'dark', style: 'dark_all', dark: true }
  ];
  var CARTO_KEY_RE = /^[A-Za-z0-9._~-]{8,256}$/;
  var KNOWN_BASEMAP_IDS = ['light', 'dark', 'osm', 'osm-dark', 'satellite'];
  var BASEMAP_STORAGE_KEY = 'datacenter-atlas:basemap';

  /** The CARTO key when it is a plausible URL-safe key, else "". */
  function cartoKey(value) {
    var key = typeof value === 'string' ? value.trim() : '';
    return CARTO_KEY_RE.test(key) ? key : '';
  }

  /**
   * Basemaps available on a page: CARTO Light/Dark first when a CARTO key is
   * configured, then OpenStreetMap (plus its darkened variant when CARTO Dark
   * is not available) and the Sentinel-2 satellite layer. New objects every
   * call, so callers may hand the options straight to Leaflet.
   */
  function basemapsFor(options) {
    var key = cartoKey(options && options.cartoKey);
    var list = [];
    if (key) {
      CARTO_STYLES.forEach(function (style) {
        list.push({
          id: style.id,
          name: style.name,
          role: style.role,
          url: 'https://{s}.basemaps.cartocdn.com/' + style.style + '/{z}/{x}/{y}{r}.png?key=' + encodeURIComponent(key),
          dark: style.dark,
          options: { subdomains: 'abcd', maxZoom: 19, attribution: CARTO_ATTRIBUTION }
        });
      });
    }
    list.push(OSM_BASEMAP);
    if (!key) {
      list.push(OSM_DARK_BASEMAP);
    }
    list.push(SATELLITE_BASEMAP);
    return list.map(function (basemap) {
      var copy = {};
      Object.keys(basemap).forEach(function (name) { copy[name] = basemap[name]; });
      copy.options = {};
      Object.keys(basemap.options).forEach(function (name) { copy.options[name] = basemap.options[name]; });
      return copy;
    });
  }

  // What a page without a CARTO key offers (the default deployment).
  var BASEMAPS = basemapsFor({});

  function findBasemap(id, basemaps) {
    var list = Array.isArray(basemaps) ? basemaps : BASEMAPS;
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) {
        return list[i];
      }
    }
    return null;
  }

  function roleOf(id) {
    if (id === 'light' || id === 'osm') {
      return 'light';
    }
    if (id === 'dark' || id === 'osm-dark') {
      return 'dark';
    }
    return '';
  }

  /** First available basemap for a light/dark role (CARTO first when present). */
  function basemapForRole(role, basemaps) {
    var list = Array.isArray(basemaps) ? basemaps : BASEMAPS;
    for (var i = 0; i < list.length; i++) {
      if (list[i].role === role) {
        return list[i].id;
      }
    }
    return list.length ? list[0].id : '';
  }

  /**
   * The stored choice when it is available on this page; a stored light or
   * dark choice whose provider is not configured keeps its role (e.g. CARTO
   * "dark" becomes the darkened OpenStreetMap); otherwise light or dark from
   * prefers-color-scheme.
   */
  function chooseBasemap(storedId, prefersDark, basemaps) {
    if (findBasemap(storedId, basemaps)) {
      return storedId;
    }
    var role = roleOf(storedId) || (prefersDark ? 'dark' : 'light');
    return basemapForRole(role, basemaps);
  }

  /** The stored basemap id when it is one this site has ever offered, else "". */
  function readStoredBasemap(storage) {
    try {
      var value = storage ? storage.getItem(BASEMAP_STORAGE_KEY) : null;
      return KNOWN_BASEMAP_IDS.indexOf(value) !== -1 ? value : '';
    } catch (error) {
      return '';
    }
  }

  function storeBasemap(storage, id) {
    try {
      if (storage && KNOWN_BASEMAP_IDS.indexOf(id) !== -1) {
        storage.setItem(BASEMAP_STORAGE_KEY, id);
        return true;
      }
    } catch (error) {
      // Storage can be unavailable (privacy mode, quota); the choice is cosmetic.
    }
    return false;
  }

  /** Same-origin relative prefix to the site root: "./" or "../" repeated. */
  var ROOT_PREFIX_RE = /^(?:\.\/|(?:\.\.\/){1,8})$/;

  /**
   * Permanent map credit for the Atlas's own layer (markers and outlines):
   * the data licence and the OpenStreetMap credit that ODbL requires for the
   * OSM-derived geometries, whatever basemap is shown. `root` must be a
   * relative prefix such as "./" or "../../"; anything else drops the link.
   */
  function dataCredit(root) {
    var atlas = ROOT_PREFIX_RE.test(root) ? '<a href="' + root + 'about/attribution/">Data Center Atlas</a>' : 'Data Center Atlas';
    return 'Sites: ' + atlas + ' (CC BY 4.0 + source terms); some geometries ' + OSM_COPYRIGHT + ' (ODbL)';
  }

  return Object.freeze({
    version: '2',
    LIFECYCLE_ORDER: LIFECYCLE_ORDER,
    STATUS_GROUPS: STATUS_GROUPS,
    OTHER_GROUP: OTHER_GROUP,
    LOCATORS: LOCATORS,
    SORTS: SORTS,
    CSV_COLUMNS: CSV_COLUMNS,
    BASEMAPS: BASEMAPS,
    BASEMAP_STORAGE_KEY: BASEMAP_STORAGE_KEY,
    DEFAULT_EXPORT_LICENSE: DEFAULT_EXPORT_LICENSE,
    AGENT_CAVEATS: AGENT_CAVEATS,
    statusGroup: statusGroup,
    sortStatusCodes: sortStatusCodes,
    statusLabel: statusLabel,
    vocabLabel: vocabLabel,
    vocabDescription: vocabDescription,
    humanizeCode: humanizeCode,
    isoDate: isoDate,
    isMonth: isMonth,
    monthOf: monthOf,
    monthRange: monthRange,
    formatMonth: formatMonth,
    isoDateMinusDays: isoDateMinusDays,
    formatNumber: formatNumber,
    formatCoordinate: formatCoordinate,
    plural: plural,
    normalizeText: normalizeText,
    tokenize: tokenize,
    matchesTokens: matchesTokens,
    buildSearchText: buildSearchText,
    validGeometry: validGeometry,
    geometryLatLngs: geometryLatLngs,
    geometryBounds: geometryBounds,
    nearestPoint: nearestPoint,
    primaryStatus: primaryStatus,
    prepareSite: prepareSite,
    prepareSites: prepareSites,
    buildContext: buildContext,
    defaultState: defaultState,
    parseQuery: parseQuery,
    parseHash: parseHash,
    buildHash: buildHash,
    serializeState: serializeState,
    normalizeState: normalizeState,
    unmatchedFilters: unmatchedFilters,
    activeFilterCount: activeFilterCount,
    statusesInRange: statusesInRange,
    filterSites: filterSites,
    facetCounts: facetCounts,
    compareText: compareText,
    sortSites: sortSites,
    neutralizeFormula: neutralizeFormula,
    csvField: csvField,
    sitesToCsv: sitesToCsv,
    exportTerms: exportTerms,
    sitesToGeoJSON: sitesToGeoJSON,
    exportFilename: exportFilename,
    agentToolSchemas: agentToolSchemas,
    toolInputToState: toolInputToState,
    toolSiteId: toolSiteId,
    toolSiteSummary: toolSiteSummary,
    safeHttpUrl: safeHttpUrl,
    externalMapLinks: externalMapLinks,
    correctionUrl: correctionUrl,
    licenseUrl: licenseUrl,
    isOpenStreetMapCredit: isOpenStreetMapCredit,
    OSM_COPYRIGHT_URL: OSM_COPYRIGHT_URL,
    rootFromAssetSrc: rootFromAssetSrc,
    embedSnippet: embedSnippet,
    joinRoot: joinRoot,
    fillTemplate: fillTemplate,
    formatPowerValue: formatPowerValue,
    cartoKey: cartoKey,
    basemapsFor: basemapsFor,
    findBasemap: findBasemap,
    basemapForRole: basemapForRole,
    chooseBasemap: chooseBasemap,
    readStoredBasemap: readStoredBasemap,
    storeBasemap: storeBasemap,
    dataCredit: dataCredit
  });
});
