# alos-eligibility

Deterministic KCC limit & eligibility engine. Pure Python, **no dependencies**,
no I/O, no LLM. This is the reproducible source of truth for KCC numbers — AI
explains these figures, it does not produce them
(see [ADR-0005](../../docs/adr/0005-deterministic-decisions-ai-explains.md)).

## Formula

```
crop_loan    = Σ  ScaleOfFinance(crop, season) × area_sown(ha)
post_harvest = post_harvest_rate × crop_loan          # default 10%
maintenance  = maintenance_rate  × crop_loan          # default 20%
insurance    = crop premia + asset premium
gross_limit  = crop_loan + post_harvest + maintenance + insurance
net_limit    = gross_limit − existing agri/KCC liabilities
```

Policy values (rates, collateral-free ceiling, subvention limit, Scale of
Finance table) are **versioned, effective-dated config** — never constants.

## Run

```bash
cd packages/eligibility-engine
python -m pytest -q                 # tests
python -m alos_eligibility.demo     # worked example  (set PYTHONPATH=src)
```

## Worked example output
2 ha wheat (₹45k/ha) + 1.5 ha paddy (₹55k/ha), ₹20k existing KCC →
crop loan ₹1,72,500 (+10% +20% +₹2,700 insurance) → gross ₹2,26,950 →
net ₹2,06,950, requires collateral (above the ₹2,00,000 ceiling).
