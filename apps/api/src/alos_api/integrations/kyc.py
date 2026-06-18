"""KYC port + mock adapter.

Demonstrates the adapter framework end-to-end. The mock returns realistic,
deterministic fixtures and — critically — never echoes a raw Aadhaar number:
the result carries a *token reference* only (docs/06 Aadhaar handling).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from .base import Adapter


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
