# Edge Cases — Phase 5: Response Generation

> Phase Goal: Produce a factual, cited, ≤3-sentence response using retrieved chunks and the LLM, or trigger the refusal/special-case handler.  
> Reference: `phase_wise_architecture.md § Phase 5`

---

## Response Format Contract

```
[Factual answer — max 3 sentences, grounded in retrieved context]

Source: https://groww.in/mutual-funds/[scheme-slug]
Last updated from sources: YYYY-MM-DD
```

---

## Edge Cases

| # | Edge Case | Scenario | Expected Behaviour | Priority |
|---|-----------|----------|--------------------|----------|
| 5.1 | Retrieved chunks are contradictory | Two chunks show different exit load values for the same scheme | Flag in response: "Sources show differing values. Please verify directly on Groww." | 🔴 High |
| 5.2 | LLM response exceeds 3 sentences | Model ignores the sentence-limit rule | Output validator counts sentences; truncate at sentence 3; append source and footer | 🔴 High |
| 5.3 | LLM generates a hallucinated source URL | Non-existent or non-corpus URL in citation | Domain whitelist check in output validator; reject and re-generate if URL not in `groww.in` | 🔴 High |
| 5.4 | LLM response contains advisory language | "You should consider this fund for long-term goals" | Output validator detects advisory keywords; reject response; re-generate with stricter prompt | 🔴 High |
| 5.5 | LLM API returns empty response | Network timeout or overloaded model | Retry once automatically; if still empty, return: "Unable to generate a response. Please try again." | 🟠 Medium |
| 5.6 | `fetch_date` is missing from chunk metadata | Footer cannot be populated with a date | Fall back to corpus manifest's `last_full_refresh` date | 🟠 Medium |
| 5.7 | User asks about NAV (real-time price data) | "What is today's NAV for HDFC Equity Fund?" | Trigger performance-query special case; redirect to Groww fund page; do not fabricate a number | 🔴 High |
| 5.8 | User asks for a comparison across all 5 schemes | "Compare expense ratio of all 5 HDFC funds" | Factual and allowed; retrieve per scheme; present as a list or table; add no recommendations | 🟠 Medium |
| 5.9 | Response is factually correct but incomplete | Partial exit load info retrieved (only "1 year" clause, not "no load after") | Always retrieve top-4 chunks; prompt instructs LLM to note if partial information is being returned | 🟠 Medium |
| 5.10 | No chunks retrieved (empty retrieval result) | Query well below score threshold (< 0.72) | Return: "This information is not available in our current source corpus. Please visit [Groww URL]." | 🔴 High |
| 5.11 | LLM uses prior knowledge instead of context | Model "fills in" a fact not in retrieved chunks | Temperature = 0 + strict prompt ("Answer ONLY from the provided context"); monitor via output validator | 🔴 High |
| 5.12 | Response footer shows a date far in the past | Last ingestion was months ago | Display exact date; do not hide staleness; users must see: "Last updated from sources: 2026-02-01" | 🟠 Medium |
| 5.13 | LLM wraps response in markdown or JSON | Model outputs `**bold**` or `{"answer": "..."}` | Normalize LLM output to plain text before output validation and display | 🟡 Low |
| 5.14 | Refusal handler is triggered but educational link is broken | AMFI URL changes or goes offline | Validate refusal links on startup; use a fallback hardcoded text if URL is unreachable | 🟠 Medium |

---

## Refusal Handler Templates

**Advisory Query:**
```
"I'm only able to provide factual information about HDFC mutual fund schemes —
such as expense ratios, exit loads, and SIP minimums. For investment guidance,
please consult a SEBI-registered financial advisor.

Learn more: https://www.amfiindia.com/investor-corner"
```

**Performance Query:**
```
"For performance data on [Scheme Name], please refer to the official
fund page directly. No return calculations or comparisons are provided here.

Source: https://groww.in/mutual-funds/[scheme-slug]
Last updated from sources: [date]"
```

---

## Test Checklist

- [ ] Submit a factual query — confirm ≤3 sentences with source + date footer
- [ ] Manually trigger contradictory chunk retrieval — confirm disambiguation message
- [ ] Force LLM to generate 5 sentences — confirm truncation at sentence 3
- [ ] Submit "Should I invest?" — confirm polite refusal with AMFI link
- [ ] Submit "What is today's NAV?" — confirm redirect to Groww, no number fabricated
- [ ] Set score threshold high to force empty retrieval — confirm "not in corpus" response
- [ ] Inject advisory keyword into LLM output mock — confirm re-generation triggered

---

*Phase 5 Edge Cases | HDFC Mutual Fund FAQ Assistant v1*
