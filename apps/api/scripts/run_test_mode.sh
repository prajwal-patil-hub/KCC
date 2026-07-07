#!/usr/bin/env bash
# Run ALOS in full TEST mode: in-memory stores, all integrations mocked, AI off,
# and the per-stage bypass enabled. Nothing external is required.
#
#   bash apps/api/scripts/run_test_mode.sh
#   → API + web workspace at http://localhost:8000/app/
set -euo pipefail
cd "$(dirname "$0")/.."          # apps/api

export ALOS_STORAGE=memory        # no database needed
export ALOS_INTEGRATION_MODE=mock # Aadhaar/CBS/NESL/... all mocked
export ALOS_LLM_PROVIDER=none      # AI off → memo falls back to template/skip
export ALOS_TEST_BYPASS=1          # enable ⏭ bypass on every stage
export PYTHONPATH=src

echo "ALOS test mode → http://localhost:${PORT:-8000}/app/  (bypass ON, all mocked)"
exec python -m uvicorn alos_api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
