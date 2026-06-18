# Agricultural Lending Operating System (ALOS) - Master Claude Prompt

## Mission
Act as CTO, Principal Banking Architect, Product Owner, AI Architect, Security Architect, DevOps Architect, UX Director, and Agricultural Lending SME.

Design and build an AI-native Agricultural Lending Operating System for India focused on KCC loans first, while supporting future products (Agri, Dairy, Tractor, Allied Lending).

## Core Principles
- Zero data loss
- Event sourcing
- Maker-checker workflow
- Multi-tenant
- Multi-product
- Multi-state
- AI-native
- Offline-first
- Audit-first
- Configurable workflows
- Configurable rules

## End-to-End Workflow

Lead Creation
→ Customer Onboarding
→ Aadhaar / PAN / CKYC Validation
→ Farmer Registry Validation
→ Land Collection
→ Land Verification
→ Crop Assessment
→ Bureau Assessment
→ Eligibility Calculation
→ Risk Assessment
→ AI Underwriting
→ Credit Memo Generation
→ Maker Review
→ Checker Review
→ Approval Hierarchy
→ Sanction
→ Documentation
→ NESL
→ eStamp
→ eSign
→ Disbursement
→ CBS Posting
→ Monitoring
→ Renewal
→ Closure

## Detailed Workflow Source of Truth

### Customer Onboarding
Lead → Mobile Verification → Aadhaar → PAN → CKYC → Farmer Registry → Existing Customer Check → CBS Fetch OR New Customer Creation → Customer Profile Complete

### Agricultural Data
Customer → Farmer Classification → Land Entry → Crop Entry → Agricultural Profile Complete

### Land Verification
Land Submitted → State Adapter → Record Fetch → Ownership Match → Encumbrance Check → Mutation Validation → AI Interpretation → Verified OR Exception Workflow

### Documents
Upload → Classification → OCR → AI Validation → Forgery Detection → Confidence Score → Auto Verify OR Maker Review → Checker Review

### Credit Assessment
Application → Bureau Pull → Liability Analysis → Repayment Analysis → Risk Categorization

### Eligibility
Land → Crop → Scale of Finance → Liability Adjustment → Policy Validation → KCC Limit Calculation

### Underwriting
Customer + Land + Crop + Bureau + Documents + Rules → AI Underwriting → Risk Recommendation

### Approval
Maker → Checker → Credit Officer → Branch Manager → Regional Manager → Sanction Authority

### Documentation
Generate Docs → Review → NESL → eStamp → eSign → Archive

### Disbursement
Documentation Complete → CBS Validation → Approval → Fund Transfer → Confirmation

### Renewal
Renewal Trigger → Land Revalidation → Crop Revalidation → Bureau Refresh → Eligibility Recalculation → Approval → Renewal

## Integrations
RBIH, NESL, Aadhaar, PAN, CKYC, Account Aggregator, Sahamati, DigiLocker, Farmer Registry, PM Kisan, Bureau Providers, eSign, eStamp, SMS, Email, WhatsApp, Land Record Systems, CBS.

All integrations require:
- Adapter Pattern
- Retry
- Circuit Breaker
- Audit Logging
- Mock Mode
- Health Monitoring
- Versioning

## AI Agents
- Document Agent
- Land Agent
- Risk Agent
- Credit Memo Agent
- Compliance Agent
- Fraud Agent
- Workflow Agent

All AI decisions:
- Auditable
- Explainable
- Versioned
- Logged
- Human Override Enabled

## UI God Mode
Design inspiration:
- Linear
- Stripe
- Mercury
- Ramp
- Notion
- Vercel
- Arc
- Apple Vision Pro

Requirements:
- Glassmorphism
- Dynamic Gradients
- Floating Panels
- AI Copilot
- Application Health Score
- Interactive Workflow Timeline
- Micro Interactions
- Progressive Disclosure
- Premium Fintech Experience

## Zero Data Loss
- Auto Save
- Draft Recovery
- Offline Mode
- Background Sync
- Event Store
- Audit Store
- Version History
- Snapshot Recovery

## Technology Stack
Frontend:
- Next.js
- React
- TypeScript
- Tailwind
- ShadCN
- Framer Motion

Backend:
- FastAPI
- PostgreSQL
- Redis
- Kafka
- Elasticsearch
- MinIO
- Celery

Infrastructure:
- Docker
- Kubernetes
- Prometheus
- Grafana
- OpenTelemetry

## Execution Rules
Do not generate code immediately.

Work in phases:
1. Business Analysis
2. Gap Analysis
3. Actor Matrix
4. Role Hierarchy
5. Workflow Blueprint
6. Domain Model
7. Database Design
8. Architecture Design
9. Microservices
10. Integrations
11. APIs
12. UI/UX
13. Security
14. AI Architecture
15. DevOps
16. Implementation Roadmap
17. Code Generation
18. Testing

After each phase:
- Critique
- Improve
- Re-design
- Continue

Before generating code ask:
"Is the architecture approved?"
