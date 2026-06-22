"""A tiny stand-in for a KYC vendor sandbox, for local dev and the live HTTP
contract check. It mimics an Aadhaar offline-eKYC aggregator response.

Run:  PYTHONPATH=src uvicorn scripts.kyc_sandbox:app --port 9099
Then: ALOS_KYC_PROVIDER=sandbox ALOS_KYC_SANDBOX_URL=http://127.0.0.1:9099 uvicorn alos_api.main:app

This is NOT the real vendor — it just emits the agreed contract shape so the
SandboxKycAdapter (and its parser) can be exercised against a real socket.
"""

from __future__ import annotations

import hashlib

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="KYC Vendor Sandbox")


class VerifyBody(BaseModel):
    aadhaar: str
    name: str
    consent: bool = False
    consent_ref: str | None = None


@app.post("/kyc/verify")
def verify(body: VerifyBody):
    digits = "".join(c for c in body.aadhaar if c.isdigit())
    ok = len(digits) == 12 and bool(body.name.strip()) and body.consent
    token = "uidtkn_" + hashlib.sha256(body.aadhaar.encode()).hexdigest()[:20]
    return {
        "txn_id": "TXN-" + hashlib.sha256(body.aadhaar.encode()).hexdigest()[:8],
        "status": "SUCCESS" if ok else "FAILED",
        "kyc": {
            "name": body.name,
            "name_match_score": 0.97 if ok else 0.0,
            "verified": ok,
            "uid_token": token,
            "masked_uid": "XXXXXXXX" + (digits[-4:] if len(digits) >= 4 else "0000"),
        },
    }
