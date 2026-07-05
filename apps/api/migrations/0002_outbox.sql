-- ALOS schema 0002 — transactional outbox (ADR-0002).
--
-- The outbox row is written in the SAME transaction as the domain event (see
-- PostgresEventStore.append), so there is no dual-write: either both the event
-- and its outbox entry commit, or neither does. A separate relay later publishes
-- unpublished rows to the message bus (at-least-once) and stamps published_at.
--
-- The relay is trusted infrastructure (not a tenant), so it runs under a
-- BYPASSRLS role; tenants themselves are still confined by RLS.

DROP TABLE IF EXISTS outbox CASCADE;
CREATE TABLE outbox (
    id              BIGSERIAL PRIMARY KEY,
    stream_id       TEXT        NOT NULL,
    sequence        INTEGER     NOT NULL,
    type            TEXT        NOT NULL,
    payload         JSONB       NOT NULL,
    tenant_id       TEXT        NOT NULL,
    correlation_id  TEXT        NOT NULL,
    occurred_at     TEXT        NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at    TIMESTAMPTZ                         -- NULL until relayed
);
CREATE INDEX outbox_unpublished_idx ON outbox (id) WHERE published_at IS NULL;

ALTER TABLE outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox FORCE  ROW LEVEL SECURITY;
CREATE POLICY outbox_tenant_isolation ON outbox
    USING      (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- Let the relay role (if present) drain and stamp the outbox. Guarded so the
-- migration is portable to environments without the relay role.
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'alos_relay') THEN
        GRANT SELECT, UPDATE ON outbox TO alos_relay;
    END IF;
END $$;
