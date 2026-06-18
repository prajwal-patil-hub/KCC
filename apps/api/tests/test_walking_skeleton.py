"""End-to-end tests for the Milestone 0 walking skeleton.

Proves the cross-cutting spine: auth, tenancy isolation, event-sourced
application lifecycle, server-side maker-checker, the eligibility engine wired
in, and the tamper-evident audit chain.
"""

from tests.conftest import auth


def test_health_is_open(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["integration_mode"] == "mock"


def test_unauthenticated_is_rejected(client):
    r = client.post("/applications", json={"applicant_name": "X", "mobile": "9"})
    assert r.status_code == 401


def _create_lead(client, **who):
    r = client.post(
        "/applications",
        json={"applicant_name": "Ramesh", "mobile": "9999999999"},
        headers=auth(**who),
    )
    assert r.status_code == 201, r.text
    return r.json()["application_id"]


def test_full_kcc_happy_path(client):
    app_id = _create_lead(client)

    # link customer
    r = client.post(
        f"/applications/{app_id}/link-customer",
        json={"customer_id": "C1", "farmer_class": "small"},
        headers=auth(),
    )
    assert r.status_code == 200 and r.json()["stage"] == "CustomerLinked"

    # KYC via mock adapter — only tokenised/masked aadhaar is persisted
    r = client.post(
        f"/applications/{app_id}/kyc",
        json={"aadhaar_number": "1234 5678 9012", "name": "Ramesh"},
        headers=auth(),
    )
    assert r.status_code == 200
    kyc = r.json()["kyc"]
    assert kyc["masked_aadhaar"] == "XXXX-XXXX-9012"
    assert kyc["aadhaar_token"].startswith("aktn_")
    assert "123456789012" not in str(kyc)  # raw aadhaar never stored

    # eligibility via the pure engine
    r = client.post(
        f"/assessment/{app_id}/eligibility",
        json={
            "parcels": [{"parcel_id": "P1", "area_hectares": 2.0, "verified": True}],
            "crops": [{"parcel_id": "P1", "crop": "wheat", "season": "rabi",
                       "area_hectares": 2.0}],
        },
        headers=auth(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["eligible"] is True
    assert r.json()["breakup"]["net_limit"] == "117000"

    # maker reviews
    r = client.post(f"/applications/{app_id}/advance/MakerReviewed",
                    json={"reason": "looks good"}, headers=auth(user="maker1"))
    assert r.status_code == 200

    # checker must be a different user (server-side maker-checker)
    r = client.post(f"/applications/{app_id}/advance/CheckerReviewed",
                    json={"reason": "verified"}, headers=auth(user="checker1",
                                                              roles="Checker"))
    assert r.status_code == 200 and r.json()["stage"] == "CheckerReviewed"

    # sanction
    r = client.post(f"/applications/{app_id}/advance/Sanctioned", json={},
                    headers=auth(user="officer1", roles="SanctionAuthority"))
    assert r.status_code == 200 and r.json()["stage"] == "Sanctioned"

    # history is the full event stream
    r = client.get(f"/applications/{app_id}/history", headers=auth())
    types = [e["type"] for e in r.json()]
    assert types == [
        "application.LeadCreated",
        "application.CustomerLinked",
        "application.KycCompleted",
        "application.EligibilityComputed",
        "application.MakerReviewed",
        "application.CheckerReviewed",
        "application.Sanctioned",
    ]


def test_maker_cannot_check_own_work(client):
    app_id = _create_lead(client, user="maker1")
    for stage in ("CustomerLinked", "KycCompleted"):
        # shortcut: drive via generic advance where possible
        pass
    client.post(f"/applications/{app_id}/link-customer",
                json={"customer_id": "C1"}, headers=auth(user="maker1"))
    client.post(f"/applications/{app_id}/kyc",
                json={"aadhaar_number": "123456789012", "name": "R"},
                headers=auth(user="maker1"))
    client.post(f"/assessment/{app_id}/eligibility",
                json={"parcels": [{"parcel_id": "P1", "area_hectares": 1,
                                   "verified": True}],
                      "crops": [{"parcel_id": "P1", "crop": "wheat",
                                 "season": "rabi", "area_hectares": 1}]},
                headers=auth(user="maker1"))
    client.post(f"/applications/{app_id}/advance/MakerReviewed",
                json={}, headers=auth(user="maker1"))
    # same user tries to check -> 409
    r = client.post(f"/applications/{app_id}/advance/CheckerReviewed",
                    json={}, headers=auth(user="maker1"))
    assert r.status_code == 409
    assert "different user" in r.json()["detail"].lower()


def test_invalid_transition_is_rejected(client):
    app_id = _create_lead(client)
    # cannot jump straight to Sanctioned
    r = client.post(f"/applications/{app_id}/advance/Sanctioned", json={},
                    headers=auth())
    assert r.status_code == 409


def test_tenant_isolation(client):
    app_id = _create_lead(client, tenant="bankA")
    # another tenant cannot read it
    r = client.get(f"/applications/{app_id}", headers=auth(tenant="bankB"))
    assert r.status_code == 403


def test_audit_chain_is_intact(client):
    _create_lead(client)
    r = client.get("/audit/verify", headers=auth())
    assert r.status_code == 200 and r.json()["chain_intact"] is True
