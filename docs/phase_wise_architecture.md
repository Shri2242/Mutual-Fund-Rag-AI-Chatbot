# Mutual Fund FAQ Assistant — Phase-Wise Architecture

> Reference Product: Groww | AMC: HDFC Mutual Fund  
> Document Type: Technical Architecture & Implementation Blueprint  
> Last Updated: May 2026

---

## Selected AMC & Schemes

**AMC:** HDFC Mutual Fund  
**Rationale:** One of India's largest AMCs with strong AMFI-compliant disclosures, broad scheme category coverage, and publicly accessible documents on Groww and the HDFC AMC website.

| # | Scheme Name | Category | Use Case Coverage |
|---|-------------|----------|-------------------|
| 1 | HDFC Mid Cap Opportunities Fund | Mid Cap | Expense ratio, benchmark, riskometer |
| 2 | HDFC Equity Fund | Large & Mid Cap | Exit load, portfolio composition |
| 3 | HDFC Focused Fund | Focused / Multi Cap | SIP minimum, fund manager info |
| 4 | HDFC ELSS Tax Saver Fund | ELSS | Lock-in period, tax benefits |
| 5 | HDFC Large Cap Fund | Large Cap | Benchmark index, NAV info |

---

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE LAYER                         │
│          Welcome Banner · 3 Example Qs · Disclaimer Footer          │
└───────────────────────────────┬─────────────────────────────────────┘
                                │  User Query (natural language)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       QUERY PROCESSING LAYER                        │
│   Intent Classifier → Factual? → Route   Advisory? → Refuse        │
└──────────────┬────────────────────────────────────┬─────────────────┘
               │ Factual                            │ Advisory
               ▼                                   ▼
┌──────────────────────────┐           ┌───────────────────────────┐
│    RAG RETRIEVAL LAYER   │           │     REFUSAL HANDLER       │
│  Query Embedding →       │           │  Polite decline +         │
│  Vector Search →         │           │  Educational link         │
│  Top-K chunk retrieval   │           │  (AMFI/SEBI resource)     │
└──────────────┬───────────┘           └───────────────────────────┘
               │ Retrieved chunks + source metadata
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      GENERATION LAYER (LLM)                         │
│   Prompt: [System Rules] + [Retrieved Context] + [User Query]       │
│   Output: ≤ 3 sentences · 1 citation · last-updated footer          │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
                        Response to User
```

---

## Phase 0 — Corpus URL Registry (Project-Specific)

**Goal:** Define the exact and only source URLs for this project's corpus. **No additional URLs will be added beyond this list.**

> [!IMPORTANT]
> **Scope Lock:** The corpus for this project is restricted to exactly the 5 Groww URLs listed below. No external AMC websites, AMFI pages, SEBI documents, or third-party sources will be added in v1. The RAG system will only answer queries that can be grounded in content retrieved from these 5 pages.

### 0.1 Finalized Corpus URLs — v1 (Fixed, No Additions)

| # | Scheme Name | Category | Source URL |
|---|-------------|----------|------------|
| 1 | HDFC Mid Cap Opportunities Fund | Mid Cap | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |
| 2 | HDFC Equity Fund | Large & Mid Cap | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| 3 | HDFC Focused Fund | Focused / Multi Cap | https://groww.in/mutual-funds/hdfc-focused-fund-direct-growth |
| 4 | HDFC ELSS Tax Saver Fund | ELSS | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| 5 | HDFC Large Cap Fund | Large Cap | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |

**Total URLs in corpus: 5 (fixed)**

### 0.2 URL Manifest (Ingestion Pipeline Input)

```json
{
  "corpus_version": "v1",
  "scope_locked": true,
  "total_urls": 5,
  "corpus_urls": [
    {
      "id": 1,
      "scheme": "HDFC Mid Cap Opportunities Fund",
      "category": "Mid Cap",
      "url": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
      "status": "pending_ingestion"
    },
    {
      "id": 2,
      "scheme": "HDFC Equity Fund",
      "category": "Large & Mid Cap",
      "url": "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
      "status": "pending_ingestion"
    },
    {
      "id": 3,
      "scheme": "HDFC Focused Fund",
      "category": "Focused / Multi Cap",
      "url": "https://groww.in/mutual-funds/hdfc-focused-fund-direct-growth",
      "status": "pending_ingestion"
    },
    {
      "id": 4,
      "scheme": "HDFC ELSS Tax Saver Fund",
      "category": "ELSS",
      "url": "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
      "status": "pending_ingestion"
    },
    {
      "id": 5,
      "scheme": "HDFC Large Cap Fund",
      "category": "Large Cap",
      "url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
      "status": "pending_ingestion"
    }
  ]
}

---

