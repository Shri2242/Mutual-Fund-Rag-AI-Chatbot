# Edge Cases — Mutual Fund FAQ Assistant

> Reference: `phase_wise_architecture.md`  
> AMC: HDFC Mutual Fund | Corpus: 5 Groww URLs (v1, scope-locked)  
> Last Updated: May 2026

This document enumerates edge cases, failure modes, and their expected handling strategies for each phase of the system. Use this as a testing checklist and a developer reference.

---

## Phase 0 — Corpus URL Registry

| # | Edge Case | Scenario | Expected Behaviour |
|---|-----------|----------|--------------------|
| 0.1 | URL is unreachable at ingestion time | Groww page returns 404 or 503 | Log the error, skip ingestion for that URL, alert developer; do not partially ingest |
| 0.2 | URL redirects to a different page | Groww changes slug (e.g., fund renamed) | Follow the redirect only if the destination is still on `groww.in`; reject otherwise and flag for manual review |
| 0.3 | A 6th URL is proposed during build | Developer tempted to add hdfcfund.com or AMFI link | Hard reject — manifest has `scope_locked: true`; no new URL accepted in v1 |
| 0.4 | Groww page returns a login wall or CAPTCHA | Page is temporarily gated | Skip ingestion; mark URL status as `blocked`; display last-known fetch date to users |
| 0.5 | Duplicate URL submitted | Same URL added twice by mistake | Deduplication check on manifest load; keep only one entry |
| 0.6 | URL is valid but scheme page has no fund data yet | New fund, page is a shell | Detect empty content sections; mark as `empty_corpus`; exclude from retrieval |

---

## Phase 1 — Corpus Definition & Data Collection

| # | Edge Case | Scenario | Expected Behaviour |
|---|-----------|----------|--------------------|
| 1.1 | Groww page content is JavaScript-rendered (SPA) | Static scraper gets empty HTML | Use a headless browser (Playwright/Puppeteer) as fallback to render JS before extracting |
| 1.2 | Page structure changes (Groww UI redesign) | CSS selectors or element hierarchy changes | Scraper fails silently or extracts garbage; add structural validation after fetch; alert on anomaly |
| 1.3 | Content is behind an AJAX call | Key fund data loads asynchronously | Trigger explicit wait for content-loaded event; use Playwright `wait_for_selector` |
| 1.4 | Scraped content is in mixed language (Hindi + English) | Some Groww fields appear in Devanagari | Extract English sections only for v1; log and skip non-ASCII blocks |
| 1.5 | Groww page shows stale or incorrect data | Data inconsistency on Groww vs. AMC source | Since v1 uses Groww as sole source, ingest as-is; document this as a known limitation |
| 1.6 | Robot.txt blocks scraping | `groww.in/robots.txt` disallows crawl | Respect `robots.txt`; pause ingestion and flag for manual download if blocked |
| 1.7 | Network timeout during fetch | Slow response from Groww CDN | Retry 3 times with exponential backoff (2s, 4s, 8s); mark as `fetch_failed` after all retries |
| 1.8 | Fetched content is identical to previous fetch | Page not updated since last run | Compare content hash; skip re-ingestion; retain existing chunks |

---

## Phase 2 — Preprocessing & Chunking

| # | Edge Case | Scenario | Expected Behaviour |
|---|-----------|----------|--------------------|
| 2.1 | Chunk is entirely boilerplate | Header/footer repeats identically across all 5 pages | Remove using boilerplate fingerprinting; do not store duplicate chunks |
| 2.2 | Chunk size is 0 after cleaning | Section heading with no body text | Skip empty chunks; do not embed or store |
| 2.3 | Table data gets broken during text extraction | Groww renders a table (e.g., expense ratio grid) | Flatten table rows into key-value sentences: `"Expense Ratio (Direct): 0.52%"` |
| 2.4 | A single sentence exceeds the max chunk size | Very long legal disclaimer sentence | Force-split at punctuation boundary, not mid-word; store as two chunks with overlapping context |
| 2.5 | Metadata field `fetch_date` is missing | Ingestion pipeline skips date tagging | Block chunk from being stored; require all metadata fields to be present |
| 2.6 | Scheme name cannot be auto-detected from page | Generic Groww page title without fund name | Fall back to scheme name from the URL manifest entry (Phase 0) |
| 2.7 | Duplicate chunks across two pages | Exit load info repeated identically on two fund pages | Hash-based deduplication; keep one chunk with primary source URL; note alternate source in metadata |
| 2.8 | Chunk contains a mix of data from two different schemes | Groww comparison widget or related funds section | Detect multi-scheme content by entity extraction; split or discard to avoid cross-contamination |

---

## Phase 3 — Embedding & Vector Store

