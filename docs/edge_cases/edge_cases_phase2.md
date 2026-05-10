# Edge Cases — Phase 2: Preprocessing & Chunking

> Phase Goal: Convert raw fetched content into clean, metadata-tagged text chunks ready for embedding.  
> Reference: `phase_wise_architecture.md § Phase 2`

---

## Chunking Strategy Reference

| Content Type | Chunk Size | Overlap |
|---|---|---|
| Table-heavy sections (e.g., expense ratio grid) | 300 tokens | 50 tokens |
| Dense text sections (fund details, disclaimers) | 500 tokens | 100 tokens |
| Q&A / FAQ-style sections | Per Q&A pair | None |

---

## Edge Cases

| # | Edge Case | Scenario | Expected Behaviour | Priority |
|---|-----------|----------|--------------------|----------|
| 2.1 | Chunk is entirely boilerplate | Header/footer text repeats identically across all 5 pages | Remove using boilerplate fingerprinting (hash-based); do not store duplicate chunks | 🟠 Medium |
| 2.2 | Chunk size is 0 after cleaning | Section heading with no body text underneath | Skip empty chunks entirely; do not embed or store | 🟠 Medium |
| 2.3 | Table data gets broken during extraction | Groww renders an expense ratio table with merged cells | Flatten table rows into key-value sentences: `"Expense Ratio (Direct): 0.52%"` | 🔴 High |
| 2.4 | A single sentence exceeds max chunk size | Very long legal disclaimer run-on sentence | Force-split at nearest punctuation boundary; store as two overlapping chunks | 🟠 Medium |
| 2.5 | Metadata field `fetch_date` is missing | Ingestion pipeline skips date tagging | Block chunk from being stored; all metadata fields are mandatory | 🔴 High |
| 2.6 | Scheme name cannot be auto-detected from page content | Generic Groww page title without explicit fund name | Fall back to scheme name from the Phase 0 URL manifest entry | 🔴 High |
| 2.7 | Duplicate chunks across two fund pages | "No exit load after 1 year" text is identical on 3 pages | Hash-based deduplication; keep one chunk with primary source URL; note alternate sources in metadata | 🟠 Medium |
| 2.8 | Chunk contains data from two different schemes | Groww "You may also like" or related funds section bleeds into content | Detect multi-scheme content via entity extraction; split or discard to prevent cross-contamination | 🔴 High |
| 2.9 | PDF-style ligature artifacts in extracted text | "fi" and "fl" rendered as single characters (ﬁ, ﬂ) | Normalize ligatures during text cleaning before chunking | 🟡 Low |
| 2.10 | Chunk contains only numbers or special characters | Groww renders a chart or image caption as raw characters | Validate chunk has minimum meaningful word count (>10 words); discard if below threshold | 🟠 Medium |
| 2.11 | Overlapping chunks create contradictory context | Chunk boundary splits a conditional clause mid-way | Use semantic-boundary splitting (sentence endings, section headers) rather than fixed token counts | 🟠 Medium |
| 2.12 | Cleaned text length is zero for an entire page | Groww page fetched but cleaning removed all content | Mark scheme as `no_content`; exclude from vector store; do not serve queries against this scheme | 🔴 High |

---

## Required Chunk Metadata Schema

Every stored chunk must have all fields populated:

```json
{
  "chunk_id": "hdfc_mid_cap_p2_c3",
  "text": "...",
  "metadata": {
    "scheme": "HDFC Mid Cap Opportunities Fund",
    "source_url": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
    "fetch_date": "2026-05-01",
    "content_type": "fund_details"
  }
}
```

> **Validation rule:** If any metadata field is `null` or empty, the chunk must be rejected and logged.

---

## Test Checklist

- [ ] Run chunker on all 5 pages — confirm no chunk has 0 tokens
- [ ] Introduce a duplicate section across two pages — confirm only one chunk stored
- [ ] Pass a table-heavy page — confirm expense ratio is readable as text post-flatten
- [ ] Remove `fetch_date` from a test chunk — confirm storage rejection
- [ ] Include a "related funds" section — confirm it is excluded from chunks
- [ ] Pass a page where all content is cleaned away — confirm `no_content` flagging

---

*Phase 2 Edge Cases | HDFC Mutual Fund FAQ Assistant v1*