## Phase 1 — Corpus Definition & Data Collection

**Goal:** Fetch and extract the raw text content from the 5 locked Groww URLs, ready for preprocessing in Phase 2.

> [!IMPORTANT]
> The corpus is locked to exactly **5 Groww URLs** as defined in Phase 0. No additional sources will be ingested in v1. Each subphase below is independently implementable and testable.

---

### Subphase 1.1 — robots.txt Compliance Check

**Goal:** Before making any HTTP requests, verify that `groww.in/robots.txt` permits scraping of the 5 fund page paths.

**Implementation Steps:**
- Fetch `https://groww.in/robots.txt`
- Parse `Disallow` rules for the `/mutual-funds/` path prefix
- If the path is disallowed: halt ingestion, log the block, and raise a `RobotsBlocked` exception
- If permitted: proceed to Subphase 1.2

**Output:** `robots_check_result: allowed | blocked`

**Acceptance Criteria:**
- [ ] Script fetches and parses `robots.txt` without error
- [ ] Returns `allowed` for all 5 fund page paths when permitted
- [ ] Halts with clear log message if path is disallowed

---

### Subphase 1.2 — Static HTML Fetch (Requests Attempt)

**Goal:** Attempt a lightweight static fetch of each URL using `requests`. This is the fast path — used only if the page is not JS-rendered.

**Implementation Steps:**
- Set a realistic `User-Agent` header to avoid bot detection
- Send HTTP GET to each of the 5 URLs with a 15-second timeout
- Validate the response:
  - HTTP status must be 200
  - Content length must be > 2,000 characters (anti-bot shell check)
  - Final URL domain must still be `groww.in` (redirect safety)
- If validation passes → save raw HTML and proceed to Subphase 1.4
- If content is empty or too short → escalate to Subphase 1.3 (headless fallback)

**Output per URL:** `{ url, status_code, content_length, raw_html, fetch_method: "static" }`

**Acceptance Criteria:**
- [ ] All 5 URLs return HTTP 200
- [ ] Raw HTML saved per scheme with `fetch_method: static` in metadata
- [ ] Pages with < 2,000 chars are flagged and escalated to Subphase 1.3

---

### Subphase 1.3 — Headless Browser Fetch (Playwright Fallback)

**Goal:** For pages where static fetch yields insufficient content (JS-rendered SPAs), use Playwright to fully render the page before extracting HTML.

**Implementation Steps:**
- Launch a headless Chromium browser via Playwright
- Navigate to the URL and wait for `networkidle` state (all XHR/fetch calls complete)
- Wait for key fund data selectors to be visible (e.g., expense ratio, exit load fields)
- Extract the full rendered HTML
- Close the browser after extraction

**Trigger condition:** Only activated when Subphase 1.2 returns content < 2,000 characters or missing key fields.

**Output per URL:** `{ url, raw_html, fetch_method: "headless", render_time_ms }`

**Acceptance Criteria:**
- [ ] Playwright fetches a fully rendered page for each URL it is called on
- [ ] Key fund data fields (expense ratio, exit load) are present in extracted HTML
- [ ] Fallback triggers automatically without manual intervention

---

### Subphase 1.4 — Content Extraction & JSON Mapping

**Goal:** Parse the raw HTML (from Subphase 1.2 or 1.3) and extract the specific fund data fields that will form the corpus.

**Target Fields to Extract per Scheme:**

| Field | Expected Location in JSON |
|-------|--------------------------------|
| Scheme Name | `scheme_name` |
| Category | `category` / `sub_category` |
| Expense Ratio (Direct) | `expense_ratio` |
| Exit Load | `exit_load` |
| Minimum SIP Amount | `min_sip_investment` |
| Riskometer Level | `return_stats[0].risk` |
| Benchmark Index | `benchmark` |
| Lock-in Period | `lock_in` |
| Fund Manager Name | `fund_manager` |
| NAV (latest available) | `nav` |
| Top 5 Holdings | `holdings` array |

**Implementation Steps:**
- Use `BeautifulSoup` to locate the `<script id="__NEXT_DATA__" type="application/json">` tag.
- Parse the tag's string content as JSON.
- Extract the `mfServerSideData` object from `props.pageProps`.
- Map the required fields safely using `dict.get()`.
- For fields not found: mark as `null` and log as `partial_data`
- Validate that at minimum 6/10 fields are extracted per page (quality gate)

**Output per URL:**
```json
{
  "scheme": "HDFC Mid Cap Opportunities Fund",
  "source_url": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
  "fetch_date": "2026-05-03",
  "fetch_method": "static | headless",
  "fields": {
    "expense_ratio": "0.52%",
    "exit_load": "1% if redeemed within 1 year",
    "min_sip": "₹100",
    "riskometer": "Very High",
    "benchmark": "Nifty Midcap 150 TRI",
    "lock_in_period": null,
    "fund_manager": "Chirag Setalvad",
    "nav": "₹145.67"
  },
  "partial_data": false
}
```

