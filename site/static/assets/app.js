/*
 * Data Center Atlas explorer: map + filterable list + detail drawer.
 *
 * Reads #atlas-bootstrap, loads api/v1/sites.geojson, and keeps the view in
 * the URL (?q=&country=&status=&locator=&power=&from=&to=&sort= and
 * #site=<id>). All data logic lives in atlas-core.js (window.AtlasCore),
 * which is loaded from next to this file when the page does not include it.
 * Every dataset value is untrusted: the DOM is built with createElement and
 * textContent, and only http(s) URLs become external hrefs.
 */
(function () {
  'use strict';

  var script = document.currentScript;
  var DOC_TOKEN = 'atlas-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
  var RADIUS = { base: 5, hover: 7, selected: 8 };
  var NEAR_PX = 14;
  var TAP_PX = 22;
  var FILTERS_OPEN_KEY = 'datacenter-atlas:filters-open';

  function onReady(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  function withCore(callback) {
    if (window.AtlasCore) {
      callback(window.AtlasCore);
      return;
    }
    var src = script && script.src ? new URL('atlas-core.js', script.src).href : '';
    if (!src) {
      callback(null);
      return;
    }
    var tag = document.createElement('script');
    tag.src = src;
    tag.async = true;
    tag.onload = function () { callback(window.AtlasCore || null); };
    tag.onerror = function () { callback(null); };
    document.head.appendChild(tag);
  }

  function readBootstrap() {
    var el = document.getElementById('atlas-bootstrap');
    if (!el) {
      return {};
    }
    try {
      var data = JSON.parse(el.textContent || '{}');
      return data && typeof data === 'object' ? data : {};
    } catch (error) {
      return {};
    }
  }

  function safeStorage() {
    try {
      return window.localStorage;
    } catch (error) {
      return null;
    }
  }

  function media(query) {
    if (window.matchMedia) {
      return window.matchMedia(query);
    }
    return { matches: false, addEventListener: function () {} };
  }

  function onMediaChange(list, handler) {
    if (typeof list.addEventListener === 'function') {
      list.addEventListener('change', handler);
    } else if (typeof list.addListener === 'function') {
      list.addListener(handler);
    }
  }

  /** Endpoint path relative to the site root ("" when it points elsewhere). */
  function rootRelative(value, fallback, baseUrl) {
    if (typeof value !== 'string' || !value) {
      return fallback;
    }
    if (/^[a-z][a-z0-9+.-]*:/i.test(value) || value.indexOf('//') === 0) {
      return baseUrl && value.indexOf(baseUrl) === 0 ? value.slice(baseUrl.length) : fallback;
    }
    return value.replace(/^\/+/, '');
  }

  /** Start downloading sites.geojson at once, in parallel with atlas-core.js. */
  function prefetchSites() {
    var boot = readBootstrap();
    var root = typeof boot.root === 'string' && boot.root ? boot.root : './';
    if (root.charAt(root.length - 1) !== '/') {
      root += '/';
    }
    var endpoints = boot.endpoints && typeof boot.endpoints === 'object' ? boot.endpoints : {};
    var baseUrl = typeof boot.base_url === 'string' ? boot.base_url : '';
    var url = root + rootRelative(endpoints.sites_geojson, 'api/v1/sites.geojson', baseUrl);
    var promise = window.fetch(url, { credentials: 'same-origin' }).then(function (response) {
      if (!response.ok) {
        throw new Error('HTTP ' + response.status);
      }
      return response.json();
    });
    // Mark as handled now; start() attaches the real handlers.
    promise.catch(function () {});
    return promise;
  }

  onReady(function () {
    var sitesPromise = document.getElementById('atlas-app') && window.fetch ? prefetchSites() : null;
    withCore(function (Core) {
      var app = document.getElementById('atlas-app');
      if (!app) {
        return;
      }
      if (!Core || !sitesPromise) {
        app.hidden = false;
        var error = document.getElementById('atlas-error');
        var loading = document.getElementById('atlas-loading');
        if (error) { error.hidden = false; }
        if (loading) { loading.hidden = true; }
        return;
      }
      start(Core, sitesPromise);
    });
  });

  function start(Core, sitesPromise) {
    var boot = readBootstrap();
    var root = typeof boot.root === 'string' && boot.root ? boot.root : './';
    var baseUrl = typeof boot.base_url === 'string' ? boot.base_url : '';
    var endpoints = boot.endpoints && typeof boot.endpoints === 'object' ? boot.endpoints : {};
    var vocab = boot.vocabularies && typeof boot.vocabularies === 'object' ? boot.vocabularies : {};
    var dataset = boot.dataset && typeof boot.dataset === 'object' ? boot.dataset : {};
    var store = safeStorage();

    var E = {};
    ['app', 'panel', 'filters', 'more', 'search', 'country', 'status', 'status-options', 'locator', 'power',
      'power-count', 'from', 'to', 'sort', 'clear', 'active-count', 'count', 'count-total', 'list', 'empty',
      'empty-clear', 'error', 'loading', 'map', 'mapwrap', 'fit', 'legend', 'legend-list', 'detail',
      'detail-title', 'detail-kicker', 'detail-body', 'detail-close', 'export-csv', 'export-geojson',
      'copy-link', 'tabs', 'tab-list', 'tab-map', 'announce'
    ].forEach(function (id) {
      var key = id.replace(/-([a-z])/g, function (m, c) { return c.toUpperCase(); });
      E[key] = document.getElementById('atlas-' + id);
    });
    if (!E.list || !E.count || !E.detail || !E.detailBody || !E.search) {
      return;
    }

    var S = {
      ready: false,
      sites: [],
      byId: Object.create(null),
      context: null,
      state: Core.defaultState(),
      visible: [],
      visibleIds: Object.create(null),
      rows: Object.create(null),
      tips: Object.create(null),
      docs: Object.create(null),
      selectedId: '',
      hoverId: '',
      hover: { marker: '', near: '', polygon: '', list: '' },
      tabStopId: '',
      origin: null,
      detailToken: 0,
      urlTimer: 0,
      closingViaBack: false,
      closingTimer: 0,
      baseTitle: document.title,
      map: null,
      tooltip: null,
      baseLayers: {},
      basemapId: '',
      basemapExplicit: false,
      markers: Object.create(null),
      polygons: Object.create(null),
      markerLayer: null,
      polygonLayer: null,
      userMoved: false,
      programmatic: 0,
      pendingView: null,
      moveFrame: 0,
      lastMove: null,
      view: 'list',
      narrow: media('(max-width: 1023.98px)'),
      reduce: media('(prefers-reduced-motion: reduce)'),
      dark: media('(prefers-color-scheme: dark)')
    };

    // -------------------------------------------------------------------------
    // DOM helpers
    // -------------------------------------------------------------------------

    function h(tag, className, text) {
      var el = document.createElement(tag);
      if (className) {
        el.className = className;
      }
      if (text !== undefined && text !== null && text !== '') {
        el.textContent = String(text);
      }
      return el;
    }

    function textNode(text) {
      return document.createTextNode(String(text));
    }

    function srOnly(text) {
      return h('span', 'sr-only', text);
    }

    function classToken(value) {
      return String(value || '').replace(/[^A-Za-z0-9_-]/g, '');
    }

    function externalLink(href, text, className) {
      var url = Core.safeHttpUrl(href);
      if (!url) {
        return h('span', className, text);
      }
      var a = h('a', (className ? className + ' ' : '') + 'external', text || url);
      a.href = url;
      a.rel = 'noopener';
      return a;
    }

    function internalLink(path, text, className) {
      var a = h('a', className, text);
      a.href = Core.joinRoot(root, path);
      return a;
    }

    function badge(code) {
      return h('span', 'badge status-' + classToken(code), Core.statusLabel(code, vocab));
    }

    function tag(text, className) {
      return h('span', 'tag' + (className ? ' ' + className : ''), text);
    }

    function announce(message) {
      if (!E.announce) {
        return;
      }
      E.announce.textContent = '';
      window.setTimeout(function () { E.announce.textContent = message; }, 40);
    }

    function relativeEndpoint(value, fallback) {
      return rootRelative(value, fallback, baseUrl);
    }

    function siteDocUrl(id) {
      var template = relativeEndpoint(endpoints.site, 'api/v1/sites/{site_id}.json');
      return Core.joinRoot(root, Core.fillTemplate(template, { site_id: id }));
    }

    function sitePagePath(id) {
      var template = boot.pages && typeof boot.pages.site === 'string' ? relativeEndpoint(boot.pages.site, '') : '';
      return template ? Core.fillTemplate(template, { site_id: id }) : 'sites/' + encodeURIComponent(id) + '/';
    }

    function fetchJSON(url) {
      return window.fetch(url, { credentials: 'same-origin' }).then(function (response) {
        if (!response.ok) {
          throw new Error('HTTP ' + response.status);
        }
        return response.json();
      });
    }

    // -------------------------------------------------------------------------
    // Clipboard and downloads
    // -------------------------------------------------------------------------

    function legacyCopy(text) {
      var area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.style.position = 'fixed';
      area.style.top = '0';
      area.style.left = '0';
      area.style.opacity = '0';
      area.style.pointerEvents = 'none';
      document.body.appendChild(area);
      area.select();
      var ok = false;
      try {
        ok = document.execCommand('copy');
      } catch (error) {
        ok = false;
      }
      document.body.removeChild(area);
      return ok;
    }

    function copyText(text) {
      if (navigator.clipboard && window.isSecureContext) {
        return navigator.clipboard.writeText(text).catch(function () {
          if (!legacyCopy(text)) {
            throw new Error('copy failed');
          }
        });
      }
      return legacyCopy(text) ? Promise.resolve() : Promise.reject(new Error('copy failed'));
    }

    var flashing = typeof WeakMap === 'function' ? new WeakMap() : null;

    function flash(button, label) {
      if (!flashing || !button) {
        return;
      }
      var saved = flashing.get(button);
      if (!saved) {
        saved = { nodes: Array.prototype.slice.call(button.childNodes), timer: 0 };
        flashing.set(button, saved);
      }
      window.clearTimeout(saved.timer);
      button.textContent = label;
      button.classList.add('is-copied');
      saved.timer = window.setTimeout(function () {
        button.textContent = '';
        saved.nodes.forEach(function (node) { button.appendChild(node); });
        button.classList.remove('is-copied');
        flashing.delete(button);
      }, 1800);
    }

    function copyWithFeedback(text, button, doneMessage) {
      copyText(text).then(function () {
        flash(button, 'Copied');
        announce(doneMessage);
      }, function () {
        window.prompt('Copy this text:', text);
      });
    }

    function download(text, filename, type) {
      var blob = new Blob([text], { type: type });
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.hidden = true;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.setTimeout(function () { URL.revokeObjectURL(url); }, 30000);
      announce('Downloaded ' + filename);
    }

    // -------------------------------------------------------------------------
    // URL state and history
    // -------------------------------------------------------------------------

    function urlFor(siteId) {
      return window.location.pathname + Core.serializeState(S.state) + Core.buildHash(siteId);
    }

    function replaceUrl(stateObject, url) {
      try {
        window.history.replaceState(stateObject, '', url);
      } catch (error) {
        // Some browsers rate-limit history calls; the view itself is unaffected.
      }
    }

    function flushUrl() {
      window.clearTimeout(S.urlTimer);
      S.urlTimer = 0;
      var url = urlFor(S.selectedId);
      var current = window.location.pathname + window.location.search + window.location.hash;
      if (url !== current) {
        replaceUrl(window.history.state, url);
      }
    }

    function scheduleUrl(delay) {
      window.clearTimeout(S.urlTimer);
      S.urlTimer = window.setTimeout(flushUrl, delay);
    }

    function ownHistoryState() {
      var hs = window.history.state;
      return hs && typeof hs === 'object' && hs.atlasDoc === DOC_TOKEN ? hs : null;
    }

    /** Opening a site adds one history entry; switching sites replaces it. */
    function pushSiteState(id, wasOpen) {
      window.clearTimeout(S.urlTimer);
      var own = ownHistoryState();
      if (wasOpen || (own && own.atlasSite)) {
        replaceUrl({ atlasDoc: DOC_TOKEN, atlasSite: id, atlasPushed: !!(own && own.atlasPushed) }, urlFor(id));
        return;
      }
      replaceUrl(window.history.state, urlFor(''));
      try {
        window.history.pushState({ atlasDoc: DOC_TOKEN, atlasSite: id, atlasPushed: true }, '', urlFor(id));
      } catch (error) {
        replaceUrl(null, urlFor(id));
      }
    }

    /** Closing goes back to the entry the site was opened from, keeping current filters. */
    function leaveSiteState() {
      window.clearTimeout(S.urlTimer);
      var own = ownHistoryState();
      if (own && own.atlasPushed) {
        S.closingViaBack = true;
        window.clearTimeout(S.closingTimer);
        S.closingTimer = window.setTimeout(function () { S.closingViaBack = false; }, 1500);
        window.history.back();
      } else {
        replaceUrl(null, urlFor(''));
      }
    }

    function onPopState() {
      if (S.closingViaBack) {
        S.closingViaBack = false;
        window.clearTimeout(S.closingTimer);
        replaceUrl(window.history.state, urlFor(''));
        return;
      }
      if (S.ready) {
        applyLocation(false);
      }
    }

    function applyLocation(initial) {
      var next = Core.normalizeState(Core.parseQuery(window.location.search), S.context);
      var changed = initial || Core.serializeState(next) !== Core.serializeState(S.state);
      S.state = next;
      if (changed) {
        syncControls(false);
        if (Core.activeFilterCount(S.state) && E.more) {
          E.more.open = true;
        }
        render({ fit: true, animate: !initial });
      }
      var siteId = Core.parseHash(window.location.hash);
      if (siteId && S.byId[siteId]) {
        if (siteId !== S.selectedId || E.detail.hidden) {
          openSite(siteId, { history: false, zoom: true, origin: null, focus: !initial, animate: !initial });
        }
      } else if (!E.detail.hidden) {
        closeDetail({ history: false, restoreFocus: false });
      }
      if (initial) {
        replaceUrl(window.history.state, urlFor(S.selectedId));
      }
    }

    // -------------------------------------------------------------------------
    // Filters
    // -------------------------------------------------------------------------

    function checkedStatuses() {
      var codes = [];
      Array.prototype.forEach.call(E.status.querySelectorAll('input[name="status"]'), function (input) {
        if (input.checked) {
          codes.push(input.value);
        }
      });
      return codes;
    }

    function syncControls(skipSearch) {
      var st = S.state;
      if (!skipSearch && E.search.value !== st.q) {
        E.search.value = st.q;
      }
      if (E.country) { E.country.value = st.country; }
      if (E.status) {
        Array.prototype.forEach.call(E.status.querySelectorAll('input[name="status"]'), function (input) {
          input.checked = st.status.indexOf(input.value) !== -1;
        });
      }
      if (E.locator) { E.locator.value = st.locator; }
      if (E.power) { E.power.checked = st.power; }
      if (E.from) { E.from.value = st.from; }
      if (E.to) { E.to.value = st.to; }
      if (E.sort) { E.sort.value = st.sort; }
    }

    function onFilterChange(options) {
      var opts = options || {};
      if (!S.ready) {
        return;
      }
      S.state = Core.normalizeState(S.state, S.context);
      syncControls(true);
      render({ fit: opts.fit !== false, animate: true });
      scheduleUrl(opts.typing ? 400 : 60);
    }

    function clearFilters() {
      if (!S.ready) {
        return;
      }
      var sort = S.state.sort;
      S.state = Core.defaultState();
      S.state.sort = sort;
      syncControls(false);
      S.userMoved = false;
      render({ fit: true, animate: true });
      scheduleUrl(0);
      announce('Filters cleared');
    }

    function optionCount(select, value, text) {
      for (var i = 0; i < select.options.length; i++) {
        if (select.options[i].value === value) {
          if (select.options[i].textContent !== text) {
            select.options[i].textContent = text;
          }
          return;
        }
      }
    }

    function buildFilterOptions() {
      var ctx = S.context;
      if (E.country) {
        while (E.country.options.length > 1) {
          E.country.remove(1);
        }
        ctx.countries.forEach(function (country) {
          var option = h('option', '', country.name + ' (' + country.count + ')');
          option.value = country.iso;
          E.country.appendChild(option);
        });
      }
      if (E.statusOptions) {
        E.statusOptions.textContent = '';
        ctx.statuses.forEach(function (code) {
          var label = h('label', 'atlas-chip');
          var input = h('input');
          input.type = 'checkbox';
          input.name = 'status';
          input.value = code;
          var swatch = h('span', 'atlas-swatch atlas-grp-' + Core.statusGroup(code).id);
          swatch.setAttribute('aria-hidden', 'true');
          var count = h('span', 'atlas-chip-count');
          count.setAttribute('data-status-count', code);
          label.appendChild(input);
          label.appendChild(swatch);
          label.appendChild(h('span', 'atlas-chip-label', Core.statusLabel(code, vocab)));
          label.appendChild(count);
          var description = Core.vocabDescription(vocab, 'statuses', code);
          if (description) {
            label.title = description;
          }
          E.statusOptions.appendChild(label);
        });
      }
      [E.from, E.to].forEach(function (select) {
        if (!select) {
          return;
        }
        while (select.options.length > 1) {
          select.remove(1);
        }
        ctx.months.forEach(function (month) {
          var option = h('option', '', Core.formatMonth(month));
          option.value = month;
          select.appendChild(option);
        });
      });
    }

    function updateFacets(facets) {
      if (E.country) {
        var anyCountry = 0;
        S.context.countries.forEach(function (country) {
          var n = facets.country[country.iso] || 0;
          anyCountry += n;
          optionCount(E.country, country.iso, country.name + ' (' + n + ')');
        });
        optionCount(E.country, '', 'All countries (' + anyCountry + ')');
      }
      if (E.statusOptions) {
        Array.prototype.forEach.call(E.statusOptions.querySelectorAll('[data-status-count]'), function (el) {
          var n = facets.status[el.getAttribute('data-status-count')] || 0;
          el.textContent = '';
          el.appendChild(srOnly(', '));
          el.appendChild(textNode(n));
          el.appendChild(srOnly(n === 1 ? ' site' : ' sites'));
          el.parentNode.classList.toggle('is-empty', n === 0);
        });
      }
      if (E.locator) {
        optionCount(E.locator, 'any', 'Any locator (' + facets.locator.any + ')');
        optionCount(E.locator, 'official_boundary', 'Official boundary (' + facets.locator.official_boundary + ')');
        optionCount(E.locator, 'polygon', 'Polygon or MultiPolygon (' + facets.locator.polygon + ')');
        optionCount(E.locator, 'point', 'Point (' + facets.locator.point + ')');
      }
      if (E.powerCount) {
        E.powerCount.textContent = '(' + facets.power + ')';
      }
    }

    function updateSummary() {
      var n = S.visible.length;
      var total = S.sites.length;
      E.count.textContent = Core.plural(n, 'site');
      if (E.countTotal) {
        E.countTotal.textContent = n === total ? '' : ' of ' + total;
      }
      var active = Core.activeFilterCount(S.state);
      if (E.activeCount) {
        E.activeCount.textContent = active ? active + ' active' : '';
      }
      if (E.app) {
        E.app.classList.toggle('has-filters', active > 0);
      }
    }

    // -------------------------------------------------------------------------
    // Results list
    // -------------------------------------------------------------------------

    function rowFor(site) {
      var row = S.rows[site.id];
      if (row) {
        return row;
      }
      row = h('li', 'atlas-row');
      row.setAttribute('data-site-id', site.id);
      var button = h('button', 'atlas-row-btn');
      button.type = 'button';
      button.tabIndex = -1;
      var swatch = h('span', 'atlas-swatch atlas-grp-' + Core.statusGroup(site.primaryStatus).id);
      swatch.setAttribute('aria-hidden', 'true');
      var body = h('span', 'atlas-row-body');
      body.appendChild(h('span', 'atlas-row-name', site.name));
      var meta = h('span', 'atlas-row-meta');
      meta.appendChild(h('span', 'atlas-row-country', site.country || site.iso));
      if (site.newest) {
        meta.appendChild(h('span', 'atlas-row-date', 'as of ' + site.newest));
      }
      if (site.projectCount > 1) {
        meta.appendChild(h('span', 'atlas-row-projects', Core.plural(site.projectCount, 'project')));
      }
      body.appendChild(meta);
      var badges = h('span', 'atlas-row-badges');
      site.statuses.forEach(function (code) { badges.appendChild(badge(code)); });
      if (site.hasPower) {
        var mw = tag('', 'atlas-tag-power');
        var visible = h('span', '', 'MW');
        visible.setAttribute('aria-hidden', 'true');
        mw.appendChild(visible);
        mw.appendChild(srOnly('reported power'));
        mw.title = 'Has a reported power observation';
        badges.appendChild(mw);
      }
      body.appendChild(badges);
      button.appendChild(swatch);
      button.appendChild(body);
      row.appendChild(button);
      S.rows[site.id] = row;
      return row;
    }

    function rowButton(id) {
      var row = id ? S.rows[id] : null;
      return row ? row.firstChild : null;
    }

    function renderList() {
      var focusedId = '';
      var active = document.activeElement;
      if (active && E.list.contains(active)) {
        var owner = active.closest('[data-site-id]');
        focusedId = owner ? owner.getAttribute('data-site-id') : '';
      }
      var fragment = document.createDocumentFragment();
      S.visible.forEach(function (site) { fragment.appendChild(rowFor(site)); });
      E.list.textContent = '';
      E.list.appendChild(fragment);
      if (E.empty) {
        E.empty.hidden = S.visible.length !== 0;
      }
      updateTabStop(focusedId);
      if (focusedId && S.visibleIds[focusedId]) {
        rowButton(focusedId).focus({ preventScroll: true });
      }
    }

    function updateTabStop(preferredId) {
      var candidates = [preferredId, S.tabStopId, S.selectedId];
      var target = '';
      for (var i = 0; i < candidates.length && !target; i++) {
        if (candidates[i] && S.visibleIds[candidates[i]]) {
          target = candidates[i];
        }
      }
      if (!target && S.visible.length) {
        target = S.visible[0].id;
      }
      var previous = rowButton(S.tabStopId);
      if (previous) {
        previous.tabIndex = -1;
      }
      S.tabStopId = target;
      var next = rowButton(target);
      if (next) {
        next.tabIndex = 0;
      }
    }

    function focusRow(id) {
      var button = rowButton(id);
      if (!button) {
        return;
      }
      updateTabStop(id);
      button.focus({ preventScroll: false });
      if (typeof button.scrollIntoView === 'function') {
        button.scrollIntoView({ block: 'nearest' });
      }
    }

    function rowIdFromEvent(event) {
      var target = event.target && event.target.closest ? event.target.closest('[data-site-id]') : null;
      return target && E.list.contains(target) ? target.getAttribute('data-site-id') : '';
    }

    function onListKeydown(event) {
      var id = rowIdFromEvent(event);
      if (!id) {
        return;
      }
      var index = -1;
      for (var i = 0; i < S.visible.length; i++) {
        if (S.visible[i].id === id) {
          index = i;
          break;
        }
      }
      if (index === -1) {
        return;
      }
      var next;
      switch (event.key) {
        case 'ArrowDown': next = index + 1; break;
        case 'ArrowUp': next = index - 1; break;
        case 'Home': next = 0; break;
        case 'End': next = S.visible.length - 1; break;
        case 'PageDown': next = index + 10; break;
        case 'PageUp': next = index - 10; break;
        default: return;
      }
      event.preventDefault();
      next = Math.max(0, Math.min(S.visible.length - 1, next));
      focusRow(S.visible[next].id);
    }

    // -------------------------------------------------------------------------
    // Map
    // -------------------------------------------------------------------------

    function mapVisible() {
      return !!(S.map && E.map && E.map.clientWidth > 0 && E.map.clientHeight > 0);
    }

    function programmatic(fn) {
      S.programmatic += 1;
      try {
        fn();
      } finally {
        S.programmatic -= 1;
      }
    }

    function animateMoves() {
      return !S.reduce.matches;
    }

    function drawerWidth() {
      if (S.narrow.matches || E.detail.hidden) {
        return 0;
      }
      return E.detail.offsetWidth || 0;
    }

    function viewPadding() {
      return { tl: [36, 36], br: [36 + drawerWidth(), 36] };
    }

    function markerFor(id) {
      return S.markers[id] || null;
    }

    function styleSite(id) {
      if (!id) {
        return;
      }
      var selected = id === S.selectedId;
      var hovered = id === S.hoverId;
      var marker = markerFor(id);
      if (marker) {
        marker.setRadius(selected ? RADIUS.selected : (hovered ? RADIUS.hover : RADIUS.base));
        var path = marker.getElement && marker.getElement();
        if (path) {
          path.classList.toggle('is-selected', selected);
          path.classList.toggle('is-hover', hovered && !selected);
        }
        if ((selected || hovered) && S.markerLayer && S.markerLayer.hasLayer(marker)) {
          marker.bringToFront();
        }
      }
      var polygon = S.polygons[id];
      if (polygon) {
        var shape = polygon.getElement && polygon.getElement();
        if (shape) {
          shape.classList.toggle('is-selected', selected);
          shape.classList.toggle('is-hover', hovered && !selected);
        }
      }
      var row = S.rows[id];
      if (row) {
        row.classList.toggle('is-selected', selected);
        row.classList.toggle('is-hover', hovered && !selected);
        var button = row.firstChild;
        if (selected) {
          button.setAttribute('aria-current', 'true');
        } else {
          button.removeAttribute('aria-current');
        }
      }
    }

    function tooltipContent(site) {
      var tip = S.tips[site.id];
      if (!tip) {
        tip = h('span', 'atlas-tip');
        tip.appendChild(h('strong', 'atlas-tip-name', site.name));
        var parts = [site.country].concat(site.statuses.map(function (code) { return Core.statusLabel(code, vocab); }));
        tip.appendChild(h('span', 'atlas-tip-meta', parts.filter(Boolean).join(' \u00b7 ')));
        S.tips[site.id] = tip;
      }
      return tip;
    }

    function showTooltip(id, source) {
      var site = S.byId[id];
      if (!S.tooltip || !site || !site.hasLocation || !S.visibleIds[id] || !mapVisible()) {
        hideTooltip();
        return;
      }
      var latlng = window.L.latLng(site.lat, site.lon);
      if (source === 'list' && !S.map.getBounds().contains(latlng)) {
        hideTooltip();
        return;
      }
      S.tooltip.setLatLng(latlng);
      S.tooltip.setContent(tooltipContent(site));
      if (!S.map.hasLayer(S.tooltip)) {
        S.tooltip.openOn(S.map);
      }
    }

    function hideTooltip() {
      if (S.map && S.tooltip && S.map.hasLayer(S.tooltip)) {
        S.map.removeLayer(S.tooltip);
      }
    }

    /** Hover can come from a marker, a nearby pointer, a polygon or a list row. */
    function setHover(source, id) {
      if (S.hover[source] === id) {
        return;
      }
      S.hover[source] = id;
      var next = S.hover.marker || S.hover.near || S.hover.polygon || S.hover.list || '';
      var winner = S.hover.marker ? 'marker' : (S.hover.near ? 'near' : (S.hover.polygon ? 'polygon' : 'list'));
      if (next === S.hoverId) {
        return;
      }
      var previous = S.hoverId;
      S.hoverId = next;
      styleSite(previous);
      styleSite(next);
      if (next) {
        showTooltip(next, winner);
      } else {
        hideTooltip();
      }
      if (E.map) {
        E.map.classList.toggle('is-pointing', !!(S.hover.near || S.hover.marker || S.hover.polygon));
      }
    }

    function nearestVisible(point, maxPx) {
      if (!mapVisible()) {
        return null;
      }
      var size = S.map.getSize();
      var points = [];
      for (var i = 0; i < S.visible.length; i++) {
        var site = S.visible[i];
        if (!site.hasLocation) {
          continue;
        }
        var p = S.map.latLngToContainerPoint([site.lat, site.lon]);
        if (p.x < -maxPx || p.y < -maxPx || p.x > size.x + maxPx || p.y > size.y + maxPx) {
          continue;
        }
        if (Math.abs(p.x - point.x) <= maxPx && Math.abs(p.y - point.y) <= maxPx) {
          points.push({ x: p.x, y: p.y, id: site.id });
        }
      }
      return Core.nearestPoint(points, point.x, point.y, maxPx);
    }

    function onMapMouseMove(event) {
      S.lastMove = event;
      if (S.moveFrame) {
        return;
      }
      S.moveFrame = window.requestAnimationFrame(function () {
        S.moveFrame = 0;
        var move = S.lastMove;
        if (!move) {
          return;
        }
        setHover('near', nearestVisible(move.containerPoint, NEAR_PX) || '');
      });
    }

    function onMapClick(event) {
      var id = nearestVisible(event.containerPoint, TAP_PX);
      if (id) {
        openSite(id, { origin: 'map', zoom: false });
      }
    }

    function resultsBounds() {
      var L = window.L;
      var bounds = L.latLngBounds([]);
      S.visible.forEach(function (site) {
        if (site.hasLocation) {
          bounds.extend([site.lat, site.lon]);
        }
      });
      return bounds.isValid() ? bounds : null;
    }

    function fitToResults(animate) {
      if (!S.map) {
        return;
      }
      if (!mapVisible()) {
        S.pendingView = { type: 'fit' };
        return;
      }
      var bounds = resultsBounds();
      if (!bounds) {
        return;
      }
      var pad = viewPadding();
      programmatic(function () {
        S.map.fitBounds(bounds, {
          paddingTopLeft: pad.tl,
          paddingBottomRight: pad.br,
          maxZoom: 13,
          animate: !!animate && animateMoves()
        });
      });
    }

    function zoomToSite(site, animate) {
      if (!S.map || !site || !site.hasLocation) {
        return;
      }
      if (!mapVisible()) {
        S.pendingView = { type: 'site', id: site.id };
        return;
      }
      var L = window.L;
      var box = site.isArea ? Core.geometryBounds(site.geometry) : null;
      var bounds = L.latLngBounds([[site.lat, site.lon], [site.lat, site.lon]]);
      var maxZoom = Math.max(14, Math.round(S.map.getZoom()));
      if (box) {
        bounds.extend(box[0]).extend(box[1]);
        maxZoom = 17;
      }
      var pad = viewPadding();
      var options = { paddingTopLeft: pad.tl, paddingBottomRight: pad.br, maxZoom: Math.min(maxZoom, 18) };
      programmatic(function () {
        if (animate !== false && animateMoves()) {
          options.duration = 0.8;
          S.map.flyToBounds(bounds, options);
        } else {
          options.animate = false;
          S.map.fitBounds(bounds, options);
        }
      });
    }

    function keepInView(site) {
      if (!mapVisible() || !site.hasLocation) {
        return;
      }
      var pad = viewPadding();
      var size = S.map.getSize();
      var point = S.map.latLngToContainerPoint([site.lat, site.lon]);
      var left = pad.tl[0];
      var right = size.x - pad.br[0];
      if (point.x >= left && point.x <= right && point.y >= pad.tl[1] && point.y <= size.y - pad.br[1]) {
        return;
      }
      var dx = point.x - (left + right) / 2;
      var dy = point.y - size.y / 2;
      programmatic(function () {
        S.map.panBy([dx, dy], { animate: animateMoves() });
      });
    }

    function applyPendingView() {
      if (!S.pendingView || !mapVisible()) {
        return;
      }
      var pending = S.pendingView;
      S.pendingView = null;
      if (pending.type === 'site' && S.byId[pending.id]) {
        zoomToSite(S.byId[pending.id], false);
      } else {
        fitToResults(false);
      }
    }

    function renderMapLayers() {
      if (!S.map) {
        return;
      }
      S.sites.forEach(function (site) {
        var visible = !!S.visibleIds[site.id];
        var marker = S.markers[site.id];
        var polygon = S.polygons[site.id];
        var changed = false;
        if (polygon) {
          if (visible && !S.polygonLayer.hasLayer(polygon)) {
            S.polygonLayer.addLayer(polygon);
            changed = true;
          } else if (!visible && S.polygonLayer.hasLayer(polygon)) {
            S.polygonLayer.removeLayer(polygon);
          }
        }
        if (marker) {
          if (visible && !S.markerLayer.hasLayer(marker)) {
            S.markerLayer.addLayer(marker);
            changed = true;
          } else if (!visible && S.markerLayer.hasLayer(marker)) {
            S.markerLayer.removeLayer(marker);
          }
        }
        if (changed && (site.id === S.selectedId || site.id === S.hoverId)) {
          styleSite(site.id);
        }
      });
      if (S.hoverId && !S.visibleIds[S.hoverId]) {
        hideTooltip();
      }
      if (S.selectedId && S.visibleIds[S.selectedId] && S.markers[S.selectedId]) {
        S.markers[S.selectedId].bringToFront();
      }
    }

    function createSiteLayers() {
      if (!S.map) {
        return;
      }
      var L = window.L;
      S.sites.forEach(function (site) {
        if (!site.hasLocation) {
          return;
        }
        var group = Core.statusGroup(site.primaryStatus);
        var className = 'atlas-grp-' + group.id;
        if (site.isArea) {
          var latlngs = Core.geometryLatLngs(site.geometry);
          if (latlngs) {
            var polygon = L.polygon(latlngs, {
              renderer: S.polygonRenderer,
              pane: 'atlasPolygons',
              className: 'atlas-polygon ' + className,
              color: group.color,
              weight: 2,
              opacity: 0.9,
              fillColor: group.color,
              fillOpacity: 0.14,
              bubblingMouseEvents: false
            });
            polygon.on('click', function () { openSite(site.id, { origin: 'map', zoom: false }); });
            polygon.on('mouseover', function () { setHover('polygon', site.id); });
            polygon.on('mouseout', function () { setHover('polygon', ''); });
            S.polygons[site.id] = polygon;
          }
        }
        var marker = L.circleMarker([site.lat, site.lon], {
          renderer: S.markerRenderer,
          pane: 'atlasMarkers',
          className: 'atlas-marker ' + className,
          radius: RADIUS.base,
          color: '#ffffff',
          weight: 1.5,
          opacity: 1,
          fillColor: group.color,
          fillOpacity: 1,
          bubblingMouseEvents: false
        });
        marker.on('click', function () { openSite(site.id, { origin: 'map', zoom: false }); });
        marker.on('mouseover', function () { setHover('marker', site.id); });
        marker.on('mouseout', function () { setHover('marker', ''); });
        S.markers[site.id] = marker;
      });
    }

    function basemapIdOf(layer) {
      var found = '';
      Object.keys(S.baseLayers).forEach(function (id) {
        if (S.baseLayers[id] === layer) {
          found = id;
        }
      });
      return found;
    }

    function useBasemap(id) {
      if (!S.map || !S.baseLayers[id] || id === S.basemapId) {
        return;
      }
      if (S.baseLayers[S.basemapId]) {
        S.map.removeLayer(S.baseLayers[S.basemapId]);
      }
      S.baseLayers[id].addTo(S.map);
      S.basemapId = id;
      if (E.mapwrap) {
        E.mapwrap.setAttribute('data-basemap', id);
      }
    }

    function mapUnavailable() {
      S.map = null;
      if (E.app) {
        E.app.classList.add('no-map');
      }
      if (E.fit) {
        E.fit.hidden = true;
      }
    }

    function initMap() {
      var L = window.L;
      if (!L || !E.map) {
        mapUnavailable();
        return;
      }
      var still = S.reduce.matches;
      try {
        S.map = L.map(E.map, {
          zoomControl: true,
          worldCopyJump: true,
          minZoom: 1,
          maxZoom: 19,
          zoomSnap: 0.5,
          zoomAnimation: !still,
          fadeAnimation: !still,
          markerZoomAnimation: !still,
          inertia: !still
        });
        S.map.setView([22, 12], 2, { animate: false });
      } catch (error) {
        mapUnavailable();
        return;
      }
      var map = S.map;
      map.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');
      map.createPane('atlasPolygons').style.zIndex = '410';
      map.createPane('atlasMarkers').style.zIndex = '420';
      S.polygonRenderer = L.svg({ pane: 'atlasPolygons', padding: 0.5 });
      S.markerRenderer = L.svg({ pane: 'atlasMarkers', padding: 0.5 });
      S.polygonLayer = L.layerGroup().addTo(map);
      S.markerLayer = L.layerGroup().addTo(map);
      S.tooltip = L.tooltip({ direction: 'top', offset: [0, -9], className: 'atlas-tooltip', opacity: 1 });

      var stored = Core.readStoredBasemap(store);
      S.basemapExplicit = !!stored;
      var chosen = Core.chooseBasemap(stored, S.dark.matches);
      var byName = {};
      Core.BASEMAPS.forEach(function (basemap) {
        var layer = L.tileLayer(basemap.url, Object.assign({}, basemap.options));
        S.baseLayers[basemap.id] = layer;
        byName[basemap.name] = layer;
      });
      S.baseLayers[chosen].addTo(map);
      S.basemapId = chosen;
      if (E.mapwrap) {
        E.mapwrap.setAttribute('data-basemap', chosen);
      }
      L.control.layers(byName, null, { position: 'topright' }).addTo(map);
      map.on('baselayerchange', function (event) {
        var id = basemapIdOf(event.layer);
        if (id) {
          S.basemapId = id;
          S.basemapExplicit = true;
          Core.storeBasemap(store, id);
          if (E.mapwrap) {
            E.mapwrap.setAttribute('data-basemap', id);
          }
        }
      });
      onMediaChange(S.dark, function () {
        if (!S.basemapExplicit && (S.basemapId === 'light' || S.basemapId === 'dark')) {
          useBasemap(S.dark.matches ? 'dark' : 'light');
        }
      });

      map.on('movestart zoomstart', function () {
        if (!S.programmatic) {
          S.userMoved = true;
        }
      });
      map.on('mousemove', onMapMouseMove);
      map.on('mouseout', function () {
        S.lastMove = null;
        setHover('near', '');
      });
      map.on('click', onMapClick);

      if (typeof ResizeObserver === 'function') {
        var size = { w: E.map.clientWidth, h: E.map.clientHeight };
        new ResizeObserver(function () {
          window.requestAnimationFrame(function () {
            if (!S.map) {
              return;
            }
            var w = E.map.clientWidth;
            var hgt = E.map.clientHeight;
            if (w === size.w && hgt === size.h) {
              return;
            }
            size = { w: w, h: hgt };
            S.map.invalidateSize({ pan: false });
            applyPendingView();
          });
        }).observe(E.map);
      }
    }

    function renderLegend() {
      if (!E.legendList) {
        return;
      }
      E.legendList.textContent = '';
      var groups = [];
      S.context.statuses.forEach(function (code) {
        var group = Core.statusGroup(code);
        if (groups.indexOf(group) === -1) {
          groups.push(group);
        }
      });
      groups.forEach(function (group) {
        var item = h('li', 'atlas-legend-item');
        var swatch = h('span', 'atlas-swatch atlas-grp-' + group.id);
        swatch.setAttribute('aria-hidden', 'true');
        item.appendChild(swatch);
        var text = h('span', 'atlas-legend-text');
        text.appendChild(h('span', 'atlas-legend-label', group.label));
        var members = S.context.statuses.filter(function (code) { return Core.statusGroup(code) === group; });
        var names = members.map(function (code) { return Core.statusLabel(code, vocab); });
        if (names.length > 1 || (names.length === 1 && names[0] !== group.label)) {
          text.appendChild(h('span', 'atlas-legend-members', names.join(', ')));
        }
        item.appendChild(text);
        E.legendList.appendChild(item);
      });
      if (S.sites.some(function (site) { return site.isArea; })) {
        var area = h('li', 'atlas-legend-item');
        var outline = h('span', 'atlas-swatch atlas-swatch-area');
        outline.setAttribute('aria-hidden', 'true');
        area.appendChild(outline);
        var label = h('span', 'atlas-legend-text');
        label.appendChild(h('span', 'atlas-legend-label', 'Site polygon'));
        label.appendChild(h('span', 'atlas-legend-members', 'Boundary or mapped outline; circles mark the locator point'));
        area.appendChild(label);
        E.legendList.appendChild(area);
      }
    }

    // -------------------------------------------------------------------------
    // Rendering
    // -------------------------------------------------------------------------

    function render(options) {
      if (!S.ready) {
        return;
      }
      var opts = options || {};
      S.visible = Core.sortSites(Core.filterSites(S.sites, S.state), S.state.sort);
      S.visibleIds = Object.create(null);
      S.visible.forEach(function (site) { S.visibleIds[site.id] = true; });
      updateFacets(Core.facetCounts(S.sites, S.state));
      renderList();
      renderMapLayers();
      updateSummary();
      if (opts.fit && !S.userMoved) {
        fitToResults(opts.animate);
      }
    }

    // -------------------------------------------------------------------------
    // Detail drawer
    // -------------------------------------------------------------------------

    function kvRow(dl, label, value) {
      if (value === null || value === undefined || value === '') {
        return;
      }
      dl.appendChild(h('dt', '', label));
      var dd = h('dd');
      if (typeof value === 'string' || typeof value === 'number') {
        dd.textContent = String(value);
      } else {
        dd.appendChild(value);
      }
      dl.appendChild(dd);
    }

    function unknownText(reason) {
      return h('span', 'muted', reason ? 'Unknown: ' + reason : 'Unknown');
    }

    function isUnknown(value) {
      return value === null || value === undefined || value === '' || value === 'unknown';
    }

    function codedValue(kind, value, reason) {
      if (isUnknown(value)) {
        return unknownText(reason);
      }
      return h('span', '', Core.vocabLabel(vocab, kind, value));
    }

    function monoList(values) {
      var list = (Array.isArray(values) ? values : [values]).filter(function (v) { return typeof v === 'string' && v; });
      if (!list.length) {
        return null;
      }
      var wrap = h('span', 'atlas-codes');
      list.forEach(function (value, index) {
        if (index) {
          wrap.appendChild(textNode(', '));
        }
        wrap.appendChild(h('code', 'mono', value));
      });
      return wrap;
    }

    function labelList(kind, values) {
      var list = (Array.isArray(values) ? values : [values]).filter(function (v) { return typeof v === 'string' && v; });
      return list.length ? list.map(function (code) { return Core.vocabLabel(vocab, kind, code); }).join(', ') : '';
    }

    function section(title, count) {
      var el = h('section', 'atlas-detail-section');
      var heading = h('h3', 'atlas-detail-heading', title);
      if (count !== undefined) {
        heading.appendChild(textNode(' '));
        heading.appendChild(h('span', 'atlas-heading-count', String(count)));
      }
      el.appendChild(heading);
      return el;
    }

    function observationList(observations, kind) {
      var list = h('ul', 'atlas-observations');
      observations.forEach(function (obs) {
        if (!obs || typeof obs !== 'object') {
          return;
        }
        var item = h('li', 'atlas-observation');
        var head = h('p', 'atlas-observation-head');
        head.appendChild(h('strong', '', Core.vocabLabel(vocab, kind, obs.metric)));
        var value = Core.formatPowerValue(obs);
        if (value) {
          head.appendChild(textNode(' '));
          head.appendChild(h('span', 'atlas-observation-value', value));
        }
        var bits = [];
        if (obs.stage) {
          bits.push(Core.vocabLabel(vocab, 'power_stages', obs.stage));
        }
        if (obs.method) {
          bits.push(Core.vocabLabel(vocab, 'estimate_methods', obs.method));
        }
        if (obs.as_of_date) {
          bits.push('as of ' + Core.isoDate(obs.as_of_date));
        }
        if (obs.target_date) {
          bits.push('target ' + Core.isoDate(obs.target_date));
        }
        if (bits.length) {
          head.appendChild(textNode(' '));
          head.appendChild(h('span', 'atlas-observation-meta', bits.join(' \u00b7 ')));
        }
        item.appendChild(head);
        if (obs.notes) {
          item.appendChild(h('p', 'small muted', obs.notes));
        }
        list.appendChild(item);
      });
      return list;
    }

    function projectSection(project, evidenceById) {
      var el = h('section', 'project atlas-project');
      el.appendChild(h('h4', 'atlas-project-name', project.name || project.project_id));
      var status = h('p', 'atlas-project-status');
      if (project.last_observed_physical_status) {
        status.appendChild(badge(project.last_observed_physical_status));
        status.appendChild(textNode(' '));
      }
      status.appendChild(h('span', '', 'as of ' + (Core.isoDate(project.status_as_of) || 'unknown date')));
      if (project.status_method) {
        status.appendChild(h('span', 'muted', ' \u00b7 ' + Core.vocabLabel(vocab, 'status_methods', project.status_method)));
      }
      el.appendChild(status);

      var source = project.status_source && typeof project.status_source === 'object'
        ? project.status_source
        : evidenceById[project.status_evidence_id];
      if (source) {
        var src = h('p', 'atlas-project-source');
        src.appendChild(h('span', 'atlas-k', 'Status source: '));
        src.appendChild(externalLink(source.source_url || project.status_source_url, source.title || 'Source document'));
        var bits = [];
        if (source.publisher) { bits.push(source.publisher); }
        if (source.published_at) { bits.push('published ' + Core.isoDate(source.published_at)); }
        if (source.kind) { bits.push(Core.vocabLabel(vocab, 'evidence_kinds', source.kind)); }
        if (bits.length) {
          src.appendChild(h('span', 'muted', ' \u2014 ' + bits.join(', ')));
        }
        el.appendChild(src);
      }

      var dl = h('dl', 'kv atlas-kv');
      kvRow(dl, 'Operating model', codedValue('operating_models', project.operating_model, project.operating_model_unknown_reason));
      kvRow(dl, 'Development type', codedValue('development_types', project.development_type, project.development_type_unknown_reason));
      var workloads = Array.isArray(project.workloads) ? project.workloads : [];
      if (workloads.length) {
        kvRow(dl, 'Workloads', workloads.map(function (w) {
          var label = Core.vocabLabel(vocab, 'workloads', w.workload);
          return w.deployment_scope ? label + ' (' + Core.vocabLabel(vocab, 'workload_deployment_scopes', w.deployment_scope).toLowerCase() + ')' : label;
        }).join(', '));
      } else {
        kvRow(dl, 'Workloads', unknownText(project.workload_unknown_reason));
      }
      var roles = Array.isArray(project.role_claims) ? project.role_claims : [];
      if (roles.length) {
        kvRow(dl, 'Roles', roles.map(function (claim) {
          var text = Core.vocabLabel(vocab, 'party_roles', claim.role) + ': ' + (claim.party || 'unnamed');
          return claim.relationship_scope ? text + ' (' + Core.vocabLabel(vocab, 'relationship_scopes', claim.relationship_scope).toLowerCase() + ')' : text;
        }).join('; '));
      }
      ['operator', 'owner', 'users', 'tenants', 'customers'].forEach(function (field) {
        if (typeof project[field] === 'string' && project[field]) {
          kvRow(dl, Core.humanizeCode(field), project[field]);
        }
      });
      var power = Array.isArray(project.power_observations) ? project.power_observations : [];
      kvRow(dl, 'Power', power.length ? observationList(power, 'power_metrics') : unknownText(project.power_unknown_reason));
      var energy = Array.isArray(project.annual_energy_observations) ? project.annual_energy_observations : [];
      kvRow(dl, 'Annual energy', energy.length ? observationList(energy, 'power_metrics') : unknownText(project.annual_energy_unknown_reason));
      var efficiency = Array.isArray(project.efficiency_observations) ? project.efficiency_observations : [];
      kvRow(dl, 'Efficiency', efficiency.length ? observationList(efficiency, 'power_metrics') : unknownText(project.efficiency_unknown_reason));
      el.appendChild(dl);
      return el;
    }

    function locatorSection(site, record) {
      var el = section('Locator');
      el.appendChild(h('p', 'small muted', 'Locators place a site on the map; they are not building footprints or construction extents.'));
      var dl = h('dl', 'kv atlas-kv');
      kvRow(dl, 'Geometry type', site.geometryType);
      kvRow(dl, 'Locator scope', labelList('geometry_use_scopes', record ? record.geometry_use_scopes : site.locatorScopes));
      if (record) {
        kvRow(dl, 'Scope class', monoList(record.geometry_scope_classes));
        kvRow(dl, 'Authority', labelList('geometry_authority_classes', record.geometry_authority_classes));
        kvRow(dl, 'Method', monoList(record.geometry_methods));
        kvRow(dl, 'Derivation', monoList(record.geometry_derivations));
        var precision = Array.isArray(record.geometry_precision_scopes) ? record.geometry_precision_scopes.filter(Boolean) : [];
        if (precision.length) {
          kvRow(dl, 'Precision', precision.join(' '));
        }
        var metres = Core.formatNumber(record.horizontal_uncertainty_metres);
        kvRow(dl, 'Horizontal uncertainty', metres ? metres + ' m' : unknownText(record.horizontal_uncertainty_unknown_reason));
      }
      el.appendChild(dl);
      return el;
    }

    function evidenceSection(evidence) {
      var el = section('Evidence', evidence.length);
      var list = h('ul', 'evidence-list atlas-evidence-list');
      evidence.forEach(function (ev) {
        if (!ev || typeof ev !== 'object') {
          return;
        }
        var item = h('li', 'atlas-evidence');
        item.appendChild(externalLink(ev.source_url, ev.title || ev.source_url || ev.evidence_id, 'evidence-link'));
        var bits = [];
        if (ev.publisher) { bits.push(ev.publisher); }
        if (ev.kind) { bits.push(Core.vocabLabel(vocab, 'evidence_kinds', ev.kind)); }
        if (ev.published_at) { bits.push('published ' + Core.isoDate(ev.published_at)); }
        if (ev.retrieved_at) { bits.push('retrieved ' + Core.isoDate(ev.retrieved_at)); }
        if (bits.length) {
          item.appendChild(h('span', 'atlas-evidence-meta', bits.join(' \u00b7 ')));
        }
        var roles = labelList('evidence_roles', ev.roles);
        if (roles) {
          item.appendChild(h('span', 'atlas-evidence-roles', 'Supports: ' + roles));
        }
        if (ev.license) {
          var licence = 'Licence: ' + ev.license + (ev.attribution && ev.attribution !== ev.publisher ? ' \u00b7 ' + ev.attribution : '');
          item.appendChild(h('span', 'atlas-evidence-licence', licence));
        }
        list.appendChild(item);
      });
      el.appendChild(list);
      return el;
    }

    function renderDetail(site, doc, failed) {
      var record = doc && doc.site && typeof doc.site === 'object' ? doc.site : null;
      var projects = doc && Array.isArray(doc.projects) ? doc.projects : null;
      var evidence = doc && Array.isArray(doc.evidence) ? doc.evidence : null;

      E.detailTitle.textContent = site.name;
      if (E.detailKicker) {
        E.detailKicker.textContent = [site.country, site.iso].filter(Boolean).join(' \u00b7 ');
      }
      var body = document.createDocumentFragment();

      var badges = h('p', 'atlas-detail-badges');
      site.statuses.forEach(function (code) {
        badges.appendChild(badge(code));
        badges.appendChild(textNode(' '));
      });
      if (site.officialBoundary) {
        badges.appendChild(tag('Official boundary'));
        badges.appendChild(textNode(' '));
      }
      if (site.hasPower) {
        badges.appendChild(tag('Reported power'));
      }
      body.appendChild(badges);

      var asOf = 'Last observed physical status as of ' + (site.newest || 'unknown date');
      if (site.oldest && site.newest && site.oldest !== site.newest) {
        asOf += ' (projects observed ' + site.oldest + ' \u2013 ' + site.newest + ')';
      }
      body.appendChild(h('p', 'atlas-detail-asof', asOf + '.'));

      var actions = h('p', 'atlas-detail-actions');
      actions.appendChild(internalLink(sitePagePath(site.id), 'Permalink', 'btn btn-small'));
      var json = h('a', 'btn btn-small', 'JSON');
      json.href = siteDocUrl(site.id);
      actions.appendChild(json);
      var correction = Core.correctionUrl(boot.issues_url, site.name, site.id);
      if (correction) {
        actions.appendChild(externalLink(correction, 'Report a correction', 'btn btn-small'));
      }
      body.appendChild(actions);

      var where = section('Location');
      if (site.hasLocation) {
        var coords = Core.formatCoordinate(site.lat, 5) + ', ' + Core.formatCoordinate(site.lon, 5);
        var coordLine = h('p', 'atlas-coords');
        coordLine.appendChild(h('span', 'mono', coords));
        coordLine.appendChild(textNode(' '));
        var copy = h('button', 'copy-btn btn btn-small', 'Copy');
        copy.type = 'button';
        copy.setAttribute('data-copy', coords);
        copy.setAttribute('aria-label', 'Copy coordinates ' + coords);
        coordLine.appendChild(copy);
        where.appendChild(coordLine);
        var links = Core.externalMapLinks(site.lat, site.lon);
        if (links.length) {
          var external = h('p', 'atlas-maplinks');
          external.appendChild(h('span', 'atlas-k', 'Open in '));
          links.forEach(function (item, index) {
            if (index) {
              external.appendChild(textNode(' \u00b7 '));
            }
            external.appendChild(externalLink(item.url, item.label));
          });
          where.appendChild(external);
        }
      }
      var facts = h('dl', 'kv atlas-kv');
      kvRow(facts, 'Verification posture', Core.vocabLabel(vocab, 'verification_postures', site.verificationPosture));
      kvRow(facts, 'Independent imagery verification', site.imageryVerified ? 'Yes' : 'No');
      kvRow(facts, 'Newest status as of', site.newest);
      kvRow(facts, 'Oldest status as of', site.oldest);
      kvRow(facts, 'Projects', String(site.projectCount));
      where.appendChild(facts);
      body.appendChild(where);

      var projectBlock = section('Projects', site.projectCount);
      if (projects) {
        var evidenceById = Object.create(null);
        (evidence || []).forEach(function (ev) {
          if (ev && ev.evidence_id) {
            evidenceById[ev.evidence_id] = ev;
          }
        });
        projects.forEach(function (project) {
          if (project && typeof project === 'object') {
            projectBlock.appendChild(projectSection(project, evidenceById));
          }
        });
      } else {
        var summaryList = h('ul', 'atlas-project-summary');
        site.projects.forEach(function (project) {
          var item = h('li');
          item.appendChild(h('span', 'atlas-project-name', project.name));
          item.appendChild(textNode(' '));
          if (project.status) {
            item.appendChild(badge(project.status));
          }
          if (project.statusAsOf) {
            item.appendChild(h('span', 'muted', ' as of ' + project.statusAsOf));
          }
          summaryList.appendChild(item);
        });
        projectBlock.appendChild(summaryList);
      }
      body.appendChild(projectBlock);

      body.appendChild(locatorSection(site, record));

      if (evidence) {
        body.appendChild(evidenceSection(evidence));
      } else if (failed) {
        var fail = h('div', 'callout callout-warning atlas-detail-error');
        var p = h('p', '', 'Details for this site could not be loaded. ');
        p.appendChild(internalLink(sitePagePath(site.id), 'Open the site page'));
        p.appendChild(textNode(' instead.'));
        fail.appendChild(p);
        body.appendChild(fail);
      } else {
        body.appendChild(h('p', 'atlas-detail-loading muted', 'Loading projects and evidence\u2026'));
      }

      var foot = h('p', 'small muted atlas-detail-foot');
      foot.textContent = 'Last observed physical status from cited sources' +
        (dataset.label ? ' \u00b7 ' + dataset.label : '') + '. Preview data, not a final release.';
      body.appendChild(foot);

      E.detailBody.textContent = '';
      E.detailBody.appendChild(body);
      E.detail.setAttribute('aria-busy', doc || failed ? 'false' : 'true');
    }

    function loadDetail(site) {
      var token = ++S.detailToken;
      if (S.docs[site.id]) {
        renderDetail(site, S.docs[site.id], false);
        return;
      }
      renderDetail(site, null, false);
      fetchJSON(siteDocUrl(site.id)).then(function (doc) {
        if (!doc || typeof doc !== 'object') {
          throw new Error('Unexpected site document');
        }
        S.docs[site.id] = doc;
        if (token === S.detailToken && S.selectedId === site.id) {
          renderDetail(site, doc, false);
        }
      }).catch(function () {
        if (token === S.detailToken && S.selectedId === site.id) {
          renderDetail(site, null, true);
        }
      });
    }

    function focusDetailTitle() {
      try {
        E.detailTitle.focus({ preventScroll: true });
      } catch (error) {
        E.detailTitle.focus();
      }
    }

    function openSite(id, options) {
      var opts = options || {};
      var site = S.byId[id];
      if (!site) {
        return;
      }
      var wasOpen = !E.detail.hidden;
      var previous = S.selectedId;
      if ('origin' in opts) {
        S.origin = opts.origin;
      }
      S.selectedId = id;
      if (previous && previous !== id) {
        styleSite(previous);
      }
      styleSite(id);
      if (S.visibleIds[id]) {
        updateTabStop(id);
      }
      E.detail.hidden = false;
      E.app.classList.add('has-detail');
      if (S.narrow.matches) {
        document.documentElement.classList.add('atlas-sheet-open');
      }
      E.detailBody.scrollTop = 0;
      E.detail.scrollTop = 0;
      loadDetail(site);
      document.title = site.name + ' \u00b7 ' + S.baseTitle;
      if (opts.history !== false) {
        pushSiteState(id, wasOpen);
      }
      if (S.map) {
        if (opts.zoom === false) {
          keepInView(site);
        } else {
          zoomToSite(site, opts.animate);
        }
      }
      if (opts.focus !== false) {
        focusDetailTitle();
      }
    }

    function restoreFocus(id) {
      if (S.origin === 'map' && mapVisible()) {
        E.map.focus({ preventScroll: true });
        return;
      }
      var button = rowButton(id);
      if (button && S.visibleIds[id] && E.list.contains(button)) {
        updateTabStop(id);
        button.focus({ preventScroll: false });
        return;
      }
      var first = rowButton(S.tabStopId);
      if (first && E.list.contains(first)) {
        first.focus({ preventScroll: true });
      } else {
        E.search.focus({ preventScroll: true });
      }
    }

    function closeDetail(options) {
      var opts = options || {};
      if (E.detail.hidden) {
        return;
      }
      var id = S.selectedId;
      E.detail.hidden = true;
      E.app.classList.remove('has-detail');
      document.documentElement.classList.remove('atlas-sheet-open');
      S.selectedId = '';
      S.detailToken += 1;
      styleSite(id);
      document.title = S.baseTitle;
      if (opts.history !== false) {
        leaveSiteState();
      }
      if (opts.restoreFocus !== false) {
        restoreFocus(id);
      }
    }

    // -------------------------------------------------------------------------
    // Layout: narrow tabs, workspace height
    // -------------------------------------------------------------------------

    function setView(view, focusTab) {
      S.view = view === 'map' ? 'map' : 'list';
      E.app.setAttribute('data-view', S.view);
      if (E.tabList && E.tabMap) {
        E.tabList.setAttribute('aria-selected', String(S.view === 'list'));
        E.tabMap.setAttribute('aria-selected', String(S.view === 'map'));
        E.tabList.tabIndex = S.view === 'list' ? 0 : -1;
        E.tabMap.tabIndex = S.view === 'map' ? 0 : -1;
        if (focusTab) {
          (S.view === 'map' ? E.tabMap : E.tabList).focus();
        }
      }
      if (S.view === 'map' && S.narrow.matches && E.tabs) {
        var top = E.tabs.getBoundingClientRect().top;
        if (top > 1) {
          window.scrollBy(0, top);
        }
      }
      if (S.map && mapVisible()) {
        S.map.invalidateSize({ pan: false });
        applyPendingView();
      }
    }

    function applyLayoutMode() {
      var narrow = S.narrow.matches;
      E.app.classList.toggle('is-narrow', narrow);
      [[E.panel, E.tabList], [E.mapwrap, E.tabMap]].forEach(function (pair) {
        if (!pair[0] || !pair[1]) {
          return;
        }
        if (narrow) {
          pair[0].setAttribute('role', 'tabpanel');
          pair[0].setAttribute('aria-labelledby', pair[1].id);
        } else {
          pair[0].removeAttribute('role');
          pair[0].removeAttribute('aria-labelledby');
        }
      });
      if (!narrow) {
        document.documentElement.classList.remove('atlas-sheet-open');
      } else if (!E.detail.hidden) {
        document.documentElement.classList.add('atlas-sheet-open');
      }
      measure();
      if (S.map && mapVisible()) {
        S.map.invalidateSize({ pan: false });
        applyPendingView();
      }
    }

    var measureFrame = 0;

    function measure() {
      measureFrame = 0;
      var rect = E.app.getBoundingClientRect();
      var top = Math.max(0, Math.round(rect.top + (window.scrollY || window.pageYOffset || 0)));
      document.documentElement.style.setProperty('--atlas-app-top', top + 'px');
    }

    function scheduleMeasure() {
      if (!measureFrame) {
        measureFrame = window.requestAnimationFrame(measure);
      }
    }

    // -------------------------------------------------------------------------
    // Wiring
    // -------------------------------------------------------------------------

    function wire() {
      if (E.filters) {
        E.filters.addEventListener('submit', function (event) { event.preventDefault(); });
      }
      E.search.addEventListener('input', function () {
        S.state.q = E.search.value;
        onFilterChange({ typing: true });
      });
      if (E.country) {
        E.country.addEventListener('change', function () {
          S.state.country = E.country.value;
          onFilterChange();
        });
      }
      if (E.status) {
        E.status.addEventListener('change', function (event) {
          if (event.target && event.target.name === 'status') {
            S.state.status = checkedStatuses();
            onFilterChange();
          }
        });
      }
      if (E.locator) {
        E.locator.addEventListener('change', function () {
          S.state.locator = E.locator.value;
          onFilterChange();
        });
      }
      if (E.power) {
        E.power.addEventListener('change', function () {
          S.state.power = E.power.checked;
          onFilterChange();
        });
      }
      if (E.from) {
        E.from.addEventListener('change', function () {
          S.state.from = E.from.value;
          onFilterChange();
        });
      }
      if (E.to) {
        E.to.addEventListener('change', function () {
          S.state.to = E.to.value;
          onFilterChange();
        });
      }
      if (E.sort) {
        E.sort.addEventListener('change', function () {
          S.state.sort = E.sort.value;
          onFilterChange({ fit: false });
        });
      }
      [E.clear, E.emptyClear].forEach(function (button) {
        if (button) {
          button.addEventListener('click', clearFilters);
        }
      });
      if (E.more) {
        E.more.addEventListener('toggle', function () {
          try {
            if (store) {
              store.setItem(FILTERS_OPEN_KEY, E.more.open ? '1' : '0');
            }
          } catch (error) {
            // Remembering the panel state is a convenience only.
          }
          scheduleMeasure();
        });
      }

      E.list.addEventListener('click', function (event) {
        var id = rowIdFromEvent(event);
        if (id) {
          openSite(id, { origin: rowButton(id), zoom: true });
        }
      });
      E.list.addEventListener('keydown', onListKeydown);
      E.list.addEventListener('mouseover', function (event) {
        setHover('list', rowIdFromEvent(event));
      });
      E.list.addEventListener('mouseleave', function () { setHover('list', ''); });
      E.list.addEventListener('focusin', function (event) {
        var id = rowIdFromEvent(event);
        if (id) {
          S.tabStopId = id;
          setHover('list', id);
        }
      });
      E.list.addEventListener('focusout', function (event) {
        if (!event.relatedTarget || !E.list.contains(event.relatedTarget)) {
          setHover('list', '');
        }
      });

      E.app.addEventListener('click', function (event) {
        var button = event.target && event.target.closest ? event.target.closest('.copy-btn[data-copy]') : null;
        if (button && E.app.contains(button)) {
          event.preventDefault();
          copyWithFeedback(button.getAttribute('data-copy') || '', button, 'Copied to clipboard');
        }
      });

      if (E.detailClose) {
        E.detailClose.addEventListener('click', function () { closeDetail({}); });
      }
      document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape' || E.detail.hidden || event.defaultPrevented) {
          return;
        }
        var target = event.target;
        if (target && target.tagName === 'SELECT') {
          return;
        }
        event.preventDefault();
        closeDetail({});
      });

      if (E.fit) {
        E.fit.addEventListener('click', function () {
          S.userMoved = false;
          fitToResults(true);
        });
      }
      if (E.exportCsv) {
        E.exportCsv.addEventListener('click', function () {
          if (!S.ready) {
            return;
          }
          var filtered = S.visible.length !== S.sites.length;
          download('\ufeff' + Core.sitesToCsv(S.visible), Core.exportFilename(dataset.id, filtered, 'csv'), 'text/csv;charset=utf-8');
        });
      }
      if (E.exportGeojson) {
        E.exportGeojson.addEventListener('click', function () {
          if (!S.ready) {
            return;
          }
          var filtered = S.visible.length !== S.sites.length;
          var meta = {
            dataset: { id: dataset.id || null, label: dataset.label || null, release_status: dataset.release_status || null },
            query: Core.serializeState(S.state)
          };
          download(Core.sitesToGeoJSON(S.visible, meta), Core.exportFilename(dataset.id, filtered, 'geojson'), 'application/geo+json');
        });
      }
      if (E.copyLink) {
        E.copyLink.addEventListener('click', function () {
          flushUrl();
          copyWithFeedback(window.location.href, E.copyLink, 'Link to this view copied');
        });
      }

      if (E.tabList && E.tabMap) {
        E.tabList.addEventListener('click', function () { setView('list', false); });
        E.tabMap.addEventListener('click', function () { setView('map', false); });
        [E.tabList, E.tabMap].forEach(function (tab) {
          tab.addEventListener('keydown', function (event) {
            if (event.key === 'ArrowRight' || event.key === 'ArrowLeft' || event.key === 'Home' || event.key === 'End') {
              event.preventDefault();
              var next = event.key === 'Home' ? 'list' : (event.key === 'End' ? 'map' : (S.view === 'list' ? 'map' : 'list'));
              setView(next, true);
            }
          });
        });
      }

      window.addEventListener('popstate', onPopState);
      window.addEventListener('hashchange', onPopState);
      window.addEventListener('resize', scheduleMeasure);
      onMediaChange(S.narrow, applyLayoutMode);
    }

    // -------------------------------------------------------------------------
    // Startup
    // -------------------------------------------------------------------------

    function showLoadError() {
      if (E.loading) {
        E.loading.hidden = true;
      }
      if (E.error) {
        E.error.hidden = false;
      }
      E.list.removeAttribute('aria-busy');
      E.count.textContent = 'Site data unavailable';
    }

    function onData(collection) {
      var sites = Core.prepareSites(collection);
      if (!sites.length) {
        throw new Error('No sites in the data');
      }
      S.sites = sites;
      sites.forEach(function (site) { S.byId[site.id] = site; });
      S.context = Core.buildContext(sites);
      buildFilterOptions();
      renderLegend();
      createSiteLayers();
      S.ready = true;
      if (E.loading) {
        E.loading.hidden = true;
      }
      E.list.removeAttribute('aria-busy');
      [E.exportCsv, E.exportGeojson, E.copyLink].forEach(function (button) {
        if (button) {
          button.disabled = false;
        }
      });
      applyLocation(true);
      document.body.setAttribute('data-atlas-ready', 'true');
    }

    E.app.hidden = false;
    var filtersOpen = null;
    try {
      filtersOpen = store ? store.getItem(FILTERS_OPEN_KEY) : null;
    } catch (error) {
      filtersOpen = null;
    }
    // Filters start open on wide screens and folded on narrow ones (the list
    // comes first there); a reader's own choice wins, and active filters
    // from the URL always unfold them (see applyLocation).
    if (E.more && (filtersOpen === '0' || (filtersOpen === null && S.narrow.matches))) {
      E.more.open = false;
    }
    if (E.legend && S.narrow.matches) {
      E.legend.open = false;
    }
    E.list.setAttribute('aria-busy', 'true');
    document.querySelectorAll('.hidden-noscript').forEach(function (node) { node.classList.remove('hidden-noscript'); });
    wire();
    setView('list', false);
    applyLayoutMode();
    initMap();

    sitesPromise.then(function (collection) {
      try {
        onData(collection);
      } catch (error) {
        showLoadError();
      }
    }, showLoadError);
  }
})();
