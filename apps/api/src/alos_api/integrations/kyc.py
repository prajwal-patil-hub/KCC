"""KYC port + mock adapter.

Demonstrates the adapter framework end-to-end. The mock returns realistic,
deterministic fixtures and — critically — never echoes a raw Aadhaar number:
the result carries a *token reference* only (docs/06 Aadhaar handling).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

import httpx

from .base import Adapter, IntegrationError


@dataclass(frozen=True)
class KycResult:
    verified: bool
    name_match: bool
    aadhaar_token: str   # tokenised reference; raw Aadhaar is never stored/returned
    masked_aadhaar: str  # e.g. "XXXX-XXXX-1234" for display
    source: str


class KycPort(Protocol):
    def verify(self, *, aadhaar_number: str, name: str) -> KycResult: ...


def _tokenise(aadhaar_number: str) -> str:
    # Stand-in for a real tokenisation/vault call. Deterministic, one-way.
    return "aktn_" + hashlib.sha256(aadhaar_number.encode()).hexdigest()[:24]


def _mask(aadhaar_number: str) -> str:
    digits = "".join(c for c in aadhaar_number if c.isdigit())
    return "XXXX-XXXX-" + (digits[-4:] if len(digits) >= 4 else "????")


class MockKycAdapter(Adapter):
    name = "kyc"

    def verify(self, *, aadhaar_number: str, name: str) -> KycResult:
        def _do() -> KycResult:
            # Deterministic mock: 12-digit aadhaar + non-empty name => verified.
            digits = "".join(c for c in aadhaar_number if c.isdigit())
            ok = len(digits) == 12 and bool(name.strip())
            return KycResult(
                verified=ok,
                name_match=ok,
                aadhaar_token=_tokenise(aadhaar_number),
                masked_aadhaar=_mask(aadhaar_number),
                source="mock",
            )

        return self.call("verify", _do)


# --- vendor contract ------------------------------------------------------
#
# The KYC vendor/aggregator returns this shape (Aadhaar offline-eKYC style). This
# parser is the single boundary between their schema and our KycResult Port; the
# contract test pins this shape so the mock can never silently drift from it.


def assert_kyc_contract(result: KycResult) -> None:
    """Invariants every KYC adapter result must satisfy, mock or live."""
    assert isinstance(result.verified, bool)
    assert isinstance(result.name_match, bool)
    assert result.masked_aadhaar.startswith("XXXX-XXXX-"), "must be masked for display"
    if result.verified:
        # A successful verification must carry a tokenised reference; a failed one
        # legitimately has none.
        assert result.aadhaar_token, "verified result must carry a tokenised reference"


def parse_vendor_kyc(data: dict, *, name_match_threshold: float = 0.8) -> KycResult:
    """Map a vendor KYC response to our KycResult. Raises IntegrationError on a
    malformed/system response (so retries + circuit breaker engage)."""
    try:
        status = data["status"]
        kyc = data.get("kyc") or {}
    except (KeyError, TypeError) as exc:
        raise IntegrationError(f"Malformed KYC response: {data!r}") from exc

    if status not in ("SUCCESS", "FAILED"):
        raise IntegrationError(f"Unexpected KYC status: {status!r}")

    verified = status == "SUCCESS" and bool(kyc.get("verified"))
    score = float(kyc.get("name_match_score", 0) or 0)
    # Vendor gives us a token + masked id; we never receive/store the raw number.
    token = kyc.get("uid_token") or ""
    masked_raw = kyc.get("masked_uid", "")
    last4 = "".join(c for c in masked_raw if c.isdigit())[-4:] or "????"
    return KycResult(
        verified=verified,
        name_match=verified and score >= name_match_threshold,
        aadhaar_token=token,
        masked_aadhaar="XXXX-XXXX-" + last4,
        source="sandbox",
    )


class SandboxKycAdapter(Adapter):
    """Talks to a real KYC vendor *sandbox* over HTTP, behind the same Port as the
    mock. Enabled via ALOS_KYC_PROVIDER=sandbox. Resilience (retry/circuit
    breaker/audit) comes from Adapter.call; parsing comes from parse_vendor_kyc."""

    name = "kyc"

    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.Client | None = None,
        name_match_threshold: float = 0.8,
        consent_ref: str = "CONSENT-DEMO",
        **kw,
    ) -> None:
        kw.setdefault("mock_mode", False)
        super().__init__(**kw)
        self._base_url = base_url
        self._threshold = name_match_threshold
        self._consent_ref = consent_ref
        self._client = client or httpx.Client(base_url=base_url, timeout=5.0)

    def verify(self, *, aadhaar_number: str, name: str) -> KycResult:
        def _do() -> KycResult:
            resp = self._client.post(
                "/kyc/verify",
                json={
                    # The vendor legitimately needs the number; consent is captured
                    # and referenced (DPDP / Aadhaar Act, docs/06).
                    "aadhaar": aadhaar_number,
                    "name": name,
                    "consent": True,
                    "consent_ref": self._consent_ref,
                },
            )
            resp.raise_for_status()  # 5xx/4xx -> retry + breaker
            return parse_vendor_kyc(resp.json(), name_match_threshold=self._threshold)

        return self.call("verify", _do)