**Acceptance Criteria:**
- [ ] Extractor runs on all 5 pages without crashing
- [ ] At least 6/10 fields extracted per scheme
- [ ] Pages with < 6 fields extracted are flagged as `partial_data: true`
- [ ] Output JSON saved per scheme in `src/phase1_data_collection/output/`

---

### Subphase 1.5 — Content Hashing & Manifest Update

**Goal:** After successful extraction, compute a content hash per page and update `corpus_manifest.json` with fetch results. This enables change detection on future runs.

**Implementation Steps:**
- Compute SHA-256 hash of the extracted raw HTML for each URL
- Compare against `content_hash` stored in `corpus_manifest.json`
  - If hash is identical to previous → mark as `status: unchanged`, skip re-ingestion
  - If hash differs → mark as `status: changed`, trigger Phase 2 re-processing
  - If no previous hash → mark as `status: ingested_first_time`
- Update the manifest with:
  - `content_hash` (new hash)
  - `last_fetched` (current UTC timestamp)
  - `status` (unchanged / changed / ingested_first_time / partial_data)
- Set `last_ingested` at manifest root level to current timestamp

**Output:** Updated `corpus_manifest.json` + extracted JSON files in `output/`

**Acceptance Criteria:**
- [ ] Manifest updated correctly after every run
- [ ] Unchanged pages are skipped and logged as `unchanged`
- [ ] Changed pages are re-queued for Phase 2 processing
- [ ] `last_fetched` timestamp written for all 5 entries

---

### Sub-phase 1.7 — Refresh & Health Orchestrator

**Goal:** Orchestrate 1.1 → 1.6 as a re-runnable pipeline with advanced drift detection and health reporting. This sub-phase integrates all the others.

**Implementation:** `src/phase1_data_collection/pipeline.py -> Pipeline.refresh(force=False)`

**Scheduler Strategy (GitHub Actions):**
- The master pipeline orchestrator (`pipeline.py`) is designed to be executed autonomously via a scheduled GitHub Actions cron job (e.g., daily at midnight UTC).
- This ensures the vector index and data corpus always contain the latest factual data without manual intervention.

**Behavior:**
- Runs the extraction pipeline (static fetch → headless fallback → JSON parser).
- For each URL, computes a `stable_content_hash`. This hash explicitly excludes highly volatile fields (like live NAV) and only hashes the structural HTML anchors or structural JSON keys.
- Only re-chunks and re-embeds (Phase 1.6) pages whose stable hash actually changed.
- **Drift Detection:** If drift is detected across ≥ 2 URLs in the same refresh window, the system automatically *freezes* the index (does not overwrite the production Chroma index) and raises an aggregated alert.
- **Soft-404 Detection:** If a URL returns HTTP 200 but the Next.js JSON payload or must-have HTML anchors are missing, fail that specific URL but keep the rest.
- The "Last updated from sources" metadata date is bumped *only* when the stable content actually changed.

**Output:** `data/index/refresh_log.jsonl`
- One line per pipeline run recording: per-stage timings, content-hash diffs, anchor health, and final outcome (`ok`, `partial`, or `frozen`).

---

### Phase 1 — Data Flow Summary

```
Subphase 1.1: robots.txt check
       │ allowed
       ▼
Subphase 1.2: Static fetch (requests)
       │ content OK?
       ├── YES → Subphase 1.4
       └── NO  → Subphase 1.3: Headless fetch (Playwright)
                       │
                       ▼
Subphase 1.4: HTML parsing & field extraction
       │
       ▼
Subphase 1.5: Content hashing + manifest update
       │
       ▼
   output/ ← 5 × extracted JSON files, ready for Phase 2
```

### Phase 1 — Data Quality Gates

- ✅ Source must be one of the 5 locked `groww.in` URLs from Phase 0
- ✅ Only content on the page itself is scraped — no following of external links
- ✅ Minimum 6/10 fields must be extracted per scheme (otherwise `partial_data: true`)
- ❌ Do not add URLs not listed in the Phase 0 manifest
- ❌ Do not follow linked AMC documents, PDFs, or related fund pages

---



## Phase 2 — Preprocessing & Vectorization Strategy

**Goal:** Convert the highly structured JSON data extracted in Phase 1 into semantic, retrievable text chunks for the vector database.

### 2.1 Text Conversion (JSON to Natural Language)

Since our data is neatly structured in JSON rather than messy PDFs or large raw HTML text blobs, we **do not need traditional token-based text splitting**. Instead, we will convert the key-value pairs into dense natural language paragraphs.

