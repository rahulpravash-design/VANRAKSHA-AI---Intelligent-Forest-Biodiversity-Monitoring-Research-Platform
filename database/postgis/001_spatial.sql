-- Optional PostGIS enhancements.
--
-- The application works on plain PostgreSQL (or SQLite) using the portable
-- haversine queries in app/services/geo.py. When PostGIS is available — this
-- file runs automatically against the `postgres` service in docker-compose.yml
-- — it adds generated geometry columns and spatial indexes so a deployment
-- with a large observation table can use native spatial operators instead.
-- Nothing in the application requires these columns to exist.

CREATE EXTENSION IF NOT EXISTS postgis;

-- observations: a generated point geometry kept in sync with latitude/longitude.
ALTER TABLE observations
    ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326)
    GENERATED ALWAYS AS (
        CASE
            WHEN latitude IS NOT NULL AND longitude IS NOT NULL
                THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
            ELSE NULL
        END
    ) STORED;

CREATE INDEX IF NOT EXISTS ix_observations_geom ON observations USING GIST (geom);

-- forest_zones: same treatment for the centroid, plus a real polygon column
-- for deployments that go on to digitise surveyed boundaries.
ALTER TABLE forest_zones
    ADD COLUMN IF NOT EXISTS center_geom geometry(Point, 4326)
    GENERATED ALWAYS AS (
        ST_SetSRID(ST_MakePoint(center_longitude, center_latitude), 4326)
    ) STORED;

ALTER TABLE forest_zones
    ADD COLUMN IF NOT EXISTS boundary_geom geometry(MultiPolygon, 4326);

CREATE INDEX IF NOT EXISTS ix_forest_zones_center_geom
    ON forest_zones USING GIST (center_geom);
CREATE INDEX IF NOT EXISTS ix_forest_zones_boundary_geom
    ON forest_zones USING GIST (boundary_geom);

-- devices: same for sensor/camera node positions.
ALTER TABLE devices
    ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326)
    GENERATED ALWAYS AS (
        CASE
            WHEN latitude IS NOT NULL AND longitude IS NOT NULL
                THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)
            ELSE NULL
        END
    ) STORED;

CREATE INDEX IF NOT EXISTS ix_devices_geom ON devices USING GIST (geom);
