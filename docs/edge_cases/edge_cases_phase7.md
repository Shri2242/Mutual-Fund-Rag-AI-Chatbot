# Edge Cases — Phase 7: Compliance & Safety Layer

> Phase Goal: Enforce systematic guardrails at every layer — PII filtering on input, advisory detection, domain whitelist on output citations, and output format validation.  
> Reference: `phase_wise_architecture.md § Phase 7`

---

## Guardrails Reference

| Layer | Check | Where |
|---|---|---|
| PII Filter | Regex detection of PAN, Aadhaar, Phone, Email | Input (before classification) |
| Intent Check | FACTUAL vs ADVISORY classification | Input (before retrieval) |
| Domain Whitelist | Source URL must be on `groww.in` | Output (before display) |
| Output Validator | Sentence count, advisory keywords, footer presence | Output (before display) |

---

## Edge Cases

| # | Edge Case | Scenario | Expected Behaviour | Priority |
|---|-----------|----------|--------------------|----------|
| 7.1 | PII regex produces a false positive | "My name is PAN Lal" partially matches PAN pattern | Increase regex precision with word-boundary anchors; log false positive count for tuning | 🔴 High |
| 7.2 | PII is embedded mid-sentence | "For PAN ABCDE1234F, what is the exit load?" | Regex detects pattern regardless of position; block the query and ask user to rephrase | 🔴 High |
| 7.3 | Output validator flags a valid response as advisory | LLM says "This fund is a stable option" | Log as false positive; tune blocked keyword list to require stronger advisory phrasing, not lone adjectives | 🔴 High |
| 7.4 | Domain whitelist blocks a valid groww.in URL | `groww.in` not in ALLOWED_DOMAINS (oversight) | Update `ALLOWED_DOMAINS` to include `groww.in`; this is the primary v1 source domain | 🔴 High |
| 7.5 | Both PII detected AND advisory intent | "Should I use my PAN to invest here?" | PII filter fires first (before intent check); block at PII stage; do not proceed to classification | 🟠 Medium |
| 7.6 | Compliance layer itself throws an exception | Regex engine error or sanitizer crash | Fail safe: block the query; return generic error; never let unsanitized input reach the LLM | 🔴 High |
| 7.7 | LLM response is in non-standard format | LLM wraps answer in JSON or markdown code block | Normalize output to plain text before running validator checks | 🟠 Medium |
| 7.8 | Output validator runs but response has no source URL | LLM omits the source citation line | Validator fails "source URL present?" check; response is rejected; re-generate with stricter prompt | 🔴 High |
| 7.9 | Output validator runs but footer date is missing | LLM omits "Last updated from sources:" line | Inject footer automatically from chunk metadata rather than relying on LLM to include it | 🟠 Medium |
| 7.10 | Advisory keyword appears inside a quoted user question | Response repeats user query: "You asked 'should I invest?'" | Validator must check the generated answer text only, not any echoed user query | 🟠 Medium |
| 7.11 | PII filter is slow and adds >500ms latency | Complex regex on long input | Profile regex performance; pre-compile all patterns at startup to reduce match overhead | 🟡 Low |
| 7.12 | Multiple PII types detected in one query | Email + phone number in same sentence | Block on first match; report type of PII detected in response (e.g., "Email address detected") | 🟠 Medium |

---

## PII Pattern Reference

```python
PII_PATTERNS = {
    "PAN":     r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b",
    "Aadhaar": r"\b\d{4}\s?\d{4}\s?\d{4}\b",
    "Phone":   r"\b[6-9]\d{9}\b",
    "Email":   r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
}
```

> **Note:** Word boundaries (`\b`) must be used to reduce false positives on PAN and Aadhaar patterns.

## Domain Whitelist (v1)

```python
ALLOWED_DOMAINS = [
    "groww.in"   # Only corpus source for v1
]
```

---

## Test Checklist

- [ ] Send a query with a PAN number — confirm block and "PAN detected" message
- [ ] Send "My name is PAN Lal" — confirm this is NOT blocked (false positive prevention)
- [ ] Send a query with a phone number mid-sentence — confirm block
- [ ] Generate a response with a non-groww.in URL — confirm output rejection
- [ ] Generate a response with 4 sentences — confirm truncation at 3
- [ ] Generate a response with "you should invest" — confirm re-generation triggered
- [ ] Crash the sanitizer function intentionally — confirm fail-safe blocks the query

---

*Phase 7 Edge Cases | HDFC Mutual Fund FAQ Assistant v1*