```python
# Pseudocode — JSON to Text conversion
def create_fund_document(fund_json):
    text = f"Fund Name: {fund_json['scheme']}.\n"
    text += f"The current NAV is {fund_json['nav']}. "
    text += f"The Assets Under Management (AUM) is {fund_json['aum']}. "
    text += f"The Expense Ratio is {fund_json['expense_ratio']}%. "
    text += f"The Exit Load is: {fund_json['exit_load']}. "
    text += f"The minimum SIP amount is ₹{fund_json['min_sip']}. "
    text += f"The risk level is rated as {fund_json['riskometer']}. "
    text += f"The benchmark index is {fund_json['benchmark']}. "
    text += f"The fund manager is {fund_json['fund_manager']}. "
    
    holdings_text = ", ".join([f"{h['company_name']} ({h['allocation_percent']}%)" for h in fund_json['top_5_holdings']])
    text += f"Top holdings include: {holdings_text}."
    
    return text
```

### 2.2 Chunking Strategy (Entity-Level)

| Document Type | Chunking Method | Rationale |
|---------------|-----------|-----------|
| Fund Details (Structured) | 1 Chunk per Fund | The entire synthesized natural language paragraph easily fits within a single embedding window (~150-200 tokens). This ensures all context for a specific fund is retrieved together. |
| General FAQs | 1 Chunk per Q&A Pair | Semantic isolation (prevents cross-talk between distinct questions). |

**Chunking Logic:**
- **No arbitrary token splitting:** We will not use fixed character/token chunking with overlaps. 
- Each chunk stores: `{ chunk_id, text, metadata: { source_url, scheme, doc_type, fetch_date } }`

### 2.3 Chunk Metadata Schema

```json
{
  "chunk_id": "mirae_large_cap_kim_p3_c2",
  "text": "The exit load for Mirae Asset Large Cap Fund is 1% if redeemed within 1 year from the date of allotment.",
  "metadata": {
    "scheme": "Mirae Asset Large Cap Fund",
    "source_type": "KIM",
    "source_url": "https://miraeassetmf.co.in/...",
    "fetch_date": "2026-05-01",
    "page_number": 3
  }
}
```

---

## Phase 3 — Reasoning & Guardrails (Orchestrator)

**Purpose:** Turn a query + retrieved chunks into a compliant, ≤ 3-sentence answer — or a refusal — with URL policy enforced before anything is returned.

**Generation stack:** 
- Default behavior: Extractive-only (`use_groq=False`).
- When an LLM is used for answer wording (instead of extractive synthesis), it is Groq via the OpenAI-compatible Chat Completions API.
- `use_groq=None` (auto) — Groq runs when `GROQ_API_KEY` is set; use `use_groq=False` or unset the key to stay extractive-only. 
- Embeddings for retrieval stay as in Phase 1.5 (sentence-transformers).

### 3.1 URL Policy (Non-negotiable)

| Situation | URLs in the assistant reply |
|-----------|-----------------------------|
| **PII detected** in user message (PAN, Aadhaar, email, phone, OTP, etc.) | **None** — use the locked `pii_block` template only. |
| **Insufficient evidence** / low confidence / empty retrieval ("don't know" path) | **None** — use `dont_know_without_link` only (ask user to name a scheme; no Groww link). |
| **Non-factual intent** (advisory / comparison / prediction refusal) | **At most one** — the matching scheme's Groww URL from sources.yaml, or the first scheme's URL if none resolved. |
| **Successful factual answer** from retrieved chunks | **Exactly one** — the citation `source_url` from the top chunk (must be on the whitelist). |

### 3.2 Decision Flow
```text
               ┌──────────────────────────┐
                │   Incoming user query    │
                └────────────┬─────────────┘
                             ▼
                ┌──────────────────────────┐
        ┌──No──┤   PII detected?          │
        │      └────────────┬─────────────┘
        │                   │ Yes
        │                   ▼
        │      pii_block template — NO URL
        ▼
 ┌───────────────────────────────────────┐
 │  Intent Classifier                    │
 │  {factual | advisory | comparison |   │
 │   prediction}                         │
 └───────────┬─────────────┬─────────────┘
             │ factual     │ advisory / comparison / prediction
             ▼             ▼
   ┌─────────────────┐  ┌──────────────────────────────┐
   │ Retriever       │  │ Refusal Composer             │
   │ (Phase 2)       │  │ • polite; facts-only policy  │
   └────────┬────────┘  │ • exactly ONE Groww URL from │
            ▼           │   whitelist                  │
   ┌─────────────────┐  └──────────────────────────────┘
   │ Confidence ≥ τ ?│  
   │ & hits non-empty│
   └──┬───────────┬──┘
   No │           │ Yes
      ▼           ▼
 dont_know      Groq or extractive body from top chunk
 _without_link  (≤ 3 sentences) + Source: URL +
 — NO URL       Last updated from sources: <date>
                 │
                 ▼
              Post-Processor
              • sentence count; banned tokens
              • exactly one whitelisted URL OR zero
              • defensive PII scan on draft output
```

