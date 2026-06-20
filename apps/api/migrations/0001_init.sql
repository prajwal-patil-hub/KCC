-- ALOS schema 0001 — event store + audit store with tenant Row-Level Security.
--
-- RLS is the DB-layer half of tenant isolation (ADR-0003). The app sets
-- app.tenant_id per transaction; these policies make Postgres itself reject any
-- row whose tenant_id differs — even if application code has a bug.
--
-- FORCE ROW LEVEL SECURITY is essential: the table owner (alos_app) would
-- otherwise BYPASS its own RLS policies.

-- ---------------------------------------------------------------------------
-- Event store (selective event sourcing — ADR-0002). Append-only.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS events CASCADE;
CREATE TABLE events (
    id              BIGSERIAL PRIMARY KEY,
    stream_id       TEXT        NOT NULL,
    sequence        INTEGER     NOT NULL,
    type            TEXT        NOT NULL,
    payload         JSONB       NOT NULL,
    tenant_id       TEXT        NOT NULL,
    actor_id        TEXT        NOT NULL,
    correlation_id  TEXT        NOT NULL,
    schema_version  INTEGER     NOT NULL DEFAULT 1,
    occurred_at     TEXT        NOT NULL,
    UNIQUE (stream_id, sequence)          -- optimistic concurrency guard
);
CREATE INDEX events_stream_idx ON events (stream_id, sequence);

ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE events FORCE  ROW LEVEL SECURITY;
CREATE POLICY events_tenant_isolation ON events
    USING      (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- Append-only: forbid UPDATE/DELETE even for the owner.
CREATE RULE events_no_update AS ON UPDATE TO events DO INSTEAD NOTHING;
CREATE RULE events_no_delete AS ON DELETE TO events DO INSTEAD NOTHING;

-- ---------------------------------------------------------------------------
-- Audit store (hash-chained, per tenant — docs/06). Append-only.
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS audit CASCADE;
CREATE TABLE audit (
    seq             BIGINT      NOT NULL,
    tenant_id       TEXT        NOT NULL,
    actor_id        TEXT        NOT NULL,
    action          TEXT        NOT NULL,
    resource        TEXT        NOT NULL,
    reason          TEXT,
    correlation_id  TEXT        NOT NULL,
    prev_hash       TEXT        NOT NULL,
    this_hash       TEXT        NOT NULL,
    at              TEXT        NOT NULL,
    PRIMARY KEY (tenant_id, seq)          -- per-tenant monotonic chain
);

ALTER TABLE audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit FORCE  ROW LEVEL SECURITY;
CREATE POLICY audit_tenant_isolation ON audit
    USING      (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE RULE audit_no_update AS ON UPDATE TO audit DO INSTEAD NOTHING;
CREATE RULE audit_no_delete AS ON DELETE TO audit DO INSTEAD NOTHING;
