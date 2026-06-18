# 02 — Domain Model & Bounded Contexts

Domain-Driven Design view. The lending lifecycle decomposes into bounded
contexts; each becomes a module (ADR-0001). Aggregates own their invariants.

## Bounded contexts (the map)

```
                       ┌────────────────────────────────────────────┐
                       │              Platform / shared              │
                       │  Identity & Access · Tenancy · Config ·     │
                       │  Audit · Event Store · Notification         │
                       └────────────────────────────────────────────┘
   Acquisition            Assessment                 Decision & Fulfilment
 ┌───────────┐  ┌──────────────────────────┐  ┌──────────────────────────────┐
 │ Lead      │  │ Land (verify)            │  │ Underwriting (AI + rules)    │
 │ Customer  │→ │ Crop                     │→ │ Credit Memo                  │
 │ KYC       │  │ Bureau / Liability       │  │ Approval (maker/checker/hier)│
 └───────────┘  │ Eligibility & Limit      │  │ Documentation (NESL/eStamp/  │
                └──────────────────────────┘  │   eSign) · Disbursement·CBS  │
                                              │ Servicing/Renewal (future)    │
                                              └──────────────────────────────┘
```

## Core aggregates & key invariants

### LoanApplication  (event-sourced — ADR-0002)
The spine. Holds the workflow state and links to all assessment artefacts.
- **Invariants:** can only advance through allowed workflow transitions; a
  `requiresChecker` transition cannot be performed by the maker's user id;
  cannot reach `Sanctioned` without a valid Eligibility result + completed
  approval chain; cannot reach `Disbursed` without `Documentation.complete`.
- **Key events:** `LeadCreated, CustomerLinked, KycCompleted, LandAdded,
  LandVerified, CropAdded, BureauPulled, EligibilityComputed, MemoGenerated,
  MakerReviewed, CheckerReviewed, Sanctioned, DocumentsExecuted, Disbursed,
  CbsPosted, RenewalInitiated, Closed`.

### Customer / Farmer
- Identity (tokenised Aadhaar ref, PAN, CKYC id), farmer classification
  (marginal/small/other), contact, consent artefacts (DPDP).
- **Invariant:** PII fields encrypted; Aadhaar stored only as a token reference.

### Land  (parcel)
- Survey/khasra no., area, location, ownership share, encumbrance status,
  mutation status, verification result, source adapter + fetched record hash.
- **Invariant:** a parcel used in eligibility must be `Verified` or carry a
  recorded exception override (with actor + reason).

### Crop
- Crop type, season (Kharif/Rabi/Zaid), area sown, irrigation, expected cycle.
- Links to **Scale of Finance** (district × crop × year) for the limit math.

### EligibilityResult  (value object, deterministic — ADR-0005)
- Inputs snapshot (land, crop, SoF version, policy version, liabilities).
- Outputs: crop loan component, post-harvest (10%), maintenance (20%), insurance,
  **KCC limit**, collateral-free flag, PSL tag, subvention eligibility.
- **Invariant:** fully reproducible from inputs + config versions.

### CreditDecision
- Deterministic outputs + AI memo + risk flags + confidence + human override.
- **Invariant:** carries `model`, `prompt_version`, `inputs_hash`.

### MoneyEvent  (event-sourced)
- Sanction limit set, disbursement, posting, reversal — each idempotent, each
  reconciled against CBS.

## Ubiquitous language (selected)
- **SoF** — Scale of Finance (₹/ha per crop, set by DLTC, annual).
- **KCC limit** — sanctioned crop-credit limit (formula in prompt v2 §3).
- **MISS** — Modified Interest Subvention Scheme.
- **PSL** — Priority Sector Lending (KCC crop = PSL-Agriculture).
- **IRAC** — Income Recognition & Asset Classification (Standard/SMA/NPA).
- **Maker/Checker** — the user who acts vs the user who independently verifies.

## Context → module → (future) service mapping
Each context above maps 1:1 to a Python package in the monolith. Likely *first*
extractions when scaling: Document/AI processing (CPU/GPU heavy), Notification
(spiky), Land verification (slow external I/O).
