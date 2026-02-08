CREATE TABLE IF NOT EXISTS events (
    event_id       UUID PRIMARY KEY,
    ts             TIMESTAMPTZ NOT NULL,
    workspace_id   TEXT NOT NULL,
    satellite_id   TEXT NOT NULL,
    trace_id       UUID NOT NULL,
    type           TEXT NOT NULL,
    severity       TEXT NOT NULL,
    confidence     DOUBLE PRECISION NOT NULL,
    payload_json   JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_events_workspace_ts
    ON events (workspace_id, ts);

CREATE INDEX IF NOT EXISTS idx_events_workspace_type_ts
    ON events (workspace_id, type, ts);

CREATE INDEX IF NOT EXISTS idx_events_trace_id
    ON events (trace_id);
