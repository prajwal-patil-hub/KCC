"""KYC vendor contract test (ADR-0006).

A contract test pins the vendor's response *shape* and proves our adapter parses
it correctly — and that the mock stays consistent with the same KycResult
contract, so it can't silently drift from the real integration.

Uses httpx.MockTransport (no network) so it is deterministic and CI-safe.
"""

from __future__ import annotations

import httpx
import pytest

from alos_api.integrations.base import IntegrationError
from alos_api.integrations.kyc import (
    MockKycAdapter,
    SandboxKycAdapter,
    assert_kyc_contract,
    parse_vendor_kyc,
)

# --- the pinned contract --------------------------------------------------
CONTRACT_SUCCESS = {
    "txn_id": "TXN-abc123",
    "status": "SUCCESS",
    "kyc": {
        "name": "Ramesh Kumar",
        "name_match_score": 0.97,
        "verified": True,
        "uid_token": "uidtkn_deadbeefcafe",
        "masked_uid": "XXXXXXXX9012",
    },
}
CONTRACT_FAILED = {
    "txn_id": "TXN-def456",
    "status": "FAILED",
    "kyc": {"name": "", "name_match_score": 0.0, "verified": False,
            "uid_token": "", "masked_uid": ""},
}


def _adapter_with(handler) -> SandboxKycAdapter:
    client = httpx.Client(transport=httpx.MockTransport(handler),
                          base_url="http://vendor.test")
    return SandboxKycAdapter("http://vendor.test", client=client, max_retries=2)


def test_parser_maps_success_contract():
    r = parse_vendor_kyc(CONTRACT_SUCCESS)
    assert r.verified is True
    assert r.name_match is True
    assert r.aadhaar_token == "uidtkn_deadbeefcafe"
    assert r.masked_aadhaar == "XXXX-XXXX-9012"
    assert r.source == "sandbox"
    assert_kyc_contract(r)


def test_parser_maps_failed_contract():
    r = parse_vendor_kyc(CONTRACT_FAILED)
    assert r.verified is False
    assert r.name_match is False
    assert_kyc_contract(r)


def test_low_name_match_is_not_verified():
    data = {**CONTRACT_SUCCESS, "kyc": {**CONTRACT_SUCCESS["kyc"],
                                        "name_match_score": 0.4}}
    r = parse_vendor_kyc(data, name_match_threshold=0.8)
    assert r.verified is True and r.name_match is False


def test_malformed_response_raises():
    with pytest.raises(IntegrationError):
        parse_vendor_kyc({"unexpected": "shape"})


def test_sandbox_adapter_parses_over_http():
    r = _adapter_with(lambda req: httpx.Response(200, json=CONTRACT_SUCCESS)) \
        .verify(aadhaar_number="1234 5678 9012", name="Ramesh Kumar")
    assert r.verified is True
    assert r.aadhaar_token == "uidtkn_deadbeefcafe"
    assert "123456789012" not in str(r)  # raw aadhaar never returned/stored


def test_sandbox_adapter_sends_consent():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        import json
        seen.update(json.loads(req.content))
        return httpx.Response(200, json=CONTRACT_SUCCESS)

    _adapter_with(handler).verify(aadhaar_number="123456789012", name="R")
    assert seen["consent"] is True and seen["consent_ref"]


def test_server_error_retries_then_raises():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={"error": "upstream down"})

    with pytest.raises(IntegrationError):
        _adapter_with(handler).verify(aadhaar_number="123456789012", name="R")
    assert calls["n"] == 2  # retried (max_retries=2) before giving up


def test_mock_and_sandbox_satisfy_same_contract():
    # The mock's success output must obey the same invariants the vendor parser
    # produces — this is what keeps the mock honest.
    mock = MockKycAdapter().verify(aadhaar_number="123456789012", name="Ramesh")
    vendor = parse_vendor_kyc(CONTRACT_SUCCESS)
    assert_kyc_contract(mock)
    assert_kyc_contract(vendor)
    assert mock.verified == vendor.verified is True
    assert mock.masked_aadhaar.startswith("XXXX-XXXX-")
