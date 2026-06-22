"""Multi-product + renewal via configuration (the headline architectural proof).

Adding Dairy and renewal added only workflow definitions + a dairy rule; the
application service, aggregate, stores, maker-checker, audit and RLS are
unchanged. These tests prove a Dairy application flows through its OWN (different)
stages, the KCC workflow is untouched, and renewal runs as its own product."""

from alos_api.platform.workflow import get_workflow, known_products
from tests.conftest import auth


# --- the config itself ----------------------------------------------------

def test_products_registered():
    assert set(known_products()) >= {"KCC", "DAIRY", "KCC-RENEWAL"}


def test_kcc_workflow_unchanged_by_adding_dairy():
    kcc = get_workflow("KCC").names()
    assert "DocumentsExecuted" in kcc          # KCC still has documentation
    dairy = get_workflow("DAIRY").names()
    assert "DocumentsExecuted" not in dairy     # dairy deliberately omits it
    assert dairy[0] == "LeadCreated"
    assert get_workflow("KCC-RENEWAL").names()[0] == "RenewalInitiated"


# --- dairy end to end ------------------------------------------------------

def _dairy_to_sanction(client):
    app_id = client.post("/applications",
                         json={"applicant_name": "Lakshmi", "mobile": "9",
                               "product": "DAIRY"},
                         headers=auth()).json()["application_id"]
    client.post(f"/applications/{app_id}/link-customer",
                json={"customer_id": "D1"}, headers=auth())
    client.post(f"/applications/{app_id}/kyc",
                json={"aadhaar_number": "123456789012", "name": "Lakshmi"}, headers=auth())
    r = client.post(f"/assessment/{app_id}/dairy-eligibility",
                    json={"cattle": [{"animal_type": "buffalo", "count": 2}]},
                    headers=auth())
    assert r.json()["eligible"] is True
    assert r.json()["breakup"]["net_limit"] == "161000"
    client.post(f"/applications/{app_id}/memo/generate", headers=auth())
    client.post(f"/applications/{app_id}/advance/MakerReviewed", json={},
                headers=auth(user="m1", roles="Maker"))
    client.post(f"/applications/{app_id}/advance/CheckerReviewed", json={},
                headers=auth(user="c1", roles="Checker"))
    client.post(f"/applications/{app_id}/advance/Sanctioned", json={},
                headers=auth(user="a1", roles="SanctionAuthority"))
    return app_id


def test_dairy_full_flow_skips_documentation(client):
    app_id = _dairy_to_sanction(client)
    # Dairy disburses directly after sanction (no DocumentsExecuted stage)
    r = client.post(f"/applications/{app_id}/disburse", headers=auth())
    assert r.status_code == 200, r.text
    assert r.json()["stage"] == "Disbursed"
    assert r.json()["disbursement"]["amount"] == 161000.0
    r = client.post(f"/applications/{app_id}/cbs-post", headers=auth())
    assert r.json()["stage"] == "CbsPosted"

    types = [e["type"] for e in
             client.get(f"/applications/{app_id}/history", headers=auth()).json()]
    assert "application.DocumentsExecuted" not in types
    assert types[0] == "application.LeadCreated" and types[-1] == "application.CbsPosted"


def test_dairy_cannot_execute_documents(client):
    app_id = _dairy_to_sanction(client)
    # The documentation stage isn't in the dairy workflow -> rejected
    r = client.post(f"/applications/{app_id}/documents/execute", headers=auth())
    assert r.status_code == 409


def test_dairy_timeline_uses_dairy_workflow(client):
    app_id = _dairy_to_sanction(client)
    t = client.get(f"/applications/{app_id}/timeline", headers=auth()).json()
    assert t["product"] == "DAIRY"
    assert t["total"] == 10   # dairy has 10 stages (KCC has 11)
    assert all(s["name"] != "DocumentsExecuted" for s in t["timeline"])


# --- renewal end to end ----------------------------------------------------

def _kcc_to_cbs(client):
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
    client.post(f"/applications/{app_id}/advance/MakerReviewed", json={},
                headers=auth(user="m1", roles="Maker"))
    client.post(f"/applications/{app_id}/advance/CheckerReviewed", json={},
                headers=auth(user="c1", roles="Checker"))
    client.post(f"/applications/{app_id}/advance/Sanctioned", json={},
                headers=auth(user="a1", roles="SanctionAuthority"))
    client.post(f"/applications/{app_id}/documents/execute", headers=auth())
    client.post(f"/applications/{app_id}/disburse", headers=auth())
    client.post(f"/applications/{app_id}/cbs-post", headers=auth())
    return app_id


def test_renewal_flow(client):
    loan = _kcc_to_cbs(client)
    r = client.post(f"/applications/{loan}/renew", headers=auth())
    assert r.status_code == 201, r.text
    renewal = r.json()
    assert renewal["product"] == "KCC-RENEWAL"
    assert renewal["stage"] == "RenewalInitiated"
    rid = renewal["application_id"]

    # recompute (KCC engine), memo, maker, checker, renew
    client.post(f"/assessment/{rid}/eligibility",
                json={"parcels": [{"parcel_id": "P1", "area_hectares": 2.5, "verified": True}],
                      "crops": [{"parcel_id": "P1", "crop": "wheat", "season": "rabi",
                                 "area_hectares": 2.5}]}, headers=auth())
    client.post(f"/applications/{rid}/memo/generate", headers=auth())
    client.post(f"/applications/{rid}/advance/MakerReviewed", json={},
                headers=auth(user="m1", roles="Maker"))
    client.post(f"/applications/{rid}/advance/CheckerReviewed", json={},
                headers=auth(user="c1", roles="Checker"))
    r = client.post(f"/applications/{rid}/advance/Renewed", json={},
                    headers=auth(user="a1", roles="SanctionAuthority"))
    assert r.status_code == 200 and r.json()["stage"] == "Renewed"


def test_renewal_requires_live_loan(client):
    # a fresh KCC app (not yet disbursed) cannot be renewed
    app_id = client.post("/applications", json={"applicant_name": "X", "mobile": "9"},
                         headers=auth()).json()["application_id"]
    r = client.post(f"/applications/{app_id}/renew", headers=auth())
    assert r.status_code == 409