| # | Edge Case | Scenario | Expected Behaviour |
|---|-----------|----------|--------------------|
| 3.1 | Embedding API is unavailable | OpenAI API returns 500 or rate-limit error | Retry with backoff (max 3 attempts); if persistent, fall back to local `all-MiniLM-L6-v2` model |
| 3.2 | Embedding dimension mismatch | Developer switches embedding model mid-project | Detect dimension mismatch on insertion; wipe and re-index the entire collection with new model |
| 3.3 | ChromaDB collection is empty at query time | Vector store not yet initialized | Return graceful error: "Knowledge base is not ready. Please try again later." |
| 3.4 | Two chunks have near-identical embeddings | Very similar text across fund pages | Both are stored; retrieval naturally returns one; no action needed |
| 3.5 | Score threshold blocks all chunks | Query is very specific (e.g., about a fund sub-type not on Groww) | Return "not found" response: "This information is not available in our current source corpus." |
| 3.6 | ChromaDB file corruption | Disk write error or process killed mid-write | Detect checksum failure on load; trigger a full re-ingestion from the 5 source URLs |
| 3.7 | Metadata filter returns zero results | User asks about a specific scheme but filter is too narrow | Broaden search by removing scheme filter and re-running similarity search |
| 3.8 | Top-K returns chunks from wrong scheme | Scheme entity not detected; mixed retrieval | Post-filter retrieved chunks by scheme name if entity was successfully extracted |

---

## Phase 4 — Query Processing & Intent Classification

| # | Edge Case | Scenario | Expected Behaviour |
|---|-----------|----------|--------------------|
| 4.1 | Query is in Hindi or a regional language | User types "इस फंड में कितना SIP करना चाहिए?" | Detect non-English input; politely ask user to re-enter in English for v1 |
| 4.2 | Query is extremely short | User sends "exit load?" or just "?" | Treat as ambiguous; ask: "Could you please clarify which HDFC fund you're referring to?" |
| 4.3 | Query contains multiple intents | "What is the exit load and should I invest?" | Split query; answer the factual part, refuse the advisory part in the same response |
| 4.4 | Advisory keyword is used in a factual context | "What is the return calculation method used?" | Do not trigger refusal — "return calculation" as a factual query about methodology is allowed; context matters |
| 4.5 | Regex pre-filter produces false positive | "Should the exit load be calculated before or after..." | Regex fires on "should"; escalate to LLM classifier for final ruling before refusing |
| 4.6 | Scheme name in query is misspelled | "HDFC Midcap fund" vs "HDFC Mid Cap Opportunities Fund" | Use fuzzy matching against the 5 known scheme names; map to closest match |
| 4.7 | Query mentions a scheme not in the corpus | "Tell me about HDFC Small Cap Fund" | Respond: "This assistant currently covers only 5 HDFC schemes. HDFC Small Cap Fund is not in scope." |
| 4.8 | Query is completely off-topic | "What is the weather in Mumbai?" | Classify as OUT_OF_SCOPE; respond: "I can only answer questions about HDFC mutual fund schemes." |
| 4.9 | User sends an empty query | Blank input or only spaces | Block at UI layer before submission; display inline validation: "Please enter a question." |
| 4.10 | Very long query (>500 words) | User pastes a long paragraph | Truncate to first 300 tokens for classification; use full text only if needed for retrieval context |

---

## Phase 5 — Response Generation

| # | Edge Case | Scenario | Expected Behaviour |
|---|-----------|----------|--------------------|
| 5.1 | Retrieved chunks are contradictory | Two chunks give different exit load values | Flag the contradiction in the response: "Sources show differing values. Please verify directly on Groww." |
| 5.2 | LLM response exceeds 3 sentences | Model ignores the sentence limit | Output validator counts sentences; truncate at sentence 3 and append source/footer |
| 5.3 | LLM generates a source URL not in the corpus | Hallucinated URL (e.g., non-existent AMC link) | Domain whitelist check in output validator; reject response and re-generate if URL not in `groww.in` |
| 5.4 | LLM response contains advisory language | "You should consider this fund..." | Output validator detects advisory keywords; re-generate with a stricter prompt |
| 5.5 | LLM API returns empty response | Network timeout or overloaded model | Retry once; if still empty, return: "Unable to generate a response right now. Please try again." |
| 5.6 | `fetch_date` is missing from chunk metadata | Footer cannot be populated | Use corpus manifest's `last_full_refresh` date as fallback |
| 5.7 | User asks about NAV (real-time data) | "What is today's NAV?" | Trigger the performance-query special case: redirect to official NAV page, do not fabricate a number |
| 5.8 | User asks for comparison across schemes | "Compare expense ratio of all 5 HDFC funds" | This is factual but multi-scheme; retrieve per scheme and present a structured list, not a recommendation |
| 5.9 | Response is factually correct but misleading by omission | Only partial exit load info retrieved | Always retrieve top-4 chunks to ensure full clause coverage; prompt instructs to note if info may be partial |

---

## Phase 6 — User Interface

