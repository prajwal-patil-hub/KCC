"""Test-only per-stage bypass escape hatch."""

from alos_api import deps
from alos_api.config import Settings
from tests.conftest import auth


def _enable_bypass(client):
    client.app.dependency_overrides[deps.get_settings] = \
        lambda: Settings(test_bypass=True)


def test_bypass_disabled_by_default(client):
    app_id = client.post("/applications", json={"applicant_name": "R", "mobile": "9"},
                         headers=auth()).json()["application_id"]
    r = client.post(f"/applications/{app_id}/bypass", json={"reason": "x"}, headers=auth())
    assert r.status_code == 403
    assert "ALOS_TEST_BYPASS" in r.json()["detail"]


def test_bypass_advances_one_stage_when_enabled(client):
    _enable_bypass(client)
    try:
        app_id = client.post("/applications", json={"applicant_name": "R", "mobile": "9"},
                             headers=auth()).json()["application_id"]
        # bypass straight past CustomerLinked without providing any data
        r = client.post(f"/applications/{app_id}/bypass",
                        json={"reason": "no customer system"}, headers=auth())
        assert r.status_code == 200
        assert r.json()["stage"] == "CustomerLinked"
    finally:
        client.app.dependency_overrides.clear()


def test_bypass_can_walk_the_whole_lifecycle(client):
    _enable_bypass(client)
    try:
        app_id = client.post("/applications", json={"applicant_name": "R", "mobile": "9"},
                             headers=auth()).json()["application_id"]
        # keep bypassing until the final stage; must terminate at CbsPosted
        last = "LeadCreated"
        for _ in range(20):
            r = client.post(f"/applications/{app_id}/bypass", json={}, headers=auth())
            if r.status_code == 409:
                break
            assert r.status_code == 200
            last = r.json()["stage"]
        assert last == "CbsPosted"
        # every step is recorded and tagged as a bypass in the audit history
        hist = client.get(f"/applications/{app_id}/history", headers=auth()).json()
        bypassed = [e for e in hist if e["payload"].get("_bypassed")]
        assert len(bypassed) >= 9  # all stages after LeadCreated
    finally:
        client.app.dependency_overrides.clear()


def test_bypass_at_final_stage_is_rejected(client):
    _enable_bypass(client)
    try:
        app_id = client.post("/applications", json={"applicant_name": "R", "mobile": "9"},
                             headers=auth()).json()["application_id"]
        for _ in range(20):
            if client.post(f"/applications/{app_id}/bypass", json={}, headers=auth()).status_code == 409:
                break
        r = client.post(f"/applications/{app_id}/bypass", json={}, headers=auth())
        assert r.status_code == 409
        assert "final stage" in r.json()["detail"].lower()
    finally:
        client.app.dependency_overrides.clear()


def test_health_reports_bypass_flag(client):
    _enable_bypass(client)
    try:
        assert client.get("/health").json()["test_bypass"] is True
    finally:
        client.app.dependency_overrides.clear()
    assert client.get("/health").json()["test_bypass"] is False
