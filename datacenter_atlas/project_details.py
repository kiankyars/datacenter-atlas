"""Readable views of preserved project facts, with their original scope and citations."""

from __future__ import annotations

import html
from decimal import Decimal
import re
from urllib.parse import urlsplit


def text(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def label(value):
    return str(value or "").replace("_", " ").capitalize()


def link(url, title):
    if isinstance(url, str) and urlsplit(url).scheme in {"https", "http"} and urlsplit(url).netloc:
        return f'<a href="{text(url)}" rel="noopener">{text(title)}</a>'
    return text(title)


def number(value):
    """Keep source figures readable without rounding or scientific notation."""
    if isinstance(value, (float, int)):
        return format(Decimal(str(value)), ',f')
    return str(value if value is not None else '')


def render_record(record, *, current_status=None, current_date=None, include_summary=True):
    """Render an original structured record without inferring new facts or dates."""
    sources = {item["id"]: item for item in record.get("sources", [])}

    def citations(item):
        return "; ".join(link(sources[sid].get("url"), sources[sid].get("publisher") or sid)
                         for sid in item.get("source_ids", []) if sid in sources)

    def table(headers, rows):
        return ('<div class="table-wrap"><table><thead><tr>' +
                "".join(f'<th scope="col">{text(title)}</th>' for title in headers) +
                '</tr></thead><tbody>' + "".join('<tr>' + ''.join(f'<td>{cell}</td>' for cell in row) + '</tr>' for row in rows) +
                '</tbody></table></div>')

    parts = [f'<p>{text(record.get("summary"))}</p>'] if include_summary else []
    if record.get("status") != current_status or record.get("status_as_of") != current_date:
        parts.append(f'<p class="small">This record reports {text(label(record.get("status"))).lower()} '
                     f'as of {text(record.get("status_as_of"))}. '
                     f'{citations({"source_ids": record.get("status_source_ids", [])})}</p>')
    location = record.get("location") or {}
    place = ", ".join(dict.fromkeys(str(location[key]) for key in ("locality", "admin2", "admin1", "country") if location.get(key)))
    if place:
        parts.append(f'<p><strong>Location:</strong> {text(place)}. {text(location.get("note"))} {citations(location)}</p>')
    if record.get("workloads"):
        parts.append('<p><strong>Use:</strong> ' + ', '.join(text(label(x)) for x in record['workloads']) + '</p>')
    metrics = record.get("metrics", [])
    if metrics:
        rows = []
        qualifiers = {"exact": "", "approximately": "about ", "at_least": "at least ", "more_than": "more than ",
                      "up_to": "up to ", "less_than": "less than ", "range": ""}
        for item in metrics:
            value = item.get("value")
            value_text = number(value)
            if item.get("value_high") is not None:
                value_text += f'–{number(item["value_high"])}'
            value_text = qualifiers.get(item.get("qualifier"), label(item.get("qualifier")) + " ") + value_text + ' ' + str(item.get("unit") or "")
            scope = " · ".join(label(item.get(k)) for k in ("basis", "applies_to", "power_scope") if item.get(k))
            if item.get("phase_label"):
                scope += ' · ' + item['phase_label']
            rows.append([text(label(item.get("metric"))), text(value_text), text(scope), text(item.get("as_of")),
                         text(item.get("note")), citations(item)])
        parts += ['<h4>Capacity, investment and other figures</h4>', table(['Measure', 'Value', 'Scope', 'As of', 'Notes', 'Sources'], rows)]
    if record.get("parties"):
        parts += ['<h4>Companies and organizations</h4>', table(['Name', 'Role', 'Notes', 'Sources'], [
            [text(i.get('name')), text(label(i.get('role'))), text(i.get('note')), citations(i)] for i in record['parties']])]
    if record.get("milestones"):
        parts += ['<h4>Timeline</h4>', table(['Date', 'Event', 'Actual or planned', 'Notes', 'Sources'], [
            [text(i.get('date')), text(label(i.get('event'))), text(label(i.get('kind'))), text(i.get('note')), citations(i)]
            for i in record['milestones']])]
    if record.get("power_sources"):
        parts += ['<h4>Power supply</h4>', table(['Type', 'Description', 'Sources'], [
            [text(label(i.get('type'))), text(i.get('description')), citations(i)] for i in record['power_sources']])]
    if record.get('notes'):
        parts.append(f'<p class="small">{text(record["notes"])}</p>')
    related = [identifier for identifier in record.get('related_ids', [])
               if isinstance(identifier, str) and re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', identifier)]
    if related:
        parts.append('<p><strong>Related projects:</strong> ' + ', '.join(
            f'<a href="../../projects/{text(identifier)}/">{text(identifier.replace("-", " "))}</a>'
            for identifier in related) + '</p>')
    parts.append('<details><summary>Sources for these details</summary><ul>' + ''.join(
        f'<li>{link(s.get("url"), s.get("title"))} — {text(s.get("publisher"))}; '
        f'{text(s.get("published") or "publication date not stated")}'
        + (f' · {link(s["archived_url"], "Archived source")}' if s.get('archived_url') else '') + '</li>'
        for s in record.get('sources', [])) + '</ul></details>')
    return '\n'.join(parts)


def detail_sheets(projects):
    """Flatten arrays for Excel so figures and timelines remain usable as columns."""
    layouts = {
        'metrics': ['metric', 'value', 'value_high', 'qualifier', 'unit', 'basis', 'applies_to', 'power_scope', 'phase_label', 'as_of', 'note'],
        'parties': ['name', 'role', 'note'],
        'milestones': ['date', 'event', 'kind', 'note'],
        'power_sources': ['type', 'description'],
    }
    for field, keys in layouts.items():
        rows = [['project_id', 'source_record_id', *keys, 'source_urls']]
        for project in projects:
            for detail in project.get('project_details') or []:
                record = detail['record']
                sources = {s['id']: s['url'] for s in record['sources']}
                for item in record.get(field, []):
                    rows.append([project['project_id'], record['id'], *(item.get(k) for k in keys),
                                 '; '.join(sources[s] for s in item.get('source_ids', []))])
        if len(rows) > 1:
            yield field, rows
