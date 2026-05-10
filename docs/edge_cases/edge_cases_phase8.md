# Edge Cases — Phase 8: Deployment & Observability

> Phase Goal: Deploy the system (FastAPI backend + ChromaDB + React frontend), track corpus freshness, and maintain compliance-safe logs.  
> Reference: `phase_wise_architecture.md § Phase 8`

---

## Deployment Stack Reference

| Component | Tool | Notes |
|---|---|---|
| Backend API | FastAPI (Python) | `/query` endpoint |
| Vector Store | ChromaDB (local) | Persisted to disk |
| LLM | Claude Sonnet via Anthropic API | Temperature = 0 |
| Frontend | React (served via Nginx) | Static build |
| Hosting | Vercel (frontend) + Railway/Render (backend) | MVP |

---

## Edge Cases

| # | Edge Case | Scenario | Expected Behaviour | Priority |
|---|-----------|----------|--------------------|----------|
| 8.1 | Backend API is down | FastAPI server crashes or Render restarts | Frontend displays: "Service temporarily unavailable. Please try again shortly." | 🔴 High |
| 8.2 | ChromaDB collection missing at startup | First deployment without running ingestion first | Startup health-check detects 0 documents; block all queries; display "Knowledge base initializing." | 🔴 High |
| 8.3 | LLM API key is invalid or expired | Anthropic API returns 401 Unauthorized | Log alert immediately; do not expose key error to user; return: "Response generation temporarily unavailable." | 🔴 High |
| 8.4 | Log volume is too high | High traffic fills disk with query logs | Implement log rotation (daily); cap log file at 100 MB; archive older logs | 🟠 Medium |
| 8.5 | `corpus_manifest.json` is missing | Deleted or not committed during deployment | Regenerate manifest from ChromaDB metadata; use earliest `fetch_date` in DB as fallback date | 🟠 Medium |
| 8.6 | Deployment environment has no internet access | Air-gapped or firewall-restricted server | Switch to local embedding (`all-MiniLM-L6-v2`) and locally hosted LLM; pre-ingest corpus offline | 🟠 Medium |
| 8.7 | Race condition during simultaneous re-ingestion | Two workers write to ChromaDB at the same time | Use file-lock or DB mutex during ingestion; second process waits and skips if lock is held | 🟠 Medium |
| 8.8 | Frontend and backend version mismatch | Old frontend cached in browser after backend update | Version the API (`/v1/query`); add cache-busting headers; display version mismatch warning in UI | 🟠 Medium |
| 8.9 | Query hash collision in logs | Two different queries produce the same SHA-256 prefix | Log full timestamp + first 15 chars of query as secondary key; no user data stored | 🟡 Low |
| 8.10 | Render/Railway cold starts cause >5s first response | Serverless backend wakes up slowly | Implement a `/health` ping on frontend load to warm up the backend before user submits query | 🟠 Medium |
| 8.11 | ChromaDB persisted DB grows too large | Repeated re-ingestions without deduplication | Track document count per ingestion; deduplicate before insert; set a maximum DB size alert | 🟠 Medium |
| 8.12 | CORS policy blocks frontend from reaching backend | Vercel frontend cannot reach Render API | Configure FastAPI CORS middleware to allow Vercel production domain explicitly | 🔴 High |
| 8.13 | Anthropic API rate limit hit under load | Many simultaneous users trigger rate limit (429) | Implement request queue with retry-after handling; display "High traffic — please wait." to user | 🟠 Medium |
| 8.14 | Environment variable missing on deployment | `ANTHROPIC_API_KEY` not set in Render settings | Startup check validates all required env vars; fail fast with a clear error log, not a runtime crash | 🔴 High |

---

## Startup Health-Check Requirements

Every deployment startup must validate:

```python
STARTUP_CHECKS = [
    "ANTHROPIC_API_KEY present in environment",
    "ChromaDB collection exists and has > 0 documents",
    "corpus_manifest.json present and parseable",
    "All 5 scheme entries present in manifest",
    "Backend can reach LLM API (ping test)",
]
```

If any check fails → log the failure, block all query endpoints, return 503 on `/query`.

---

## Compliance-Safe Log Format

```json
{
  "query_hash": "sha256(query)[:16]",
  "intent": "FACTUAL | ADVISORY | AMBIGUOUS | OUT_OF_SCOPE",
  "top_chunk_score": 0.84,
  "response_sentences": 2,
  "source_domain": "groww.in",
  "pii_detected": false,
  "timestamp": "2026-05-03T10:22:00Z"
}
```

> **No raw query text, no user identifiers, no IP addresses stored in logs.**

---

## Test Checklist

- [ ] Deploy without running ingestion first — confirm "Knowledge base initializing" message
- [ ] Remove `ANTHROPIC_API_KEY` env var — confirm startup fail-fast with clear log
- [ ] Kill the backend — confirm frontend shows "Service unavailable" message
- [ ] Submit 20 requests simultaneously — confirm rate limiting and queue handling
- [ ] Remove `corpus_manifest.json` — confirm regeneration from ChromaDB metadata
- [ ] Mismatch frontend and backend versions — confirm version warning in UI
- [ ] Check CORS — confirm Vercel frontend can call Render backend without errors

---

*Phase 8 Edge Cases | HDFC Mutual Fund FAQ Assistant v1*
