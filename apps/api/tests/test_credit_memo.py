"""Credit-Memo agent: AI path + every graceful fallback when AI is unavailable.

The core guarantee under test: the memo step can ALWAYS be completed and the
workflow proceeds, whether or not AI is running.
"""

from alos_api import deps
from alos_api.contexts.credit_memo.agent import CreditMemoAgent
from alos_api.contexts.credit_memo.provider import MockLLMProvider, NullProvider
from tests.conftest import auth


def _drive_to_eligibility(client, who):
    r = client.post("/applications",
                    json={"applicant_name": "Sita", "mobile": "9000000000"},
                    headers=auth(**who))
    app_id = r.json()["application_id"]
    client.post(f"/applications/{app_id}/link-customer",
                json={"customer_id": "C9", "farmer_class": "marginal"},
                headers=auth(**who))
    client.post(f"/applications/{app_id}/kyc",
                json={"aadhaar_number": "123456789012", "name": "Sita"},
                headers=auth(**who))
    client.post(f"/assessment/{app_id}/eligibility",
                json={"parcels": [{"parcel_id": "P1", "area_hectares": 2.0,
                                   "verified": True}],
                      "crops": [{"parcel_id": "P1", "crop": "wheat",
                                 "season": "rabi", "area_hectares": 2.0}]},
                headers=auth(**who))
    return app_id


# --- agent unit tests -----------------------------------------------------

ELIG = {"eligible": True, "policy_version": "kcc-2026.1",
        "breakup": {"net_limit": "117000", "gross_limit": "117000"},
        "collateral_free": True, "psl_category": "PSL-Agriculture"}


def test_no_ai_falls_back_to_template():
    agent = CreditMemoAgent(NullProvider())
    r = agent.generate(applicant_name="Sita", eligibility=ELIG)
    assert r.mode == "template"
    assert r.ai_available is False
    assert "CREDIT MEMO" in r.narrative
    assert r.fallback_reason


def test_ai_available_produces_ai_memo():
    agent = CreditMemoAgent(MockLLMProvider(healthy=True))
    r = agent.generate(applicant_name="Sita", eligibility=ELIG)
    assert r.mode == "ai"
    assert r.ai_available is True
    assert r.confidence == 0.82
    assert r.citations  # grounded
    # The deterministic figures are still attached to the AI narrative.
    assert "NET KCC LIMIT" in r.narrative


def test_ai_runtime_failure_falls_back_to_template():
    agent = CreditMemoAgent(MockLLMProvider(healthy=True, fail=True))
    r = agent.generate(applicant_name="Sita", eligibility=ELIG)
    assert r.mode == "template"
    assert "AI call failed" in r.fallback_reason


def test_manual_and_skip_modes():
    agent = CreditMemoAgent(NullProvider())
    m = agent.manual(applicant_name="Sita", eligibility=ELIG, text="Hand-written memo")
    assert m.mode == "manual" and m.narrative == "Hand-written memo"
    s = agent.skip(applicant_name="Sita", eligibility=ELIG, reason="Branch override")
    assert s.mode == "skipped" and s.note == "Branch override"


# --- API tests ------------------------------------------------------------

def test_ai_health_reports_unavailable_by_default(client):
    r = client.get("/ai/health", headers=auth())
    body = r.json()
    assert body["ai_available"] is False
    assert body["provider"] == "none"
    assert body["fallback_options"] == ["template", "manual", "skip"]


def test_generate_endpoint_uses_template_when_ai_off(client):
    app_id = _drive_to_eligibility(client, {})
    r = client.post(f"/applications/{app_id}/memo/generate", headers=auth())
    assert r.status_code == 200
    assert r.json()["memo"]["mode"] == "template"
    assert r.json()["stage"] == "MemoGenerated"


def test_skip_requires_reason_and_advances(client):
    app_id = _drive_to_eligibility(client, {})
    # too-short reason rejected by validation
    bad = client.post(f"/applications/{app_id}/memo/skip",
                      json={"reason": "x"}, headers=auth())
    assert bad.status_code == 422
    ok = client.post(f"/applications/{app_id}/memo/skip",
                     json={"reason": "AI down; manager approved fast-track"},
                     headers=auth())
    assert ok.status_code == 200
    assert ok.json()["memo"]["mode"] == "skipped"
    assert ok.json()["stage"] == "MemoGenerated"


def test_manual_memo_endpoint_advances(client):
    app_id = _drive_to_eligibility(client, {})
    r = client.post(f"/applications/{app_id}/memo/manual",
                    json={"text": "Officer's manual assessment: approve."},
                    headers=auth())
    assert r.status_code == 200
    assert r.json()["memo"]["mode"] == "manual"


def test_ai_health_available_when_provider_mock(client):
    # Simulate "AI is running" by overriding the agent dependency, and confirm
    # the UI would see it as available with no fallback options forced.
    client.app.dependency_overrides[deps.get_credit_memo_agent] = (
        lambda: CreditMemoAgent(MockLLMProvider(healthy=True))
    )
    try:
        r = client.get("/ai/health", headers=auth())
        assert r.json()["ai_available"] is True
        assert r.json()["provider"] == "mock"
        assert r.json()["fallback_options"] == []
    finally:
        client.app.dependency_overrides.clear()
