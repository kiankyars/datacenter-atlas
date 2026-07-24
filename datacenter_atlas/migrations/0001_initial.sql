CREATE TABLE evidence (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN (
        'government_record', 'company_disclosure', 'utility_record', 'equipment_order',
        'satellite_imagery', 'openstreetmap', 'third_party_dataset', 'news', 'other'
    )),
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    source_url TEXT NOT NULL CHECK (length(trim(source_url)) > 0),
    publisher TEXT,
    source_family TEXT,
    license TEXT,
    attribution TEXT,
    published_at TEXT,
    retrieved_at TEXT NOT NULL CHECK (length(trim(retrieved_at)) > 0),
    excerpt TEXT,
    content_hash TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX evidence_source_url_idx ON evidence(source_url);
CREATE INDEX evidence_retrieved_at_idx ON evidence(retrieved_at);

CREATE TABLE entities (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('campus', 'facility', 'building', 'project')),
    stable_key TEXT NOT NULL UNIQUE CHECK (length(trim(stable_key)) > 0),
    created_from_evidence_id TEXT NOT NULL REFERENCES evidence(id),
    created_at TEXT NOT NULL CHECK (length(trim(created_at)) > 0)
);

CREATE TABLE campuses (
    entity_id TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE
);

CREATE TABLE facilities (
    entity_id TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    campus_id TEXT REFERENCES campuses(entity_id)
);

CREATE TABLE buildings (
    entity_id TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    facility_id TEXT NOT NULL REFERENCES facilities(entity_id)
);

CREATE TABLE projects (
    entity_id TEXT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    target_entity_id TEXT NOT NULL REFERENCES entities(id)
);

CREATE TRIGGER campuses_kind_insert
BEFORE INSERT ON campuses
WHEN (SELECT kind FROM entities WHERE id = NEW.entity_id) != 'campus'
BEGIN
    SELECT RAISE(ABORT, 'campuses entity must have campus kind');
END;

CREATE TRIGGER facilities_kind_insert
BEFORE INSERT ON facilities
WHEN (SELECT kind FROM entities WHERE id = NEW.entity_id) != 'facility'
BEGIN
    SELECT RAISE(ABORT, 'facilities entity must have facility kind');
END;

CREATE TRIGGER buildings_kind_insert
BEFORE INSERT ON buildings
WHEN (SELECT kind FROM entities WHERE id = NEW.entity_id) != 'building'
BEGIN
    SELECT RAISE(ABORT, 'buildings entity must have building kind');
END;

CREATE TRIGGER projects_kind_insert
BEFORE INSERT ON projects
WHEN (SELECT kind FROM entities WHERE id = NEW.entity_id) != 'project'
BEGIN
    SELECT RAISE(ABORT, 'projects entity must have project kind');
END;

CREATE TRIGGER projects_target_insert
BEFORE INSERT ON projects
WHEN (SELECT kind FROM entities WHERE id = NEW.target_entity_id) = 'project'
BEGIN
    SELECT RAISE(ABORT, 'projects cannot target another project');
END;

CREATE TABLE entity_snapshots (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    name TEXT,
    latitude REAL,
    longitude REAL,
    geometry_json TEXT,
    tags_json TEXT NOT NULL DEFAULT '{}',
    evidence_id TEXT NOT NULL REFERENCES evidence(id),
    as_of_date TEXT NOT NULL CHECK (length(trim(as_of_date)) > 0),
    valid_to_date TEXT,
    recorded_at TEXT NOT NULL CHECK (length(trim(recorded_at)) > 0),
    superseded_at TEXT,
    method TEXT NOT NULL CHECK (length(trim(method)) > 0),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    CHECK ((latitude IS NULL) = (longitude IS NULL)),
    CHECK (latitude IS NULL OR (latitude >= -90 AND latitude <= 90)),
    CHECK (longitude IS NULL OR (longitude >= -180 AND longitude <= 180)),
    CHECK (valid_to_date IS NULL OR valid_to_date > as_of_date),
    CHECK (superseded_at IS NULL OR superseded_at > recorded_at)
);

CREATE INDEX entity_snapshots_entity_time_idx
ON entity_snapshots(entity_id, as_of_date, recorded_at);

CREATE TABLE lifecycle_observations (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN (
        'lead', 'candidate', 'announced', 'proposed', 'site_control', 'permitting',
        'permitted', 'site_preparation', 'clearing', 'civil_works', 'foundations',
        'shell', 'mep_electrical', 'under_construction', 'commissioning', 'operational',
        'expansion', 'paused', 'cancelled', 'repurposed', 'decommissioned', 'demolished',
        'unknown'
    )),
    evidence_id TEXT NOT NULL REFERENCES evidence(id),
    as_of_date TEXT NOT NULL CHECK (length(trim(as_of_date)) > 0),
    valid_to_date TEXT,
    recorded_at TEXT NOT NULL CHECK (length(trim(recorded_at)) > 0),
    superseded_at TEXT,
    method TEXT NOT NULL CHECK (length(trim(method)) > 0),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    notes TEXT,
    CHECK (valid_to_date IS NULL OR valid_to_date > as_of_date),
    CHECK (superseded_at IS NULL OR superseded_at > recorded_at)
);

