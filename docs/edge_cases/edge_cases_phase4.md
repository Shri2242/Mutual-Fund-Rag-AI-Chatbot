# Edge Cases — Phase 4: Query Processing & Intent Classification

> Phase Goal: Receive user query, sanitize it, classify intent (FACTUAL / ADVISORY / AMBIGUOUS / OUT_OF_SCOPE), and extract scheme entity before routing to retrieval.  
> Reference: `phase_wise_architecture.md § Phase 4`

---

## Intent Classification Reference

```
Query → Intent Classifier
         │
         ├── FACTUAL         → proceed to RAG retrieval
         ├── ADVISORY        → trigger refusal handler
         ├── AMBIGUOUS       → ask clarifying question
         └── OUT_OF_SCOPE    → politely decline
```

---

## Edge Cases

| # | Edge Case | Scenario | Expected Behaviour | Priority |
|---|-----------|----------|--------------------|----------|
| 4.1 | Query is in Hindi or a regional language | "इस फंड में कितना SIP करना चाहिए?" | Detect non-English input; respond: "Please enter your question in English for v1." | 🟠 Medium |
| 4.2 | Query is extremely short or vague | "exit load?" or just "?" | Classify as AMBIGUOUS; ask: "Could you clarify which HDFC fund you're referring to?" | 🟠 Medium |
| 4.3 | Query contains multiple intents | "What is the exit load and should I invest?" | Split: answer factual part via RAG; refuse advisory part in the same response | 🔴 High |
| 4.4 | Advisory keyword used in a factual context | "What is the return calculation method used by HDFC?" | Do NOT trigger refusal — "return calculation" as methodology is factual; LLM classifier makes final call | 🔴 High |
| 4.5 | Regex pre-filter produces a false positive | "Should the exit load be before or after redemption?" | Regex fires on "should"; escalate to LLM classifier; do not refuse purely on regex match | 🔴 High |
| 4.6 | Scheme name in query is misspelled | "HDFC Midcap fund" vs "HDFC Mid Cap Opportunities Fund" | Use fuzzy matching against 5 known scheme names; map to closest match above 80% similarity threshold | 🟠 Medium |
| 4.7 | Query mentions a scheme not in the 5 URLs | "Tell me about HDFC Small Cap Fund" | Respond: "This assistant covers only 5 HDFC schemes. HDFC Small Cap Fund is not currently in scope." | 🔴 High |
| 4.8 | Query is completely off-topic | "What is the weather in Mumbai?" | Classify as OUT_OF_SCOPE; respond: "I can only answer questions about HDFC mutual fund schemes." | 🟠 Medium |
| 4.9 | User sends an empty query | Blank input or only whitespace | Block at UI layer before submission; if it reaches backend, return 400 with "Query cannot be empty." | 🟠 Medium |
| 4.10 | Very long query (>500 words) | User pastes a long paragraph or article | Truncate to first 300 tokens for classification; log truncation; do not silently drop content | 🟠 Medium |
| 4.11 | Query asks about performance / returns | "How has HDFC Mid Cap performed this year?" | Classify as performance-query special case; redirect to official page; no retrieval or generation | 🔴 High |
| 4.12 | Query asks to compare two schemes | "Compare expense ratio of HDFC Equity and HDFC Large Cap" | Factual comparison is allowed; retrieve for each scheme separately; present as a table, not a recommendation | 🟠 Medium |
| 4.13 | Scheme entity extraction picks wrong fund | Query says "large cap" — maps to wrong scheme | Disambiguate: there is only 1 large cap scheme in corpus; present the match and ask for confirmation | 🟡 Low |
| 4.14 | User explicitly asks for investment advice | "Give me your best recommendation" | Classify as ADVISORY immediately; trigger refusal handler; include AMFI education link | 🔴 High |

---

## Classification Boundary Examples

| Query | Classification | Reason |
|-------|---------------|--------|
| "What is the expense ratio of HDFC Equity Fund?" | ✅ FACTUAL | Objective, answerable from corpus |
| "Should I invest in HDFC ELSS?" | ❌ ADVISORY | "Should I invest" is advisory |
| "What does riskometer mean?" | ✅ FACTUAL | Definitional, objective |
| "Will this fund give 15% returns?" | ❌ ADVISORY | Predictive claim |
| "HDFC funds" | ⚠️ AMBIGUOUS | Too broad — needs clarification |
| "Best mutual fund in India?" | 🚫 OUT_OF_SCOPE | Not about corpus schemes |

---

## Test Checklist

- [ ] Submit a clearly factual query — confirm FACTUAL classification and RAG routing
- [ ] Submit "should I invest?" — confirm ADVISORY classification and refusal response
- [ ] Submit "exit load?" (no scheme named) — confirm AMBIGUOUS and clarification prompt
- [ ] Submit a misspelled scheme name — confirm fuzzy match resolves correctly
- [ ] Submit a query about a non-corpus scheme — confirm out-of-scope response
- [ ] Submit "return calculation method" — confirm NOT refused (factual context)
- [ ] Submit empty string — confirm 400 error or UI block

---

*Phase 4 Edge Cases | HDFC Mutual Fund FAQ Assistant v1*
