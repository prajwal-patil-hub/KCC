# Run ALOS on a MacBook — beginner guide

No prior experience needed. Copy each command into **Terminal** and press Return.
Total time: ~10 minutes. This runs everything **self-contained** — no database, no
accounts, nothing external.

> Works on Apple Silicon (M1/M2/M3/M4) and Intel Macs.

---

## Step 0 — Open Terminal
Press **⌘ (Command) + Space**, type **Terminal**, press **Return**. A window opens
where you type commands.

## Step 1 — Install Homebrew (the macOS software installer)
Paste this and press Return (it may ask for your Mac password — typing shows
nothing, that's normal):
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
When it finishes, it prints 2 lines under **"Next steps"** starting with
`echo >> ...` and `eval ...`. **Copy-paste and run those two lines** (Apple Silicon
only) so `brew` works. Then check:
```bash
brew --version
```
You should see a version number.

## Step 2 — Install Python and Git
```bash
brew install python git
```
Check they work:
```bash
python3 --version     # should say Python 3.11 (or newer)
git --version
```

## Step 3 — Download the project
```bash
cd ~/Desktop
git clone https://github.com/prajwal-patil-hub/KCC.git
cd KCC
git checkout claude/architecture-planning-hgztvk
```
The first `git clone` may open a window asking you to **sign in to GitHub** — log in
with your GitHub account (it's your repo). If a browser sign-in appears, approve it.

> Now you're inside the project folder (`~/Desktop/KCC`). Every command below is run
> from here. If you close Terminal, come back with `cd ~/Desktop/KCC` first.

## Step 4 — Create an isolated Python environment
This keeps the project's packages separate from your Mac's system Python.
```bash
python3 -m venv .venv
source .venv/bin/activate
```
Your prompt now starts with `(.venv)`. That means it's active.
(You'll run `source .venv/bin/activate` again each time you reopen Terminal.)

## Step 5 — Install the project's packages
```bash
pip install -e packages/eligibility-engine
pip install fastapi uvicorn "pydantic>=2" pydantic-settings httpx pytest
```
The quotes around `"pydantic>=2"` matter — don't remove them.

## Step 6 — Run it 🚀
```bash
bash apps/api/scripts/run_test_mode.sh
```
You'll see: `ALOS test mode → http://localhost:8000/app/  (bypass ON, all mocked)`.
**Leave this Terminal window open** — it's the running server.

## Step 7 — Open the app
Open **Safari or Chrome** and go to:
```
http://localhost:8000/app/
```
You'll see the ALOS workspace. Try it:
1. Pick a product (KCC or Dairy), click **Create & run to eligibility**.
2. Walk the steps: generate the memo → maker → checker → sanction → disburse → CBS.
3. Stuck on any step? Click **⏭ Bypass step (test)** to force past it.

You can also open the built-in API docs at **http://localhost:8000/docs**.

## Step 8 — Stop / start again
- **Stop the server:** click the Terminal window and press **Control + C**.
- **Start again later:**
  ```bash
  cd ~/Desktop/KCC
  source .venv/bin/activate
  bash apps/api/scripts/run_test_mode.sh
  ```

## (Optional) Run the automated tests
Open a **second** Terminal window (⌘N), then:
```bash
cd ~/Desktop/KCC && source .venv/bin/activate
cd packages/eligibility-engine && PYTHONPATH=src python -m pytest -q   # engine tests
cd ../../apps/api && PYTHONPATH=src python -m pytest -q                # app tests
```

---

## Troubleshooting
- **`command not found: brew`** → you skipped the two "Next steps" lines in Step 1.
  Re-run them (Apple Silicon: they add `/opt/homebrew/bin` to your PATH).
- **`command not found: python3`** → run `brew install python` again, then open a
  new Terminal window.
- **`Address already in use` / port 8000 busy** → run on another port:
  ```bash
  PORT=8001 bash apps/api/scripts/run_test_mode.sh
  ```
  then open `http://localhost:8001/app/`.
- **The page won't load** → make sure the Step 6 Terminal is still running (it must
  stay open) and you typed `http://` not `https://`.
- **`(.venv)` isn't showing** → run `source .venv/bin/activate` from inside `~/Desktop/KCC`.

## What "test mode" means
The run script sets everything to safe, offline defaults:
`ALOS_STORAGE=memory` (no database), `ALOS_INTEGRATION_MODE=mock` (no real
Aadhaar/CBS/etc.), `ALOS_LLM_PROVIDER=none` (AI off — the memo falls back to a
template), and `ALOS_TEST_BYPASS=1` (the ⏭ bypass button on every step). Nothing you
do here touches any real system.

## Later: trying a real database (optional, not needed to test)
Only if you want the Postgres features (RLS + outbox):
```bash
brew install postgresql@16 && brew services start postgresql@16
createdb alos
psql alos -c "CREATE ROLE alos_app LOGIN PASSWORD 'alos_pw' NOSUPERUSER NOBYPASSRLS;"
psql alos -c "CREATE ROLE alos_relay LOGIN PASSWORD 'relay_pw' NOSUPERUSER BYPASSRLS;"
psql alos -f apps/api/migrations/0001_init.sql
psql alos -f apps/api/migrations/0002_outbox.sql
pip install "psycopg[binary]" psycopg_pool
# then run with the DB instead of in-memory:
ALOS_STORAGE=postgres \
ALOS_DATABASE_URL=postgresql://alos_app:alos_pw@localhost:5432/alos \
ALOS_TEST_BYPASS=1 PYTHONPATH=apps/api/src \
  python -m uvicorn alos_api.main:app --port 8000
```
