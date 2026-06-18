# 06 — Security & Compliance

Security is a first-class concern from increment 1 (not "phase 13"). Drivers #2
and #4: auditability and PII protection.

## Identity & access
- **OIDC SSO** for staff; short-lived tokens; refresh rotation.
- **RBAC** for coarse roles (FieldAgent, Maker, Checker, CreditOfficer,
  BranchManager, RegionalManager, SanctionAuthority, Admin, Auditor).
- **ABAC** for fine rules: tenant, branch, product, **amount band**, region.
- **Separation of Duties** enforced server-side: maker ≠ checker; no single
  role spans incompatible duties.

## Tenancy isolation
- Postgres **RLS** + app-layer tenant guard (ADR-0003). Negative isolation tests
  in CI (Tenant A token must get 0 rows of Tenant B).

## PII & data protection
- **Aadhaar:** tokenise — store a reference/Virtual ID, never the raw number in
  app tables; mask in UI and logs; offline eKYC where possible; **consent
  captured and stored** (Aadhaar Act / UIDAI norms).
- **PAN & other PII:** field-level encryption at rest; TLS 1.2+ in transit.
- **DPDP Act 2023:** consent artefact per data principal + purpose limitation +
  data-subject rights (access/correction/erasure where lawful) + breach-
  notification hooks + retention policy per data class.
- **Data residency:** all PII and Aadhaar-linked data stays in India; LLM
  inference uses an in-country path for sensitive payloads.

## Audit immutability
- Append-only, **hash-chained** audit store (each row references prior hash) →
  tamper-evident. Executed legal documents in **WORM** object storage.
- Audited: every PII read/write, every money event, every AI decision and
  override, every config change, every login/permission change.

## Secrets & keys
- Central **vault** for secrets; **KMS/HSM** for encryption keys; rotation
  policy. **No secrets in git** (CI secret-scanning gate). Per-environment keys.

## Application security
- STRIDE **threat model per bounded context**; reviewed at each increment.
- Input validation, output encoding, rate limiting, idempotency on writes.
- Dependency + container scanning; SAST/DAST in CI; signed images.
- Least-privilege service accounts; network policies between pods.

## Money-movement controls
- Idempotency keys on disbursement/CBS/eSign/eStamp/NESL.
- **Dual control** (maker/checker) on sanction and disbursement.
- **Reconciliation** jobs with break dashboards; reversal is an explicit,
  audited event, never a delete.

## Compliance reporting hooks
- Capture data needed for **PSL returns**, regulatory MIS, and asset
  classification (IRAC) from the start, even if reporting UI is later.
