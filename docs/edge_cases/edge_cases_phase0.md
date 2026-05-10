# Edge Cases — Phase 0: Corpus URL Registry

> Phase Goal: Define the exact and only 5 Groww source URLs for the project corpus. No additions in v1.  
> Reference: `phase_wise_architecture.md § Phase 0`

---

## Scope Constraint Reminder

The corpus is **scope-locked** to exactly these 5 URLs:

| # | Scheme | URL |
|---|--------|-----|
| 1 | HDFC Mid Cap Opportunities Fund | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |
| 2 | HDFC Equity Fund | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| 3 | HDFC Focused Fund | https://groww.in/mutual-funds/hdfc-focused-fund-direct-growth |
| 4 | HDFC ELSS Tax Saver Fund | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| 5 | HDFC Large Cap Fund | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |

---

## Edge Cases

| # | Edge Case | Scenario | Expected Behaviour | Priority |
|---|-----------|----------|--------------------|----------|
| 0.1 | URL is unreachable at ingestion time | Groww page returns 404 or 503 | Log the error; skip ingestion for that URL; alert developer; do not partially ingest | 🔴 High |
| 0.2 | URL redirects to a different page | Groww changes slug (e.g., fund renamed) | Follow redirect only if destination is still on `groww.in`; reject otherwise and flag for manual review | 🔴 High |
| 0.3 | A 6th URL is proposed during build | Developer adds hdfcfund.com or AMFI link | Hard reject — manifest has `scope_locked: true`; no new URL accepted in v1 | 🔴 High |
| 0.4 | Groww page returns a login wall or CAPTCHA | Page is temporarily gated | Skip ingestion; mark URL status as `blocked`; display last-known fetch date to users | 🟠 Medium |
| 0.5 | Duplicate URL submitted | Same URL added twice to manifest | Deduplication check on manifest load; keep only one entry; log the duplicate | 🟡 Low |
| 0.6 | URL is valid but scheme page has no fund data | New fund, page is a shell with no content | Detect empty content sections; mark as `empty_corpus`; exclude from retrieval | 🟠 Medium |
| 0.7 | URL domain changes | Groww migrates to a new domain (e.g., groww.com) | Fail validation; require manual manifest update and developer approval before ingestion | 🔴 High |
| 0.8 | Manifest file is deleted or corrupted | `corpus_manifest.json` missing at startup | Block all ingestion; regenerate manifest from last known DB state or re-initialize from scratch | 🔴 High |

---

## Test Checklist

- [ ] Ingest with all 5 URLs valid — confirm 5 entries in manifest with `status: complete`
- [ ] Simulate 404 on URL #3 — confirm the other 4 ingest correctly and #3 is marked `fetch_failed`
- [ ] Attempt to add a 6th URL — confirm rejection and error log
- [ ] Simulate redirect to external domain — confirm rejection
- [ ] Submit duplicate URL — confirm only one entry stored
- [ ] Run ingestion with CAPTCHA-gated page — confirm graceful skip

---

*Phase 0 Edge Cases | HDFC Mutual Fund FAQ Assistant v1*
