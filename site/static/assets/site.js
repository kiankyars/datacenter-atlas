/*
 * Data Center Atlas static pages: copy buttons, table filtering and sortable
 * tables. Works on any page built from the shared layout; every feature is
 * an enhancement of content that is already readable without JavaScript.
 *
 * Pure helpers are exported for node tests (module.exports); in a browser the
 * page behaviour starts on DOMContentLoaded.
 */
(function (factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module && module.exports) {
    module.exports = api;
  }
  if (typeof document !== 'undefined' && typeof window !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () { api.init(document); });
    } else {
      api.init(document);
    }
  }
})(function () {
  'use strict';

  // Same folding as AtlasCore.normalizeText (kept in sync by a unit test).
  var TRANSLITERATE = {
    '\u00df': 'ss', '\u00e6': 'ae', '\u0153': 'oe', '\u00f8': 'o', '\u0142': 'l', '\u0111': 'd', '\u00f0': 'd',
    '\u00fe': 'th', '\u0131': 'i', '\u0127': 'h', '\u0167': 't', '\u014b': 'ng'
  };

  function normalizeText(value) {
    if (value === null || value === undefined) {
      return '';
    }
    return String(value)
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[\u00df\u00e6\u0153\u00f8\u0142\u0111\u00f0\u00fe\u0131\u0127\u0167\u014b]/g, function (ch) { return TRANSLITERATE[ch]; })
      .replace(/['\u2019\u02bc`\u00b4]/g, '')
      .replace(/[^\p{L}\p{N}\p{M}]+/gu, ' ')
      .trim();
  }

  /** Every query word must be found in the row text (substring match). */
  function rowMatches(rowText, query) {
    var words = normalizeText(query);
    if (!words) {
      return true;
    }
    var parts = words.split(' ');
    for (var i = 0; i < parts.length; i++) {
      if (rowText.indexOf(parts[i]) === -1) {
        return false;
      }
    }
    return true;
  }

  var SIZE_UNITS = { b: 1, kb: 1e3, kib: 1024, mb: 1e6, mib: 1048576, gb: 1e9, gib: 1073741824 };

  /**
   * Numeric value of a cell's text: "1,234", "-3.5" (any Unicode minus), "5.28 MW", "1.2 MB".
   * Returns null when the text holds no number.
   */
  function parseNumber(text) {
    var value = String(text === null || text === undefined ? '' : text)
      .replace(/[\u2212\u2012\u2013]/g, '-')
      .replace(/[\s\u00a0\u202f,]/g, '');
    var match = /^([-+]?\d*\.?\d+(?:e[-+]?\d+)?)([a-z]*)/i.exec(value);
    if (!match) {
      return null;
    }
    var n = Number(match[1]);
    if (!isFinite(n)) {
      return null;
    }
    var unit = match[2].toLowerCase();
    return Object.prototype.hasOwnProperty.call(SIZE_UNITS, unit) ? n * SIZE_UNITS[unit] : n;
  }

  /** Sort key for a cell: data-sort-value wins over the visible text. */
  function sortKey(rawText, numeric) {
    var text = String(rawText === null || rawText === undefined ? '' : rawText).trim();
    var empty = text === '' || text === '\u2014' || text === '-' || text === '\u2013';
    if (numeric) {
      var n = empty ? null : parseNumber(text);
      return { empty: n === null, number: n, text: text };
    }
    return { empty: empty, number: null, text: text };
  }

  var collator = (typeof Intl !== 'undefined' && Intl.Collator)
    ? new Intl.Collator('en', { sensitivity: 'base', numeric: true })
    : null;

  /** Ascending comparison; empty cells always sort last (caller flips the rest). */
  function compareKeys(a, b) {
    if (a.empty || b.empty) {
      return (a.empty ? 1 : 0) - (b.empty ? 1 : 0);
    }
    if (a.number !== null && b.number !== null) {
      return a.number - b.number;
    }
    if (collator) {
      return collator.compare(a.text, b.text);
    }
    return a.text < b.text ? -1 : (a.text > b.text ? 1 : 0);
  }

  /** Stable sort of [key, index] entries; empties stay last in both directions. */
  function sortEntries(entries, descending) {
    return entries.slice().sort(function (x, y) {
      var a = x.key;
      var b = y.key;
      if (a.empty || b.empty) {
        return ((a.empty ? 1 : 0) - (b.empty ? 1 : 0)) || (x.index - y.index);
      }
      var result = compareKeys(a, b);
      return (descending ? -result : result) || (x.index - y.index);
    });
  }

  // ---------------------------------------------------------------------------
  // Browser behaviour
  // ---------------------------------------------------------------------------

  var liveRegion = null;

  // The status region is created when the page starts, not on the first
  // announcement: screen readers only follow live regions that already exist.
  function ensureLiveRegion(doc) {
    if (!liveRegion && doc.body) {
      liveRegion = doc.createElement('p');
      liveRegion.className = 'sr-only';
      liveRegion.setAttribute('role', 'status');
      liveRegion.setAttribute('aria-live', 'polite');
      doc.body.appendChild(liveRegion);
    }
    return liveRegion;
  }

  function announce(doc, message) {
    if (!ensureLiveRegion(doc)) {
      return;
    }
    liveRegion.textContent = '';
    window.setTimeout(function () { liveRegion.textContent = message; }, 30);
  }

  function legacyCopy(doc, text) {
    var area = doc.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.top = '0';
    area.style.left = '0';
    area.style.opacity = '0';
    area.style.pointerEvents = 'none';
    doc.body.appendChild(area);
    area.select();
    var ok = false;
    try {
      ok = doc.execCommand('copy');
    } catch (error) {
      ok = false;
    }
    doc.body.removeChild(area);
    return ok;
  }

  function copyText(doc, text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).catch(function () {
        if (!legacyCopy(doc, text)) {
          throw new Error('copy failed');
        }
      });
    }
    return legacyCopy(doc, text) ? Promise.resolve() : Promise.reject(new Error('copy failed'));
  }

  /** Last resort: select the nearby code/checksum so the reader can copy it. */
  function selectNearby(doc, button) {
    var scope = button.parentElement;
    var target = null;
    for (var depth = 0; scope && depth < 3 && !target; depth++) {
      target = scope.querySelector('pre, code, .checksum, .mono');
      scope = scope.parentElement;
    }
    if (!target || !window.getSelection) {
      return false;
    }
    var range = doc.createRange();
    range.selectNodeContents(target);
    var selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    return true;
  }

  var flashState = typeof WeakMap === 'function' ? new WeakMap() : null;

  /** Temporarily replace a button's content with `label`, then restore its original nodes. */
  function flashLabel(button, label) {
    if (!flashState) {
      return;
    }
    var state = flashState.get(button);
    if (!state) {
      state = { nodes: Array.prototype.slice.call(button.childNodes), timer: 0 };
      flashState.set(button, state);
    }
    window.clearTimeout(state.timer);
    button.textContent = label;
    button.classList.add('is-copied');
    state.timer = window.setTimeout(function () {
      button.textContent = '';
      state.nodes.forEach(function (node) { button.appendChild(node); });
      button.classList.remove('is-copied');
      flashState.delete(button);
    }, 1800);
  }

  function initCopyButtons(doc) {
    doc.addEventListener('click', function (event) {
      var button = event.target && event.target.closest ? event.target.closest('.copy-btn[data-copy]') : null;
      if (!button) {
        return;
      }
      event.preventDefault();
      var text = button.getAttribute('data-copy') || '';
      copyText(doc, text).then(function () {
        flashLabel(button, 'Copied');
        announce(doc, 'Copied to clipboard');
      }, function () {
        if (selectNearby(doc, button)) {
          flashLabel(button, 'Press Ctrl+C');
          announce(doc, 'Text selected; press Control or Command plus C to copy');
        } else {
          window.prompt('Copy this text:', text);
        }
      });
    });
  }

  function initTableFilters(doc) {
    var inputs = doc.querySelectorAll('input.filter-input[data-filter-table]');
    Array.prototype.forEach.call(inputs, function (input) {
      var tableId = input.getAttribute('data-filter-table');
      var table = doc.getElementById(tableId);
      if (!table || !table.tBodies.length) {
        return;
      }
      var counters = Array.prototype.filter.call(doc.querySelectorAll('[data-filter-count]'), function (el) {
        return el.getAttribute('data-filter-count') === tableId;
      });
      var original = counters.map(function (el) { return el.textContent; });
      var cache = null;
      var rows = function () {
        if (!cache) {
          cache = [];
          Array.prototype.forEach.call(table.tBodies, function (body) {
            Array.prototype.forEach.call(body.rows, function (row) {
              cache.push({ row: row, text: normalizeText(row.textContent) });
            });
          });
        }
        return cache;
      };
      var apply = function () {
        var query = input.value;
        var visible = 0;
        var all = rows();
        all.forEach(function (entry) {
          var match = rowMatches(entry.text, query);
          entry.row.hidden = !match;
          if (match) {
            visible += 1;
          }
        });
        counters.forEach(function (el, index) {
          el.textContent = normalizeText(query) ? visible + ' of ' + all.length + ' shown' : original[index];
        });
      };
      input.addEventListener('input', apply);
      input.addEventListener('search', apply);
      if (input.value) {
        apply();
      }
    });
  }

  function cellText(cell) {
    if (!cell) {
      return '';
    }
    return cell.hasAttribute('data-sort-value') ? cell.getAttribute('data-sort-value') : cell.textContent;
  }

  function columnIsNumeric(table, th, index) {
    if (th.classList.contains('num')) {
      return true;
    }
    var body = table.tBodies[0];
    for (var r = 0; body && r < body.rows.length && r < 25; r++) {
      var cell = body.rows[r].cells[index];
      if (cell && cell.textContent.trim()) {
        return cell.classList.contains('num');
      }
    }
    return false;
  }

  function sortTable(table, headers, index) {
    var th = headers[index];
    var descending = th.getAttribute('aria-sort') === 'ascending';
    var numeric = columnIsNumeric(table, th, index);
    Array.prototype.forEach.call(table.tBodies, function (body) {
      var entries = Array.prototype.map.call(body.rows, function (row, rowIndex) {
        return { row: row, index: rowIndex, key: sortKey(cellText(row.cells[index]), numeric) };
      });
      var fragment = body.ownerDocument.createDocumentFragment();
      sortEntries(entries, descending).forEach(function (entry) { fragment.appendChild(entry.row); });
      body.appendChild(fragment);
    });
    headers.forEach(function (other) {
      if (other !== th) {
        other.removeAttribute('aria-sort');
      }
    });
    th.setAttribute('aria-sort', descending ? 'descending' : 'ascending');
  }

  function initSortableTables(doc) {
    var tables = doc.querySelectorAll('table.sortable');
    Array.prototype.forEach.call(tables, function (table) {
      var head = table.tHead;
      if (!head || !head.rows.length) {
        return;
      }
      var headers = Array.prototype.slice.call(head.rows[head.rows.length - 1].cells);
      headers.forEach(function (th, index) {
        if (th.hasAttribute('data-no-sort') || th.querySelector('button')) {
          return;
        }
        var button = doc.createElement('button');
        button.type = 'button';
        button.className = 'sort-btn';
        while (th.firstChild) {
          button.appendChild(th.firstChild);
        }
        var icon = doc.createElement('span');
        icon.className = 'sort-icon';
        icon.setAttribute('aria-hidden', 'true');
        button.appendChild(icon);
        th.appendChild(button);
        button.addEventListener('click', function () { sortTable(table, headers, index); });
      });
    });
  }

  /**
   * Keyboard users must be able to scroll a horizontally scrolling code block
   * or table: make it a focusable, labelled region while (and only while) it
   * overflows and holds nothing focusable itself.
   */
  function updateScrollAreas(doc) {
    var areas = doc.querySelectorAll('pre.code, .table-wrap');
    Array.prototype.forEach.call(areas, function (el) {
      var managed = el.getAttribute('data-scroll-region') === 'auto';
      var overflowing = el.scrollWidth > el.clientWidth + 1;
      var hasFocusable = !!el.querySelector('a[href], button, input, select, textarea, [tabindex]');
      if (overflowing && !hasFocusable && (managed || !el.hasAttribute('tabindex'))) {
        el.setAttribute('tabindex', '0');
        el.setAttribute('data-scroll-region', 'auto');
        if (!el.hasAttribute('role')) {
          el.setAttribute('role', 'region');
        }
        if (!el.hasAttribute('aria-label')) {
          var caption = el.querySelector('caption');
          el.setAttribute('aria-label', caption && caption.textContent.trim()
            ? caption.textContent.trim() + ' (scrollable)'
            : (el.localName === 'pre' ? 'Code example (scrollable)' : 'Table (scrollable)'));
        }
      } else if (managed && !overflowing) {
        el.removeAttribute('tabindex');
        el.removeAttribute('data-scroll-region');
      }
    });
  }

  function initScrollAreas(doc) {
    updateScrollAreas(doc);
    var pending = 0;
    window.addEventListener('resize', function () {
      window.clearTimeout(pending);
      pending = window.setTimeout(function () { updateScrollAreas(doc); }, 150);
    });
  }

  function revealScriptOnly(doc) {
    var nodes = doc.querySelectorAll('.hidden-noscript');
    Array.prototype.forEach.call(nodes, function (node) { node.classList.remove('hidden-noscript'); });
  }

  function init(doc) {
    ensureLiveRegion(doc);
    revealScriptOnly(doc);
    initCopyButtons(doc);
    initTableFilters(doc);
    initSortableTables(doc);
    initScrollAreas(doc);
  }

  return {
    normalizeText: normalizeText,
    rowMatches: rowMatches,
    parseNumber: parseNumber,
    sortKey: sortKey,
    compareKeys: compareKeys,
    sortEntries: sortEntries,
    init: init
  };
});
