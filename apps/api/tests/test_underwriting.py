"""Risk / Fraud / Compliance agents: deterministic scoring + AI-optional narrative."""

from alos_api import deps
from alos_api.contexts.credit_memo.provider import MockLLMProvider, NullProvider
from alos_api.contexts.underwriting.agents import (
    UnderwritingService,
    assess_risk,
    check_compliance,
    detect_fraud,
)
from tests.conftest import auth

ELIG_GOOD = {"eligible": True, "psl_category": "PSL-Agriculture",
             "collateral_free": True,
             "breakup": {"net_limit": "117000", "gross_limit": "117000",
                         "liability_offset": "0"}}
KYC_OK = {"verified": True, "name_match": True, "aadhaar_token": "aktn_x"}


def test_risk_low_for_clean_application():
    score, band, drivers = assess_risk(ELIG_GOOD)
    assert band == "Low" and score < 30


def test_risk_high_when_not_eligible():
    score, band, _ = assess_risk({"eligible": False, "breakup": {}})
    assert band == "High" and score > 60


def test_fraud_flags_unverified_kyc():
    assert "kyc_unverified" in detect_fraud({"verified": False}, ELIG_GOOD)
    assert "name_mismatch" in detect_fraud(
        {"verified": True, "name_match": False}, ELIG_GOOD)
    assert detect_fraud(KYC_OK, ELIG_GOOD) == []


def test_compliance_fails_without_kyc():
    passed, issues = check_compliance({}, ELIG_GOOD)
    assert passed is False and any("KYC" in i for i in issues)


def test_compliance_passes_clean():
    passed, issues = check_compliance(KYC_OK, ELIG_GOOD)
    assert passed is True


def test_assessment_without_ai_uses_deterministic_narrative():
    uw = UnderwritingService(NullProvider())
    r = uw.assess(applicant_name="Ramesh", kyc=KYC_OK, eligibility=ELIG_GOOD)
    assert r.ai_used is False
    assert r.risk_band == "Low"
    assert "Risk Low" in r.narrative
    assert r.requires_human_review is True  # MVP: always human-reviewed


def test_assessment_with_ai_adds_narrative():
    uw = UnderwritingService(MockLLMProvider(healthy=True))
    r = uw.assess(applicant_name="Ramesh", kyc=KYC_OK, eligibility=ELIG_GOOD)
    assert r.ai_used is True and r.model == "mock"
    # deterministic figures still present alongside the AI text
    assert "Risk Low" in r.narrative


def test_underwriting_endpoint_and_memo_carries_it(client):
    app_id = client.post("/applications", json={"applicant_name": "Ramesh", "mobile": "9"},
                         headers=auth()).json()["application_id"]
    client.post(f"/applications/{app_id}/link-customer", json={"customer_id": "C1"}, headers=auth())
    client.post(f"/applications/{app_id}/kyc",
                json={"aadhaar_number": "123456789012", "name": "Ramesh"}, headers=auth())
    client.post(f"/assessment/{app_id}/eligibility",
                json={"parcels": [{"parcel_id": "P1", "area_hectares": 2.0, "verified": True}],
                      "crops": [{"parcel_id": "P1", "crop": "wheat", "season": "rabi",
                                 "area_hectares": 2.0}]}, headers=auth())

    # advisory preview endpoint
    pre = client.get(f"/applications/{app_id}/underwriting", headers=auth()).json()
    assert pre["risk_band"] == "Low"
    assert pre["compliance_passed"] is True
    assert pre["fraud_flags"] == []

    # memo carries the underwriting summary
    memo = client.post(f"/applications/{app_id}/memo/generate", headers=auth()).json()["memo"]
    assert "underwriting" in memo
    assert memo["underwriting"]["risk_band"] == "Low"