### 3.3 Generator Contract & Guardrails

**Extractive (default):** Build the body from the top reranked chunk only: first ≤ 3 sentences, strip any URLs embedded in chunk text so the reply does not accidentally contain extra links.

**Groq (optional):** The model returns answer body only; `Source` and `Last updated` lines are appended in code so exactly one whitelist URL appears. On API/import failure or empty body → extractive fallback.

**Hard post-checks (deterministic, non-LLM):**
1. **Route-aware URL count:** PII and insufficient-evidence replies must contain zero URLs. Factual answers must contain exactly one URL, and it must appear in `sources.yaml`.
2. **Sentence count ≤ 3** for the factual body (before the Source: line).
3. **No banned tokens** in the full draft (e.g., "recommend", "should invest", "better than", "will outperform").
4. **Footer present** on successful factual path: `Last updated from sources: <YYYY-MM-DD>`.

If post-checks fail on an otherwise retrieved answer → fall back to safe template with one whitelisted link (`safe_template`).

**Exit criteria:** 100% of generated answers respect the URL policy above on the eval set; 0 hallucinated or extra URLs on factual paths.

---

## Phase 4 — Embedding & Vector Store

**Goal:** Enable semantic search over the curated corpus.

### 4.1 Embedding Model

| Option | Model | Rationale |
|--------|-------|-----------|
| Recommended (Cloud) | `text-embedding-3-small` (OpenAI) | Cost-effective, strong on financial text |
| Recommended (Local) | `BAAI/bge-small-en-v1.5` | State-of-the-art local model. Highly optimized for dense, short factual paragraphs (which perfectly matches our JSON-to-text chunks). |
| Alternative (Local) | `sentence-transformers/all-MiniLM-L6-v2` | Older local fallback, fast but less accurate than BGE. |

- Embed all chunks at ingestion time
- Store embeddings alongside metadata in vector DB

### 4.2 Vector Store

| Option | Type | Use Case |
|--------|------|----------|
| **ChromaDB** (recommended) | Local / embedded | Lightweight MVP, no infra overhead |
| Pinecone | Managed cloud | Scale-up path if corpus grows |
| FAISS | In-memory | Prototyping only |

**Index Configuration:**
- Distance metric: Cosine similarity
- Collection per AMC (extensible to multi-AMC)
- Metadata filters: `scheme_name`, `source_type`, `fetch_date`

### 4.3 Retrieval Configuration

```python
retrieval_config = {
    "top_k": 4,              # Retrieve top 4 most relevant chunks
    "score_threshold": 0.72, # Minimum similarity score; below = no confident answer
    "metadata_filter": {     # Optional — filter by scheme if query mentions one
        "scheme": detected_scheme_or_none
    }
}
```

**Fallback:** If top-1 similarity < 0.72, trigger "source not found" graceful response rather than hallucinating.

---

## Phase 5 — Query Processing & Intent Classification

**Goal:** Route queries correctly before hitting retrieval.

### 5.1 Intent Classification

```
Query → Intent Classifier
         │
         ├── FACTUAL → proceed to RAG retrieval
         │     Examples:
         │       "What is the exit load of Mirae Asset Large Cap Fund?"
         │       "Minimum SIP amount for ELSS fund?"
         │       "How do I download my capital gains statement?"
         │
         ├── ADVISORY → trigger refusal handler
         │     Examples:
         │       "Should I invest in this fund?"
         │       "Which fund is better for 5 years?"
         │       "Will this fund give 15% returns?"
         │
         └── AMBIGUOUS → ask clarifying question
               Examples:
                 "Tell me about Mirae Asset" (too broad)
```

**Classifier Implementation:**
- Use LLM-based classification (fast prompt, not full RAG)
- System prompt defines FACTUAL vs ADVISORY boundary explicitly
- Regex pre-filters for obvious advisory keywords: "should I", "better", "recommend", "return", "will it"

### 5.2 Scheme Entity Extraction

Before retrieval, extract:
- **Scheme name** (if mentioned) → used as metadata filter
- **Query type** (expense ratio / exit load / SIP / ELSS / statement) → used for re-ranking

### 5.3 Retrieval Strategy (Hybrid + Metadata Pre-Filtering)

Given the highly dense, fact-based nature of our corpus (exactly 5 chunks), we implement a strict Query Router to ensure 100% precision:

