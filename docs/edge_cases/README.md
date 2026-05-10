# Edge Cases — Index

> Project: Mutual Fund FAQ Assistant (HDFC, Groww context)  
> Corpus: 5 Groww URLs (v1, scope-locked)  
> Last Updated: May 2026

This folder contains one dedicated edge case file per phase of the system architecture.  
Each file includes: a phase goal, edge case table (with priority), handling strategy, and a test checklist.

---

## Files in This Folder

| Phase | File | Cases | Focus Area |
|-------|------|-------|------------|
| Phase 0 — Corpus URL Registry | [edge_cases_phase0.md](./edge_cases_phase0.md) | 8 | URL availability, scope lock, redirects |
| Phase 1 — Data Collection | [edge_cases_phase1.md](./edge_cases_phase1.md) | 12 | JS rendering, robots.txt, timeouts, staleness |
| Phase 2 — Preprocessing & Chunking | [edge_cases_phase2.md](./edge_cases_phase2.md) | 12 | Empty chunks, broken tables, cross-scheme contamination |
| Phase 3 — Embedding & Vector Store | [edge_cases_phase3.md](./edge_cases_phase3.md) | 12 | API outage, dimension mismatch, score threshold |
| Phase 4 — Query Processing & Intent | [edge_cases_phase4.md](./edge_cases_phase4.md) | 14 | Multilingual, false advisory, misspelled schemes |
| Phase 5 — Response Generation | [edge_cases_phase5.md](./edge_cases_phase5.md) | 14 | Hallucination, contradictory chunks, advisory leakage |
| Phase 6 — User Interface | [edge_cases_phase6.md](./edge_cases_phase6.md) | 14 | PII paste, mobile layout, rapid clicks, offline state |
| Phase 7 — Compliance & Safety | [edge_cases_phase7.md](./edge_cases_phase7.md) | 12 | PII false positives, domain whitelist, output validator |
| Phase 8 — Deployment & Observability | [edge_cases_phase8.md](./edge_cases_phase8.md) | 14 | Cold starts, CORS, missing env vars, race conditions |

**Total documented edge cases: 112**

---

## Priority Legend

| Symbol | Level | Meaning |
|--------|-------|---------|
| 🔴 | High | Must be handled before go-live; blocks core functionality |
| 🟠 | Medium | Should be handled before go-live; degrades user experience |
| 🟡 | Low | Nice-to-have; address in v2 or as time permits |

---

## How to Use These Files

1. **During development** — use as a reference to build defensive logic into each phase
2. **During QA/testing** — use the Test Checklist in each file as your test plan
3. **During code review** — verify that high-priority cases have corresponding handling in code
4. **During v2 planning** — review 🟡 Low priority items as candidates for the next iteration

---

*Reference: `../phase_wise_architecture.md`*
