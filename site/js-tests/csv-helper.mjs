// Test helpers: a strict RFC 4180 parser and loaders for the current dataset.
// Not a test file itself (the name does not match node --test patterns).
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

export const repoRoot = new URL('../../', import.meta.url);
const require = createRequire(import.meta.url);

/** Load site/static/assets/atlas-core.js the way node consumers do. */
export function loadCore() {
  return require('../static/assets/atlas-core.js');
}

/** Parse RFC 4180 CSV text into an array of string arrays (fields keep CR/LF). */
export function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let i = 0;
  let quoted = false;
  let fieldStarted = false;
  if (text.charCodeAt(0) === 0xfeff) {
    i = 1;
  }
  while (i < text.length) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        quoted = false;
        i += 1;
        if (i < text.length && text[i] !== ',' && text[i] !== '\r' && text[i] !== '\n') {
          throw new Error(`unexpected character after closing quote at ${i}`);
        }
        continue;
      }
      field += ch;
      i += 1;
      continue;
    }
    if (ch === '"') {
      if (fieldStarted) {
        throw new Error(`bare quote inside unquoted field at ${i}`);
      }
      quoted = true;
      fieldStarted = true;
      i += 1;
      continue;
    }
    if (ch === ',') {
      row.push(field);
      field = '';
      fieldStarted = false;
      i += 1;
      continue;
    }
    if (ch === '\r' || ch === '\n') {
      row.push(field);
      rows.push(row);
      row = [];
      field = '';
      fieldStarted = false;
      i += ch === '\r' && text[i + 1] === '\n' ? 2 : 1;
      continue;
    }
    field += ch;
    fieldStarted = true;
    i += 1;
  }
  if (quoted) {
    throw new Error('unterminated quoted field');
  }
  if (fieldStarted || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

/** Parse CSV with a header row into objects. */
export function parseCsvObjects(text) {
  const [header, ...rows] = parseCsv(text);
  return rows.map((cells) => Object.fromEntries(header.map((name, index) => [name, cells[index]])));
}

function readText(relativePath) {
  return readFileSync(new URL(relativePath, repoRoot), 'utf8');
}

/**
 * Build sites.geojson-shaped features (spec 3.1 site summaries) from the
 * current dataset's CSVs, so tests exercise real names and geometries.
 */
export function loadCurrentDatasetFeatures() {
  const config = JSON.parse(readText('site/config.json'));
  const dir = config.current_dataset.replace(/\/+$/, '') + '/';
  const sites = parseCsvObjects(readText(dir + 'sites.csv'));
  const projects = parseCsvObjects(readText(dir + 'projects.csv'));
  const evidence = parseCsvObjects(readText(dir + 'evidence.csv'));
  const evidenceById = new Map(evidence.map((row) => [row.evidence_id, row]));
  const projectsBySite = new Map();
  for (const project of projects) {
    if (!projectsBySite.has(project.site_id)) {
      projectsBySite.set(project.site_id, []);
    }
    projectsBySite.get(project.site_id).push(project);
  }
  const features = sites.map((site) => {
    const siteProjects = (projectsBySite.get(site.site_id) || [])
      .slice()
      .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    const publishers = [...new Set(siteProjects
      .map((project) => (evidenceById.get(project.status_evidence_id) || {}).publisher)
      .filter(Boolean))].sort();
    const power = [];
    for (const project of siteProjects) {
      for (const obs of JSON.parse(project.power_observations_json)) {
        power.push({
          project_id: project.project_id, metric: obs.metric, stage: obs.stage, low: obs.low,
          base: obs.base, high: obs.high, unit: obs.unit, as_of_date: obs.as_of_date
        });
      }
    }
    return {
      type: 'Feature',
      id: site.site_id,
      geometry: JSON.parse(site.geometry_json),
      properties: {
        site_id: site.site_id,
        name: site.name,
        country: site.country,
        country_iso_a2: site.country_iso_a2,
        latitude: Number(site.latitude),
        longitude: Number(site.longitude),
        geometry_type: site.geometry_type,
        official_boundary: siteProjects.some((project) => project.geometry_use_scope === 'official_boundary'),
        locator_scopes: JSON.parse(site.geometry_use_scopes_json),
        statuses: JSON.parse(site.statuses_json),
        newest_status_as_of: site.newest_status_as_of,
        oldest_status_as_of: site.oldest_status_as_of,
        project_count: Number(site.project_count),
        projects: siteProjects.map((project) => ({
          project_id: project.project_id,
          name: project.name,
          status: project.last_observed_physical_status,
          status_as_of: project.status_as_of
        })),
        status_publishers: publishers,
        power_observations: power,
        verification_posture: site.verification_posture,
        independent_imagery_verification: site.independent_imagery_verification === 'true',
        url: `${config.base_url}sites/${site.site_id}/`,
        api_url: `${config.base_url}api/v1/sites/${site.site_id}.json`
      }
    };
  });
  return { config, sites, projects, evidence, features };
}
