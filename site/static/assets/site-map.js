/*
 * Data Center Atlas site page map: renders every div.site-map with Leaflet,
 * using the GeoJSON Feature in <script type="application/json" id="site-geometry">
 * and the container's data-lat / data-lon. Without JavaScript (or if Leaflet
 * fails to load) the container keeps its text fallback. An optional
 * data-carto-key on the container enables CARTO's Light/Dark basemaps.
 */
(function () {
  'use strict';

  var script = document.currentScript;

  function onReady(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  /** AtlasCore is optional on the page; load it from next to this script if needed. */
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

  function readFeature() {
    var el = document.getElementById('site-geometry');
    if (!el) {
      return null;
    }
    try {
      var data = JSON.parse(el.textContent || 'null');
      if (data && data.type === 'Feature') {
        return data;
      }
      if (data && data.type && data.coordinates) {
        return { type: 'Feature', geometry: data, properties: {} };
      }
    } catch (error) {
      return null;
    }
    return null;
  }

  function storage() {
    try {
      return window.localStorage;
    } catch (error) {
      return null;
    }
  }

  function prefersDark() {
    return !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  }

  function reducedMotion() {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function statusesOf(feature, container) {
    var props = feature && feature.properties ? feature.properties : {};
    if (Array.isArray(props.statuses)) {
      return props.statuses.filter(function (code) { return typeof code === 'string'; });
    }
    if (typeof props.status === 'string') {
      return [props.status];
    }
    var attr = container.getAttribute('data-statuses') || container.getAttribute('data-status') || '';
    return attr ? attr.split(/[\s,;]+/).filter(Boolean) : [];
  }

  function attrNumber(el, name) {
    var value = el.getAttribute(name);
    return value === null || value.trim() === '' ? NaN : Number(value);
  }

  function render(container, Core) {
    var feature = readFeature();
    var lat = attrNumber(container, 'data-lat');
    var lon = attrNumber(container, 'data-lon');
    var geometry = feature ? Core.validGeometry(feature.geometry) : null;
    if ((!isFinite(lat) || !isFinite(lon)) && geometry && geometry.type === 'Point') {
      lon = geometry.coordinates[0];
      lat = geometry.coordinates[1];
    }
    var hasPoint = isFinite(lat) && isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
    if (!hasPoint && !geometry) {
      return;
    }
    // Keep the text fallback until the map has rendered, so any failure restores it.
    var fallback = document.createDocumentFragment();
    while (container.firstChild) {
      fallback.appendChild(container.firstChild);
    }
    var map = null;
    try {
      map = window.L.map(container, mapOptions());
      drawMap(map, container, Core, feature, geometry, hasPoint ? [lat, lon] : null);
    } catch (error) {
      if (map) {
        try { map.remove(); } catch (ignored) { /* already torn down */ }
      }
      container.classList.remove('is-live');
      container.textContent = '';
      container.appendChild(fallback);
    }
  }

  function mapOptions() {
    var still = reducedMotion();
    var L = window.L;
    return {
      // On touch phones one finger scrolls the page, not the map (pinch,
      // double tap and the +/- buttons still zoom); no scroll trap.
      dragging: !(L && L.Browser && L.Browser.mobile),
      scrollWheelZoom: false,
      worldCopyJump: true,
      zoomSnap: 0.5,
      zoomAnimation: !still,
      fadeAnimation: !still,
      markerZoomAnimation: !still,
      inertia: !still
    };
  }

  function drawMap(map, container, Core, feature, geometry, point) {
    var L = window.L;
    // Same colour rule as the explorer: the newest project's status, a
    // specific stage winning a same-day tie over generic construction.
    var prepared = feature ? Core.prepareSite(feature) : null;
    var group = Core.statusGroup((prepared && prepared.primaryStatus) ||
      Core.sortStatusCodes(statusesOf(feature, container))[0] || 'under_construction');
    var name = feature && feature.properties && typeof feature.properties.name === 'string' ? feature.properties.name : '';
    container.classList.add('is-live');
    if (!container.hasAttribute('aria-label')) {
      container.setAttribute('role', 'region');
      container.setAttribute('aria-label', name ? 'Map of ' + name : 'Site map');
    }
    map.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');
    // Credit for the Atlas's own layer, whatever basemap is chosen.
    map.attributionControl.addAttribution(Core.dataCredit(Core.rootFromAssetSrc(script && script.getAttribute('src'))));

    var basemaps = Core.basemapsFor({ cartoKey: container.getAttribute('data-carto-key') });
    var store = storage();
    var chosen = Core.chooseBasemap(Core.readStoredBasemap(store), prefersDark(), basemaps);
    var layers = {};
    var byName = {};
    basemaps.forEach(function (basemap) {
      var layer = L.tileLayer(basemap.url, Object.assign({}, basemap.options));
      layers[basemap.id] = layer;
      byName[basemap.name] = layer;
    });
    layers[chosen].addTo(map);
    container.setAttribute('data-basemap', chosen);
    L.control.layers(byName, null, { position: 'topright' }).addTo(map);
    map.on('baselayerchange', function (event) {
      basemaps.forEach(function (basemap) {
        if (layers[basemap.id] === event.layer) {
          Core.storeBasemap(store, basemap.id);
          container.setAttribute('data-basemap', basemap.id);
        }
      });
    });

    var bounds = L.latLngBounds([]);
    var latlngs = geometry ? Core.geometryLatLngs(geometry) : null;
    if (latlngs) {
      L.polygon(latlngs, {
        className: 'atlas-polygon atlas-grp-' + group.id,
        color: group.color,
        fillColor: group.color,
        weight: 2,
        fillOpacity: 0.14,
        interactive: false
      }).addTo(map);
      var box = Core.geometryBounds(geometry);
      bounds.extend(box[0]).extend(box[1]);
    }
    if (point) {
      L.circleMarker(point, {
        className: 'atlas-marker atlas-grp-' + group.id,
        radius: 7,
        weight: 2,
        color: '#ffffff',
        fillColor: group.color,
        fillOpacity: 1,
        interactive: false
      }).addTo(map);
      bounds.extend(point);
    }
    if (latlngs && bounds.isValid()) {
      map.fitBounds(bounds, { padding: [28, 28], maxZoom: 17, animate: false });
    } else {
      map.setView(point, 15, { animate: false });
    }

    // Wheel zoom only after the reader engages with the map (no scroll trap).
    var engage = function () {
      map.scrollWheelZoom.enable();
    };
    map.once('focus', engage);
    map.once('click', engage);

    if (typeof ResizeObserver === 'function') {
      var lastWidth = container.clientWidth;
      new ResizeObserver(function () {
        if (container.clientWidth !== lastWidth) {
          lastWidth = container.clientWidth;
          map.invalidateSize({ pan: false });
        }
      }).observe(container);
    }
  }

  onReady(function () {
    var containers = document.querySelectorAll('.site-map');
    if (!containers.length || !window.L) {
      return;
    }
    withCore(function (Core) {
      if (!Core) {
        return;
      }
      Array.prototype.forEach.call(containers, function (container) {
        render(container, Core);
      });
    });
  });
})();
