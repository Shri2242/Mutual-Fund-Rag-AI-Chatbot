# Edge Cases — Phase 6: User Interface

> Phase Goal: Provide a minimal, compliant, trust-signalling chat UI with welcome message, 3 example questions, persistent disclaimer, and chat history.  
> Reference: `phase_wise_architecture.md § Phase 6`

---

## UI Components Reference

```
┌────────────────────────────────────────────────────────┐
│  🏦  Mutual Fund FAQ Assistant                          │
│  ⚠️  Facts-only. No investment advice.  [ALWAYS VISIBLE]│
├────────────────────────────────────────────────────────┤
│  Try asking: [3 clickable example questions]           │
├────────────────────────────────────────────────────────┤
│  [Chat window]                                         │
├────────────────────────────────────────────────────────┤
│  [Text input] ___________________________ [Send]       │
└────────────────────────────────────────────────────────┘
```

---

## Edge Cases

| # | Edge Case | Scenario | Expected Behaviour | Priority |
|---|-----------|----------|--------------------|----------|
| 6.1 | User sends query by pressing Enter rapidly multiple times | Multiple identical requests submitted in quick succession | Debounce input (300ms); disable Send button while response is loading | 🔴 High |
| 6.2 | Response takes >10 seconds | Slow LLM API or network lag | Show loading spinner; after 15s display: "This is taking longer than expected. Please wait or try again." | 🟠 Medium |
| 6.3 | Chat history grows very long | 50+ exchanges in one session | Paginate or virtualize the chat list; do not send full history to LLM context | 🟠 Medium |
| 6.4 | User pastes PII into the input field | PAN number or Aadhaar pasted into chat box | Client-side PII pattern detection; clear the input; show warning before any submission | 🔴 High |
| 6.5 | User is on a mobile device with a small screen | Long source URLs break the layout | Truncate displayed URL with ellipsis; full URL accessible via tap/click | 🟠 Medium |
| 6.6 | Example question buttons clicked multiple times rapidly | Fast repeated clicks on "Try asking" prompts | Disable button on click until response is received; treat as single submission | 🟠 Medium |
| 6.7 | Browser back button navigates away during session | Chat history lost mid-conversation | Warn user on navigating away using browser `beforeunload` event | 🟡 Low |
| 6.8 | Disclaimer not visible on mobile | Bottom disclaimer scrolled out of view | Disclaimer must also appear as a persistent top banner; always visible without scrolling | 🔴 High |
| 6.9 | User pastes a very long message | >1000 character input submitted | Trim input to 500 characters at the UI layer; display inline count and warning | 🟠 Medium |
| 6.10 | User submits a query while previous one is still loading | Second request fired before first resolves | Queue or block second submission; prevent parallel in-flight requests | 🟠 Medium |
| 6.11 | No internet connection on user's device | UI loads but API calls fail | Detect offline state; display: "You appear to be offline. Please check your connection." | 🟠 Medium |
| 6.12 | Source URL in response is very long | Full Groww URL wraps across multiple lines in chat | Wrap URL in a styled `<a>` tag with descriptive link text (e.g., "View on Groww") | 🟡 Low |
| 6.13 | User uses browser's built-in autofill in the query box | Browser suggests previous form data | Disable autofill on the query input field (`autocomplete="off"`) | 🟠 Medium |
| 6.14 | UI renders on very old browser (IE11) | Layout breaks or JS fails | Display graceful "browser not supported" message; target Chrome/Firefox/Safari/Edge only | 🟡 Low |

---

## Privacy Constraints Checklist (UI Layer)

- [ ] Input field has `autocomplete="off"` and `autocorrect="off"`
- [ ] No cookies beyond session; no tracking pixels or analytics
- [ ] PAN/Aadhaar pattern detected client-side before any API call
- [ ] Chat history is session-only; cleared on page refresh
- [ ] Source URLs displayed as clickable links, not raw text

---

## Test Checklist

- [ ] Click Send 5 times rapidly — confirm only 1 request fires
- [ ] Wait 20 seconds for response — confirm timeout message appears
- [ ] Paste a PAN number — confirm input is cleared and warning shown
- [ ] Open on a 375px screen — confirm disclaimer is visible at top
- [ ] Type 800 characters — confirm trim at 500 with character counter
- [ ] Go offline mid-session — confirm offline message displayed
- [ ] Click example question — confirm auto-submit and button disabled

---

*Phase 6 Edge Cases | HDFC Mutual Fund FAQ Assistant v1*
