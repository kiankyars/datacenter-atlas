CREATE TABLE administrative_assignments (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    resolution_status TEXT NOT NULL CHECK (resolution_status IN (
        'assigned', 'unmatched', 'ambiguous', 'boundary'
    )),
    country_name TEXT,
    iso_a2 TEXT,
    iso_a3 TEXT,
    source_admin TEXT,
    source_sovereignt TEXT,
    source_type TEXT,
    source_note_adm0 TEXT,
    source_note_brk TEXT,
    source_feature_id TEXT,
    match_feature_ids_json TEXT NOT NULL DEFAULT '[]',
    source_country_tag TEXT,
    coordinate_snapshot_id TEXT NOT NULL REFERENCES entity_snapshots(id),
    boundary_evidence_id TEXT NOT NULL REFERENCES evidence(id),
    as_of_date TEXT NOT NULL CHECK (length(trim(as_of_date)) > 0),
    valid_to_date TEXT,
    recorded_at TEXT NOT NULL CHECK (length(trim(recorded_at)) > 0),
    superseded_at TEXT,
    method TEXT NOT NULL CHECK (length(trim(method)) > 0),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    notes TEXT,
    CHECK (iso_a2 IS NULL OR length(iso_a2) = 2),
    CHECK (iso_a3 IS NULL OR length(iso_a3) = 3),
    CHECK (
        (resolution_status = 'assigned'
         AND country_name IS NOT NULL
         AND length(trim(country_name)) > 0
         AND source_feature_id IS NOT NULL)
        OR
        (resolution_status != 'assigned'
         AND country_name IS NULL
         AND iso_a2 IS NULL
         AND iso_a3 IS NULL
         AND source_feature_id IS NULL)
    ),
    CHECK (valid_to_date IS NULL OR valid_to_date > as_of_date),
    CHECK (superseded_at IS NULL OR superseded_at > recorded_at)
);

CREATE INDEX administrative_assignments_entity_time_idx
ON administrative_assignments(entity_id, as_of_date, recorded_at);

CREATE INDEX administrative_assignments_country_idx
ON administrative_assignments(iso_a3, country_name);