| # | Edge Case | Scenario | Expected Behaviour |
|---|-----------|----------|--------------------|
| 6.1 | User sends query by pressing Enter rapidly multiple times | Multiple identical requests in flight | Debounce input; disable Send button while a response is loading |
| 6.2 | Response takes > 10 seconds | Slow LLM API or network lag | Show a loading spinner; after 15s, display: "This is taking longer than expected. Please wait or try again." |
| 6.3 | Chat history grows very long | 50+ exchanges in one session | Paginate or virtualize the chat window; do not send full history to LLM |
| 6.4 | User copies and pastes PII into the input | PAN number pasted into chat box | Client-side PII pattern detection; clear the input field and show warning before submission |
| 6.5 | User is on a mobile device with small screen | Long source URLs break layout | Truncate displayed URL with ellipsis; full URL accessible via tap/click |
| 6.6 | Example question buttons are clicked multiple times | Fast repeated clicks | Treat as single submission; button disabled on click until response is received |
| 6.7 | Browser back button navigates away during session | Chat history lost | Warn user on navigating away if conversation is in progress (browser `beforeunload` event) |
| 6.8 | Disclaimer is not visible on mobile | Disclaimer at bottom scrolled out of view | Disclaimer must also appear as a persistent banner at the top of the page, always visible |

---

## Phase 7 — Compliance & Safety Layer

| # | Edge Case | Scenario | Expected Behaviour |
|---|-----------|----------|--------------------|
| 7.1 | PII regex produces false positive | "My name is PAN Lal" partially matches PAN pattern | Increase regex precision (add word boundaries); log false positive rate for tuning |
| 7.2 | PII is embedded mid-sentence | "For PAN ABCDE1234F, what is the exit load?" | Regex still detects pattern regardless of position; block and strip the query |
| 7.3 | Output validator marks a valid response as advisory | Response says "This fund is a stable option" | Log as false positive; tune blocked keyword list to not catch descriptive adjectives without context |
| 7.4 | Domain whitelist blocks a valid Groww URL | groww.in added mid-project but not whitelisted | Update `ALLOWED_DOMAINS` to include `groww.in` since that is the v1 source |
| 7.5 | Both PII detected AND advisory intent | "Should I use my PAN to invest here?" | PII filter fires first (pre-advisory check); block at PII stage |
| 7.6 | Compliance layer itself throws an exception | Regex engine error or sanitizer crash | Fail safe: block the query and return a generic error rather than letting unsanitized input reach the LLM |
| 7.7 | Output validator runs but LLM response is in JSON or non-standard format | LLM wraps answer in markdown or JSON | Normalize LLM output to plain text before validation |

---

## Phase 8 — Deployment & Observability

| # | Edge Case | Scenario | Expected Behaviour |
|---|-----------|----------|--------------------|
| 8.1 | Backend API is down | FastAPI server crashes | Frontend displays: "Service temporarily unavailable. Please try again shortly." |
| 8.2 | ChromaDB collection is missing at startup | First deployment without running ingestion | Startup health-check detects empty DB; block all queries and display: "Knowledge base initializing." |
| 8.3 | LLM API key is invalid or expired | Anthropic API returns 401 | Log alert immediately; do not expose key error to user; return: "Response generation is temporarily unavailable." |
| 8.4 | Log volume is too high | 10,000+ queries per day filling disk | Implement log rotation (daily); cap log file size at 100 MB |
| 8.5 | `corpus_manifest.json` is missing | Deleted or not created during deployment | Re-generate manifest from ChromaDB metadata; use earliest `fetch_date` in DB as fallback date |
| 8.6 | Deployment environment has no internet access | Air-gapped or restricted network | Switch to local embedding model (`all-MiniLM-L6-v2`) and locally hosted LLM; pre-ingest corpus offline |
| 8.7 | Two instances run simultaneous re-ingestion | Race condition on ChromaDB write | Use a file-lock or database mutex during ingestion; second process waits and skips if lock is held |
| 8.8 | Frontend and backend version mismatch | Old frontend cached in browser after backend update | Version the API (`/v1/query`); add cache-busting headers on frontend deployment |
| 8.9 | Query hash collision in logs | Two different queries produce same SHA-256 prefix (extremely rare) | Log full timestamp + first 10 chars of query as secondary key; no user data stored |

---

## Cross-Phase Edge Cases

| # | Edge Case | Phases Involved | Expected Behaviour |
|---|-----------|----------------|--------------------|
| X.1 | Corpus not ingested but user submits query | Phase 3 + 5 | Phase 3 returns empty results → Phase 5 returns "Knowledge base not ready" error |
| X.2 | User submits a query that is factual but about a scheme not in the 5 URLs | Phase 4 + 5 | Phase 4 entity extractor detects unknown scheme → out-of-scope response without hitting retrieval |
| X.3 | PII in query passes UI filter but is caught server-side | Phase 6 + 7 | Server-side sanitizer is the final gate; client-side is best-effort only |
| X.4 | Groww updates the page content but fetch schedule hasn't triggered | Phase 0 + 1 + 3 | Old chunks remain in DB; `last_updated` footer shows stale date; user is implicitly warned by date |
| X.5 | LLM and output validator disagree on advisory content | Phase 5 + 7 | Output validator has final veto; re-generation is triggered regardless of LLM confidence |

---

*Edge Cases document prepared for: Mutual Fund FAQ Assistant (Groww context)*  
*Coverage: Phase 0 through Phase 8 + Cross-Phase | Total cases documented: 72*
