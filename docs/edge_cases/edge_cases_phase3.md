# Edge Cases — Phase 3: Embedding & Vector Store

> Phase Goal: Convert all text chunks into vector embeddings and store them in ChromaDB for semantic retrieval.  
> Reference: `phase_wise_architecture.md § Phase 3`

---

## Configuration Reference

```python
retrieval_config = {
    "top_k": 4,
    "score_threshold": 0.72,   # Below this = no confident answer
    "distance_metric": "cosine"
}
```

---

## Edge Cases

| # | Edge Case | Scenario | Expected Behaviour | Priority |
|---|-----------|----------|--------------------|----------|
| 3.1 | Embedding API is unavailable | OpenAI API returns 500 or rate-limit (429) | Retry with backoff (max 3 attempts); fall back to local `all-MiniLM-L6-v2` if persistent | 🔴 High |
| 3.2 | Embedding dimension mismatch | Developer switches embedding model mid-project | Detect dimension mismatch on insertion; wipe and re-index entire ChromaDB collection | 🔴 High |
| 3.3 | ChromaDB collection is empty at query time | Vector store not yet initialized or ingestion not run | Startup health-check detects 0 documents; block all queries; display "Knowledge base initializing" | 🔴 High |
| 3.4 | Two chunks have near-identical embeddings | Very similar text across multiple fund pages | Both stored; cosine similarity naturally handles this; no action needed | 🟡 Low |
| 3.5 | All retrieved chunks fall below score threshold | Query is very specific (e.g., sub-topic not on Groww) | Return "not found" gracefully: "This information is not in our current source corpus." | 🟠 Medium |
| 3.6 | ChromaDB file corruption on disk | Disk write error or process killed mid-write | Detect checksum failure on load; trigger full re-ingestion from 5 source URLs | 🔴 High |
| 3.7 | Metadata filter returns zero results | Scheme detected in query but filter too narrow (e.g., typo in scheme key) | Broaden search by removing scheme filter; re-run similarity search against full corpus | 🟠 Medium |
| 3.8 | Top-K returns chunks from wrong scheme | Scheme entity not detected; retrieval pulls mixed-fund chunks | Post-filter retrieved chunks by `scheme` metadata field if entity was successfully extracted | 🟠 Medium |
| 3.9 | Embedding for a very short chunk is low-quality | 3-word chunk produces a poor embedding | Enforce minimum chunk token count (>20 tokens) in Phase 2 before embedding is attempted | 🟠 Medium |
| 3.10 | OpenAI API rate limit hit during bulk ingestion | 5 pages × many chunks = high API call volume | Implement token bucket / rate limiter; batch requests with delay between batches | 🟠 Medium |
| 3.11 | ChromaDB runs out of disk space | Large number of chunks fills available storage | Monitor disk usage; alert at 80% capacity; apply chunk deduplication to reduce footprint | 🟠 Medium |
| 3.12 | Collection name collision | Two ingestion runs use the same collection name | Use versioned collection names (`hdfc_v1`, `hdfc_v2`) or overwrite with explicit confirmation | 🟡 Low |

---

## Test Checklist

- [ ] Embed all chunks from 5 pages — confirm ChromaDB reports correct document count
- [ ] Run a similarity search — confirm top-4 results returned with scores
- [ ] Query with a very specific term — confirm graceful "not found" when score < 0.72
- [ ] Switch embedding model — confirm dimension mismatch is detected and re-indexing triggered
- [ ] Simulate API outage — confirm fallback to local model activates
- [ ] Corrupt ChromaDB file — confirm re-ingestion is triggered on next startup

---

*Phase 3 Edge Cases | HDFC Mutual Fund FAQ Assistant v1*
