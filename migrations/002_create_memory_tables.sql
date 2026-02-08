CREATE TABLE IF NOT EXISTS memory_entries (
    entry_id        UUID PRIMARY KEY,
    workspace_id    TEXT NOT NULL,
    bucket          TEXT NOT NULL CHECK (bucket IN ('global', 'workspace', 'ephemeral')),
    key             TEXT NOT NULL,
    value           JSONB NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL CHECK (status IN ('candidate', 'promoted', 'retracted')),
    confidence      DOUBLE PRECISION NOT NULL,
    source_event_id UUID NOT NULL REFERENCES events(event_id),
    promoted_at     TIMESTAMPTZ,
    retracted_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memory_workspace_status
    ON memory_entries (workspace_id, status);

CREATE INDEX IF NOT EXISTS idx_memory_workspace_bucket
    ON memory_entries (workspace_id, bucket);

CREATE INDEX IF NOT EXISTS idx_memory_expires
    ON memory_entries (expires_at) WHERE expires_at IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_source_event
    ON memory_entries (source_event_id);

CREATE TABLE IF NOT EXISTS projection_cursor (
    cursor_id       TEXT PRIMARY KEY DEFAULT 'global',
    last_event_ts   TIMESTAMPTZ NOT NULL,
    last_event_id   UUID NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
