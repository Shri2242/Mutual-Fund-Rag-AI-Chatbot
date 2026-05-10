# Edge Cases — Phase 1: Data Collection

> Phase Goal: Fetch and parse content from the 5 locked Groww URLs into raw text ready for chunking.  
> Reference: `phase_wise_architecture.md § Phase 1`

---

## Edge Cases

| # | Edge Case | Scenario | Expected Behaviour | Priority |
|---|-----------|----------|--------------------|----------|
| 1.1 | Groww page content is JavaScript-rendered (SPA) | Static scraper gets empty HTML body | Use headless browser (Playwright/Puppeteer) as fallback to render JS before extracting | 🔴 High |
| 1.2 | Page structure changes (Groww UI redesign) | CSS selectors or element hierarchy changes | Scraper fails silently or extracts garbage; add structural validation after fetch; alert on anomaly | 🔴 High |
| 1.3 | Content is behind an AJAX call | Key fund data loads asynchronously after initial page load | Use `wait_for_selector` or `network_idle` in Playwright before extracting content | 🔴 High |
| 1.4 | Scraped content is in mixed language (Hindi + English) | Some Groww fields appear in Devanagari | Extract English sections only for v1; log and skip non-ASCII blocks | 🟠 Medium |
| 1.5 | Groww page shows stale or incorrect data | Data inconsistency between Groww and AMC official source | Since v1 uses Groww as sole source, ingest as-is; document this as a known limitation in README | 🟠 Medium |
| 1.6 | `robots.txt` blocks scraping | `groww.in/robots.txt` disallows crawl of fund pages | Respect `robots.txt`; pause ingestion and flag for manual download if path is disallowed | 🔴 High |
| 1.7 | Network timeout during fetch | Slow response from Groww CDN (>30s) | Retry 3 times with exponential backoff (2s, 4s, 8s); mark as `fetch_failed` after all retries | 🟠 Medium |
| 1.8 | Fetched content is identical to previous fetch | Page not updated since last ingestion run | Compare content hash with stored hash; skip re-ingestion; retain existing chunks | 🟡 Low |
| 1.9 | Partial page load | Only above-the-fold content fetched; fund details are below | Scroll or use full page render; validate presence of key data fields (e.g., "Expense Ratio") after fetch | 🟠 Medium |
| 1.10 | Groww serves different content to bots | User-agent detection returns a simplified page | Set realistic User-Agent header; compare page size to expected range; flag anomaly if content is <5KB | 🟠 Medium |
| 1.11 | Groww page returns HTTP 200 but empty content | Anti-bot protection returns an empty shell | Validate minimum content length after fetch; mark as `fetch_failed` if below threshold | 🔴 High |
| 1.12 | Fetch succeeds but a required fund data field is absent | e.g., "Exit Load" section missing from Groww UI | Log missing field; ingest available content; flag scheme as `partial_data` in manifest | 🟠 Medium |

---

## Data Collection Pipeline Reference

```
Step 1: URL Registry       → Load 5 URLs from corpus_manifest.json
Step 2: Document Fetching  → Playwright (headless) → full-page render
Step 3: Content Validation → Check minimum length, required fields
Step 4: Metadata Tagging   → { scheme_name, url, fetch_date }
Step 5: Hash Check         → Skip if content unchanged since last run
```

---

## Test Checklist

- [ ] Fetch all 5 pages with Playwright — confirm non-empty HTML for each
- [ ] Disable JS in scraper — confirm fallback to Playwright headless kicks in
- [ ] Simulate 30s timeout — confirm retry with backoff and `fetch_failed` marking
- [ ] Fetch same page twice — confirm second fetch is skipped via hash check
- [ ] Mock a page with no "Expense Ratio" field — confirm `partial_data` flag
- [ ] Test with robots.txt blocking — confirm no fetch attempt is made

---

*Phase 1 Edge Cases | HDFC Mutual Fund FAQ Assistant v1*
