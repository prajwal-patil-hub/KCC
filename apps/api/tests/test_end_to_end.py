"""Full KCC lifecycle: lead -> ... -> sanction -> documents -> disbursement ->
CBS posting, plus the correctness guarantees (idempotent money, saga
compensation, reconciliation, derived timeline/health)."""

from alos_api import deps
from alos_api.contexts.documentation.service import DocStep, DocumentationService
from alos_api.integrations.documents import (
    MockEsignAdapter,
    MockEstampAdapter,
    MockNeslAdapter,
)
from tests.conftest import auth


def _to_sanction(client):
    app_id = client.post("/applications",
                         json={"applicant_name": "Ramesh", "mobile": "9"},
                         headers=auth()).json()["application_id"]
    client.post(f"/applications/{app_id}/link-customer",
                json={"customer_id": "C1"}, headers=auth())
    client.post(f"/applications/{app_id}/kyc",
                json={"aadhaar_number": "123456789012", "name": "Ramesh"}, headers=auth())
    client.post(f"/assessment/{app_id}/eligibility",
                json={"parcels": [{"parcel_id": "P1", "area_hectares": 2.0, "verified": True}],
                      "crops": [{"parcel_id": "P1", "crop": "wheat", "season": "rabi",
                                 "area_hectares": 2.0}]}, headers=auth())
    client.post(f"/applications/{app_id}/memo/generate", headers=auth())
    client.post(f"/applications/{app_id}/advance/MakerReviewed",
                json={}, headers=auth(user="maker1", roles="Maker"))
    client.post(f"/applications/{app_id}/advance/CheckerReviewed",
                json={}, headers=auth(user="checker1", roles="Checker"))
    client.post(f"/applications/{app_id}/advance/Sanctioned",
                json={}, headers=auth(user="auth1", roles="SanctionAuthority"))
    return app_id


def test_full_lifecycle_to_cbs(client):
    app_id = _to_sanction(client)

    # documentation saga
    r = client.post(f"/applications/{app_id}/documents/execute", headers=auth())
    assert r.status_code == 200, r.text
    assert r.json()["stage"] == "DocumentsExecuted"
    assert set(r.json()["documents"]["references"]) == {"nesl", "estamp", "esign"}

    # disbursement (idempotent money event)
    r = client.post(f"/applications/{app_id}/disburse", headers=auth())
    assert r.status_code == 200, r.text
    assert r.json()["stage"] == "Disbursed"
    ref = r.json()["reference"]
    assert r.json()["disbursement"]["amount"] == 117000.0

    # CBS posting
    r = client.post(f"/applications/{app_id}/cbs-post", headers=auth())
    assert r.status_code == 200
    assert r.json()["stage"] == "CbsPosted"

    # reconciliation is clean (disbursed == posted)
    rec = client.get("/reconciliation/report", headers=auth()).json()
    assert rec["clean"] is True and rec["matched"] == 1

    # final event stream is the whole lifecycle
    types = [e["type"] for e in
             client.get(f"/applications/{app_id}/history", headers=auth()).json()]
    assert types[-3:] == [
        "application.DocumentsExecuted",
        "application.Disbursed",
        "application.CbsPosted",
    ]


def test_disbursement_is_idempotent(client):
    app_id = _to_sanction(client)
    client.post(f"/applications/{app_id}/documents/execute", headers=auth())

    first = client.post(f"/applications/{app_id}/disburse", headers=auth()).json()
    second = client.post(f"/applications/{app_id}/disburse", headers=auth()).json()

    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert first["reference"] == second["reference"]  # same money reference

    # exactly ONE Disbursed event despite two calls (scenario S1)
    types = [e["type"] for e in
             client.get(f"/applications/{app_id}/history", headers=auth()).json()]
    assert types.count("application.Disbursed") == 1


def test_documentation_saga_compensates_on_failure(client):
    app_id = _to_sanction(client)

    # Inject a documentation service whose eSign step fails -> nesl+estamp voided.
    failing = DocumentationService(
        [
            DocStep("nesl", MockNeslAdapter()),
            DocStep("estamp", MockEstampAdapter()),
            DocStep("esign", MockEsignAdapter(fail=True, max_retries=1)),
        ],
        deps._idempotency,
    )
    client.app.dependency_overrides[deps.get_documentation_service] = lambda: failing
    try:
        r = client.post(f"/applications/{app_id}/documents/execute", headers=auth())
    finally:
        client.app.dependency_overrides.clear()

    assert r.status_code == 409
    # earlier successful steps were compensated
    assert set(r.json()["detail"]["compensated"]) == {"nesl", "estamp"}
    # application did NOT advance past sanction
    assert client.get(f"/applications/{app_id}", headers=auth()).json()["stage"] == "Sanctioned"


def test_role_required_for_sanction(client):
    app_id = client.post("/applications", json={"applicant_name": "R", "mobile": "9"},
                         headers=auth()).json()["application_id"]
    client.post(f"/applications/{app_id}/link-customer", json={"customer_id": "C1"}, headers=auth())
    client.post(f"/applications/{app_id}/kyc",
                json={"aadhaar_number": "123456789012", "name": "R"}, headers=auth())
    client.post(f"/assessment/{app_id}/eligibility",
                json={"parcels": [{"parcel_id": "P1", "area_hectares": 1, "verified": True}],
                      "crops": [{"parcel_id": "P1", "crop": "wheat", "season": "rabi",
                                 "area_hectares": 1}]}, headers=auth())
    client.post(f"/applications/{app_id}/memo/generate", headers=auth())
    client.post(f"/applications/{app_id}/advance/MakerReviewed", json={},
                headers=auth(user="maker1", roles="Maker"))
    client.post(f"/applications/{app_id}/advance/CheckerReviewed", json={},
                headers=auth(user="checker1", roles="Checker"))
    # a clerk without SanctionAuthority cannot sanction
    r = client.post(f"/applications/{app_id}/advance/Sanctioned", json={},
                    headers=auth(user="clerk1", roles="Clerk"))
    assert r.status_code == 403


def test_timeline_and_health_score(client):
    app_id = _to_sanction(client)
    t = client.get(f"/applications/{app_id}/timeline", headers=auth()).json()
    assert t["product"] == "KCC"
    assert t["current_stage"] == "Sanctioned"
    assert t["total"] == 11
    assert t["completed"] == 8
    # 8/11 ~ 73, no skip penalty
    assert t["health_score"] == round(100 * 8 / 11)
    assert any(s["name"] == "Disbursed" and s["status"] == "pending" for s in t["timeline"])