CREATE INDEX lifecycle_entity_time_idx
ON lifecycle_observations(entity_id, as_of_date, recorded_at);

CREATE TABLE operating_model_observations (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    operating_model TEXT NOT NULL CHECK (operating_model IN (
        'hyperscaler', 'hyperscale_self_build', 'hyperscale_lease', 'colocation',
        'wholesale_colocation', 'retail_colocation', 'neocloud', 'enterprise_private',
        'government_research', 'sovereign_research', 'edge', 'telecom_edge', 'unknown'
    )),
    evidence_id TEXT NOT NULL REFERENCES evidence(id),
    as_of_date TEXT NOT NULL CHECK (length(trim(as_of_date)) > 0),
    valid_to_date TEXT,
    recorded_at TEXT NOT NULL CHECK (length(trim(recorded_at)) > 0),
    superseded_at TEXT,
    method TEXT NOT NULL CHECK (length(trim(method)) > 0),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    notes TEXT,
    CHECK (valid_to_date IS NULL OR valid_to_date > as_of_date),
    CHECK (superseded_at IS NULL OR superseded_at > recorded_at)
);

CREATE INDEX operating_model_entity_time_idx
ON operating_model_observations(entity_id, as_of_date, recorded_at);

CREATE TABLE workload_observations (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    workload TEXT NOT NULL CHECK (workload IN (
        'ai_specialized_unspecified', 'ai_training', 'ai_inference', 'hpc',
        'general_cloud', 'enterprise_it', 'content_delivery', 'crypto_mining',
        'mixed', 'unknown'
    )),
    evidence_id TEXT NOT NULL REFERENCES evidence(id),
    as_of_date TEXT NOT NULL CHECK (length(trim(as_of_date)) > 0),
    valid_to_date TEXT,
    recorded_at TEXT NOT NULL CHECK (length(trim(recorded_at)) > 0),
    superseded_at TEXT,
    method TEXT NOT NULL CHECK (length(trim(method)) > 0),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    notes TEXT,
    CHECK (valid_to_date IS NULL OR valid_to_date > as_of_date),
    CHECK (superseded_at IS NULL OR superseded_at > recorded_at)
);

CREATE INDEX workload_entity_time_idx
ON workload_observations(entity_id, workload, as_of_date, recorded_at);

CREATE TABLE capacity_estimates (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    metric TEXT NOT NULL CHECK (metric IN (
        'grid_connection_mw', 'gross_facility_mw', 'critical_it_mw',
        'generation_nameplate_mw', 'annual_energy_mwh', 'pue'
    )),
    stage TEXT NOT NULL DEFAULT 'unknown' CHECK (stage IN (
        'requested', 'contracted', 'design', 'planned', 'installed', 'energized',
        'operational', 'measured', 'forecast', 'unknown'
    )),
    unit TEXT NOT NULL,
    low REAL NOT NULL CHECK (low >= 0),
    base REAL NOT NULL,
    high REAL NOT NULL,
    method TEXT NOT NULL CHECK (method IN (
        'reported', 'calculated', 'permit_inference', 'equipment_inference',
        'imagery_inference', 'modeled', 'unknown'
    )),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    evidence_id TEXT NOT NULL REFERENCES evidence(id),
    as_of_date TEXT NOT NULL CHECK (length(trim(as_of_date)) > 0),
    target_date TEXT,
    valid_to_date TEXT,
    recorded_at TEXT NOT NULL CHECK (length(trim(recorded_at)) > 0),
    superseded_at TEXT,
    notes TEXT,
    CHECK (low <= base AND base <= high),
    CHECK (metric != 'pue' OR low > 0),
    CHECK (
        (metric IN ('grid_connection_mw', 'gross_facility_mw', 'critical_it_mw',
                    'generation_nameplate_mw') AND unit = 'MW')
        OR (metric = 'annual_energy_mwh' AND unit = 'MWh/year')
        OR (metric = 'pue' AND unit = 'ratio')
    ),
    CHECK (valid_to_date IS NULL OR valid_to_date > as_of_date),
    CHECK (superseded_at IS NULL OR superseded_at > recorded_at)
);

CREATE INDEX capacity_entity_metric_time_idx
ON capacity_estimates(entity_id, metric, stage, as_of_date, recorded_at);
