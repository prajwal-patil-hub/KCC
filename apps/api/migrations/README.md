# Migrations

Plain SQL migrations for the durable stores (event store + audit store).

`0001_init.sql` creates the `events` and `audit` tables with **tenant
Row-Level Security** (ADR-0003): every tenant-scoped row carries `tenant_id`, and
`USING` + `WITH CHECK` policies tie reads and writes to the `app.tenant_id` GUC
the application sets per transaction. `FORCE ROW LEVEL SECURITY` ensures even the
table owner is subject to the policies. `UPDATE`/`DELETE` are rewritten to NOTHING
so both stores are append-only.

## Apply

```bash
# create a NON-superuser, NON-BYPASSRLS role (RLS is skipped for superusers!)
sudo -u postgres psql -c "CREATE ROLE alos_app LOGIN PASSWORD 'alos_pw' NOSUPERUSER NOBYPASSRLS;"
sudo -u postgres psql -c "CREATE DATABASE alos OWNER alos_app;"

psql postgresql://alos_app:alos_pw@127.0.0.1:5432/alos -f 0001_init.sql
```

## Use the Postgres backend

```bash
ALOS_STORAGE=postgres \
ALOS_DATABASE_URL=postgresql://alos_app:alos_pw@127.0.0.1:5432/alos \
PYTHONPATH=src uvicorn alos_api.main:app
```

When `ALOS_STORAGE=memory` (default) the app runs entirely in-memory with no DB,
so dev/CI without Postgres still work. The RLS test suite
(`tests/test_postgres_rls.py`) runs only when `ALOS_DATABASE_URL` is set.