1. **Entity-Based Pre-Filtering (Top-K = 1)**
   - If the user query mentions a specific fund (e.g., "What is the exit load for HDFC Mid Cap?"), we extract the scheme name and pass it directly to ChromaDB as a metadata filter (`where={"scheme": "HDFC Mid Cap Opportunities Fund"}`).
   - This prevents semantic confusion and guarantees we only pull facts for the requested fund.

2. **Retrieve All for Comparisons (Top-K = 5)**
   - If the user asks a comparative query (e.g., "Compare the expense ratios of all funds"), we bypass vector similarity entirely. 
   - We dynamically set Top-K=5 and retrieve the entire database to allow the LLM to synthesize the comparison accurately.

3. **Hybrid Search (Dense + Sparse BM25)**
   - For general queries where a specific fund is not isolated, we use Reciprocal Rank Fusion (RRF) to combine Dense Embeddings (`BAAI/bge-small-en-v1.5`) with Sparse Keywords (`BM25Okapi`). This guarantees strict keyword matching while preserving semantic understanding.

---

**Goal:** Produce short, factual, cited responses with strict constraints.

### 5.1 Strict Response Rules
1. **Fact-Only:** Must only use context provided by the retriever.
2. **"I Don't Know" Policy:** If the answer is not in the retrieved context, the LLM must explicitly state it cannot answer. **CRITICAL:** If the answer is unknown, the system must **NOT** attach any source URLs.
3. **No PII (Personal Identifiable Information):** Any query containing personal information (account numbers, names, PAN cards, etc.) must be immediately rejected before processing.
4. **No Financial Advice:** Trigger the refusal handler for any advisory questions.
5. **Mandatory Citations:** Every factual response must end with the `source_url` and `last_updated_from_source` date (unless the answer is unknown).
6. Keep responses to a maximum of 3 sentences.
7. Always end with: "Source: [URL]" (use the chunk's source_url).
8. Always add footer: "Last updated from sources: [fetch_date]"
9. Do NOT provide investment advice, opinions, or return predictions.
10. If the context does not contain the answer, say:
   "This information is not available in our current source corpus.
    Please visit [AMC/AMFI URL] for official details."
7. Never mention PAN, Aadhaar, account numbers, or OTPs.

CONTEXT:
{retrieved_chunks}

USER QUERY:
{user_query}
```

### 5.2 Response Format Contract

```
[Answer — max 3 sentences, factual, verbatim from source context]

Source: https://[official-url]
Last updated from sources: [YYYY-MM-DD]
```

**Example Output:**
```
The exit load for Mirae Asset Large Cap Fund is 1% if units are redeemed
within 1 year from the date of allotment. There is no exit load after 1 year.

Source: https://miraeassetmf.co.in/downloads/kim/large-cap-fund.pdf
Last updated from sources: 2026-05-01
```

### 5.3 Refusal Handler

```
Trigger: ADVISORY intent detected

Output Template:
"I'm only able to provide factual information about mutual fund schemes —
such as expense ratios, exit loads, and SIP minimums. For investment
guidance, please consult a SEBI-registered financial advisor.

Learn more: https://www.amfiindia.com/investor-corner"

Footer: "Last updated from sources: [date]"
```

### 5.4 Performance-Query Special Case

For queries about past returns or NAV performance:
```
"For performance data on [Scheme Name], please refer to the official
factsheet directly. No return calculations or comparisons are provided here.

Source: https://miraeassetmf.co.in/factsheet"
Last updated from sources: [date]
```

---

## Phase 4 — User Interface (Minimal Web App)

**Purpose:** Give a clean, trustworthy surface to the assistant.

### 4.1 Layout

```
┌──────────────────────────────────────────────────────────────┐
│  Mutual Fund FAQ Assistant                                   │
│  Facts-only. No investment advice.            [disclaimer]   │
├──────────────────────────────────────────────────────────────┤
│  Welcome! Ask a factual question about HDFC MF schemes.      │
│                                                              │
│  Try one of these:                                           │
│   • What is the expense ratio of HDFC Mid Cap Fund?          │
│   • What is the exit load of HDFC Equity Fund?               │
│   • What is the lock-in period for an ELSS fund?             │
├──────────────────────────────────────────────────────────────┤
│  [  type your question…                                ] [→] │
├──────────────────────────────────────────────────────────────┤
│  Answer area                                                 │
│  ─ short answer (≤3 sentences)                               │
│  ─ Source: <single link>                                     │
│  ─ Last updated from sources: <date>                         │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 Stack & Endpoints

- **Framework:** FastAPI in `mf_faq.ui` exposes:
  - `POST /ask` — submit a query, returns compliant answer
  - `GET /meta` — returns source freshness metadata
  - `GET /health` — liveness check
- **Frontend:** Minimal static SPA served from `mf_faq/ui/static/` at `/` (same-origin fetch). HTML + Vanilla CSS/JS, no framework dependency.
- **No login, no cookies beyond session, no analytics that capture query text with PII.**

### 4.3 UI Rules (Non-negotiable)
- Disclaimer **always visible** (pinned to header, never collapses).
- Submit button **disabled** while a query is in flight.
- Answer area renders the citation as a clickable link with `rel="noopener nofollow"`.
- **“Copy answer”** optional; **“Share” deliberately omitted** to discourage misuse.

**Exit criteria:** End-to-end demo: type question → get compliant answer with link + date.

---

## Phase 5 — Evaluation, Compliance & Observability

**Purpose:** Prove the system is accurate, safe, and stays that way.

### 5a. Evaluation Harness

| Suite | What it checks | Pass bar |
|-------|---------------|----------|
| Factual Q&A (30+ Qs) | Exact-match / numeric tolerance vs gold answer | ≥ 90% |
| Citation correctness | Cited URL actually contains the fact | 100% |
| Refusal suite (15+ Qs) | Advice/comparison/prediction queries get refused with educational link | 100% |
| Out-of-corpus | Query about unknown scheme → "I don’t have a verified answer" | 100% |
| PII probes | Inputs with PAN/Aadhaar/email are rejected/redacted | 100% |
| Length & format | ≤ 3 sentences, 1 citation, footer present | 100% |

**Tooling:** A YAML test set + a small `pytest` runner that calls the API and asserts.

### 5b. Compliance Checks (CI Gate)
- Every URL in any answer ∈ `sources.yaml`.
- No banned advisory tokens in any answer.
- No PII tokens stored in logs (log-line scanner).

### 5c. Observability

Structured logs per query (no raw PII stored; queries are hashed):
```json
{
  "request_id": "uuid",
  "query_hash": "sha256(query)",
  "intent": "factual",
  "retrieved_chunk_ids": ["..."],
  "confidence": 0.82,
  "post_check_passed": true,
  "latency_ms": 740
}
```

**Dashboard (lightweight):** Refusal rate · "I don’t know" rate · Top schemes asked about · Ingestion freshness.

### 5d. Operational Runbook
- **Source change detection:** Alert when any of the 5 Groww URLs 404s or content hash drifts > X%.
- **Weekly re-index job** via GitHub Actions cron; manual `workflow_dispatch` override per source.
- **Exit criteria:** All eval suites green in CI; runbook published.

---

## Component Inventory (Cross-Phase)

| Layer | Component | Responsibility | Phase |
|-------|-----------|---------------|-------|
| Governance | `sources.yaml` | Whitelist of allowed URLs | 0 |
| Governance | `refusal_intents.yaml` | Refusal patterns + canned copy | 0 |
| Ingestion | Fetcher | HTTP download, ETag/hash tracking | 1 |
| Ingestion | Extractor + Cleaner | HTML → clean text, table-aware | 1 |
| Ingestion | Chunker | Heading-aware semantic chunking | 1 |
| Ingestion | Embedder | Vector generation | 1 |
| Storage | Vector store | Dense ANN search (FAISS/Chroma) | 1–2 |
| Storage | Keyword index | BM25 | 1–2 |
| Storage | Metadata store | Chunk metadata, source registry | 1–2 |
| Retrieval | Query normalizer | Acronym expansion, lowercase | 2 |
| Retrieval | Scheme resolver | Detect scheme to filter metadata | 2 |
| Retrieval | Hybrid retriever | Dense + BM25 + RRF | 2 |
| Retrieval | Re-ranker | Cross-encoder for precision | 2 |
| Orchestrator | PII guard | Reject inputs containing PII | 3 |
| Orchestrator | Intent classifier | factual vs advisory vs comparison etc. | 3 |
| Orchestrator | Confidence gate | Trigger “I don’t know” on low retrieval score | 3 |
| Generation | Groq LLM caller | Templated, low-temp chat completion (optional) | 3 |
| Generation | Post-processor | Length, citation, banned-token, PII checks | 3 |
| Generation | Refusal composer | Polite refusal + educational link | 3 |
| UI | FastAPI `/ask` API | JSON query → orchestrator result + structured logs | 4 |
| UI | Static SPA + CSS/JS | Welcome, examples, disclaimer, answer view, copy | 4 |
| Quality | Eval harness | Factual + refusal + format + PII suites | 5 |
| Quality | Compliance CI gate | Whitelist + banned-token + PII log scan | 5 |
| Ops | Refresh scheduler | GitHub Actions cron + `workflow_dispatch`; nightly/weekly re-ingest + diff detection | 1, 5 |
| Ops | Observability | Structured, PII-free logs + dashboard | 5 |

---

## Data Flow — Single Query End-to-End

```
1.  User types: "What is the exit load of HDFC Equity Fund Direct Growth?"
2.  UI → POST /ask {query}
3.  PII guard           → clean
4.  Intent classifier   → factual
5.  Query normalizer    → "what is the exit load of hdfc equity fund direct growth"
6.  Scheme resolver     → scheme_id = hdfc_equity
7.  Hybrid retriever    → top-K chunks from
                         https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth
8.  Re-ranker           → top-1 chunk: "Scheme Details / Exit Load" section
9.  Confidence gate     → score 0.82 ≥ τ → proceed
10. Groq generator (or extractive) → ≤3 sentence answer using only that chunk
11. Post-processor     → length OK, 1 URL OK, URL ∈ 5-URL whitelist OK,
                         no banned tokens, footer appended
12. Response:
    "HDFC Equity Fund Direct Growth charges an exit load of 1% if units are
     redeemed within 1 year of allotment; no exit load applies thereafter.
     Source: https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth
     Last updated from sources: 2026-04-15"
13. Logs: {request_id, intent=factual, scheme_id=hdfc_equity,
          chunk_ids=[...], conf=0.82, checks=passed, latency_ms=740}
          (no raw query stored)
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Groww updates a page → stale answer | Content-hash diff in nightly job; bump `last_updated`; alert if drift big |
| Groq model hallucinates a number | Numeric values must appear verbatim in retrieved chunk (regex check) |
| Groq model emits a non-whitelisted URL | Post-processor rejects + falls back to safe template |
| User asks for advice | Intent classifier + refusal composer (link = matching Groww scheme URL) |
| User pastes PAN/Aadhaar/email/phone | PII guard rejects request before retrieval; never logged |
| Ambiguous scheme name | Scheme resolver asks clarifying question (still facts-only, no opinions) |
| Performance/return question | Redirect to the relevant Groww scheme URL; never compute or compare returns |
| Low-confidence retrieval | "I don’t have a verified answer" + matching Groww scheme URL |
| Fact only present in KIM/SID (off-corpus) | Return "I don’t have a verified answer" + matching Groww scheme URL |

---

## Phase Roadmap

| Phase | Outcome | Indicative effort |
|-------|---------|-------------------|
| 0 | Sources whitelisted, refusal taxonomy ready | 0.5 day |
| 1 | Corpus ingested + indexed | 1.5 days |
| 2 | Hybrid retrieval + reranker working | 1 day |
| 3 | Orchestrator + guardrails + generator | 1.5 days |
| 4 | Minimal UI wired end-to-end | 0.5 day |
| 5 | Eval suites + CI gates + observability | 1 day |

---

## Alignment to Problem Statement

| Requirement | Where addressed |
|-------------|----------------|
| Curated corpus | Phase 0 — corpus is exactly the 5 Groww HDFC scheme URLs (locked in `sources.yaml`) |
| 3–5 schemes, category diversity | Phase 0 — 5 schemes: Mid Cap, Flexi Cap, Focused, ELSS, Large Cap |
| ≤ 3 sentences, exactly 1 citation | Phase 3 (prompt contract + deterministic post-checks) |
| Footer “Last updated from sources:” | Phase 3 (post-processor) |
| Refuse advisory queries with educational link | Phase 3 — link returned is the matching Groww scheme URL (one of the 5) |
| Welcome msg, 3 examples, visible disclaimer | Phase 4 (UI) |
| No PII collection/storage | Phase 3 (PII guard) + Phase 5 (log scanner) |
| Source restriction | Phase 0 — `sources.yaml` contains only the 5 Groww URLs; Phase 5 CI fails on any other URL in output |
| Performance queries | Phase 3 — redirect to the relevant Groww scheme URL; no returns computation/comparison |
| Accuracy + auditability | Phase 5 (eval suites + structured PII-free logs) |
| Statement / capital-gains / KIM-only facts | Out of scope this iteration — assistant returns “I don’t have a verified answer” + Groww URL |

---

## Disclaimer Snippet (UI + every refusal)

```
Facts-only. No investment advice.

This assistant provides factual information about HDFC Mutual Fund schemes
sourced exclusively from official Groww scheme pages.
It does not constitute investment advice, recommendations, or return
projections. Please consult a SEBI-registered investment advisor
before making any investment decisions.
```

---

*Architecture document for: Mutual Fund FAQ Assistant (HDFC MF via Groww)*  
*Schemes: 5 | Source URLs: 5 (locked) | Last Updated: May 2026*


*AMC: Mirae Asset Mutual Fund | Schemes: 5 | Source URLs: 22–26*