# Mutual Fund FAQ Assistant

> **AMC:** HDFC Mutual Fund | **Reference product:** Groww | **Corpus:** 5 Groww URLs (v1, scope-locked)  
> A facts-only RAG-based assistant that answers objective queries about HDFC mutual fund schemes.

---

## Project Structure

```
Milstone 2 - Mutual Funds app/
│
├── docs/
│   ├── problemStatement.md          # Project requirements
│   ├── phase_wise_architecture.md   # Full technical architecture
│   └── edge_cases/                  # Phase-by-phase edge case files
│       ├── README.md
│       ├── edge_cases_phase0.md
│       ├── edge_cases_phase1.md
│       ├── edge_cases_phase2.md
│       ├── edge_cases_phase3.md
│       ├── edge_cases_phase4.md
│       ├── edge_cases_phase5.md
│       ├── edge_cases_phase6.md
│       ├── edge_cases_phase7.md
│       └── edge_cases_phase8.md
│
├── src/
│   ├── phase0_corpus_registry/      # ✅ IMPLEMENTED
│   │   ├── __init__.py
│   │   ├── corpus_manifest.json     # 5 locked Groww URLs
│   │   └── validate_urls.py         # URL validation script
│   │
│   ├── phase1_data_collection/      # 🔲 Pending
│   │   └── __init__.py
│   │
│   ├── phase2_chunking/             # 🔲 Pending
│   │   └── __init__.py
│   │
│   ├── phase3_embedding/            # 🔲 Pending
│   │   └── __init__.py
│   │
│   ├── phase4_query_processing/     # 🔲 Pending
│   │   └── __init__.py
│   │
│   ├── phase5_generation/           # 🔲 Pending
│   │   └── __init__.py
│   │
│   ├── phase6_ui/                   # 🔲 Pending (React frontend)
│   │   └── README.md
│   │
│   ├── phase7_compliance/           # 🔲 Pending
│   │   └── __init__.py
│   │
│   └── phase8_deployment/           # 🔲 Pending (FastAPI app)
│       └── README.md
│
├── requirements.txt                 # All Python dependencies by phase
└── README.md                        # This file
```

---

## Phase 0 — Running URL Validation (Implemented)

Phase 0 validates that the 5 locked corpus URLs are reachable, on the correct domain, and not redirecting to external sites.

### Setup

```bash
# 1. Create and activate a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux

# 2. Install Phase 0 dependencies only
pip install requests
```

### Run Validation

```bash
# Validate all 5 URLs (read-only — does not modify the manifest)
python -m src.phase0_corpus_registry.validate_urls

# Validate AND update statuses + content hashes in corpus_manifest.json
python -m src.phase0_corpus_registry.validate_urls --update
```

### Expected Output

```
============================================================
  Phase 0 — Corpus URL Validation
  Manifest: corpus_manifest.json
============================================================

[1] HDFC Mid Cap Opportunities Fund
    URL: https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth
    ✓ Domain check: OK
    ✓ Reachability: HTTP 200 — OK
    ✓ First-time validation — ready for ingestion.

[2] HDFC Equity Fund
    ...

Results: 5/5 URLs passed validation
============================================================
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All 5 URLs passed |
| `1` | One or more URLs failed validation |
| `2` | Manifest file missing or schema invalid |

---

## Corpus — Scope Lock (v1)

The corpus is restricted to exactly **5 Groww URLs**. No additions are permitted in v1.

| # | Scheme | Category | URL |
|---|--------|----------|-----|
| 1 | HDFC Mid Cap Opportunities Fund | Mid Cap | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |
| 2 | HDFC Equity Fund | Large & Mid Cap | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| 3 | HDFC Focused Fund | Focused / Multi Cap | https://groww.in/mutual-funds/hdfc-focused-fund-direct-growth |
| 4 | HDFC ELSS Tax Saver Fund | ELSS | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| 5 | HDFC Large Cap Fund | Large Cap | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |

---

## Disclaimer

> ⚠️ **Facts-only. No investment advice.**  
> This assistant provides factual information about mutual fund schemes sourced exclusively from Groww. It does not constitute investment advice. Please consult a SEBI-registered financial advisor before making any investment decisions.
