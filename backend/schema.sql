-- KSP Crime Intelligence Platform — Phase 1 schema
CREATE EXTENSION IF NOT EXISTS postgis;

DROP TABLE IF EXISTS incident_suspects CASCADE;
DROP TABLE IF EXISTS incident_victims CASCADE;
DROP TABLE IF EXISTS incidents CASCADE;
DROP TABLE IF EXISTS suspects CASCADE;
DROP TABLE IF EXISTS victims CASCADE;
DROP TABLE IF EXISTS stations CASCADE;

CREATE TABLE stations (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    district TEXT NOT NULL,
    jurisdiction_polygon GEOMETRY(POLYGON, 4326),
    lat DOUBLE PRECISION NOT NULL,
    long DOUBLE PRECISION NOT NULL
);

CREATE TABLE incidents (
    id SERIAL PRIMARY KEY,
    station_id INTEGER NOT NULL REFERENCES stations(id),
    lat DOUBLE PRECISION NOT NULL,
    long DOUBLE PRECISION NOT NULL,
    crime_type TEXT NOT NULL,
    "timestamp" TIMESTAMP NOT NULL,
    weapon_or_method TEXT,
    target_type TEXT,
    escape_pattern TEXT
);

CREATE TABLE suspects (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE victims (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);

-- Link tables (many-to-many: a suspect/victim can appear across multiple incidents,
-- an incident can have multiple suspects/victims)
CREATE TABLE incident_suspects (
    incident_id INTEGER NOT NULL REFERENCES incidents(id),
    suspect_id INTEGER NOT NULL REFERENCES suspects(id),
    PRIMARY KEY (incident_id, suspect_id)
);

CREATE TABLE incident_victims (
    incident_id INTEGER NOT NULL REFERENCES incidents(id),
    victim_id INTEGER NOT NULL REFERENCES victims(id),
    PRIMARY KEY (incident_id, victim_id)
);

CREATE INDEX idx_incidents_station ON incidents(station_id);
CREATE INDEX idx_incidents_crime_type ON incidents(crime_type);
CREATE INDEX idx_incidents_timestamp ON incidents("timestamp");
CREATE INDEX idx_stations_geom ON stations USING GIST(jurisdiction_polygon);
