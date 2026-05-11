"""
Streamlit App — Mutual Fund FAQ Assistant
==========================================
Self-contained deployment. Does NOT import the orchestrator module
(avoids heavy deps like chromadb, sentence-transformers, torch).

Inlines: PII detector, intent classifier, keyword retriever, Groq/extractive
generator, and post-processor with URL whitelist enforcement.

Usage:
    streamlit run streamlit_app.py
"""

import sys
import os
import re
import json
from pathlib import Path

import streamlit as st

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env", override=False)
except ImportError:
    pass

# ─────────────────────────────────────────────────────────────────────────────
# INLINED CORE LOGIC
# ─────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.resolve()
CHUNKS_FILE = ROOT / "src" / "phase2_chunking" / "output" / "chunks.jsonl"
MANIFEST_PATH = ROOT / "src" / "phase0_corpus_registry" / "corpus_manifest.json"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
CONFIDENCE_THRESHOLD = 1

ALLOWED_URLS = [
    "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-focused-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
    "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
]

PII_BLOCK = (
    "Your message contains potentially sensitive personal information. "
    "For your security, this query has been blocked. "
    "We will never ask for your PAN, Aadhaar, OTP, or account details."
)
DONT_KNOW = (
    "This information is not available in our current source corpus. "
    "Please name the specific HDFC scheme you are asking about and try again."
)
REFUSAL = (
    "As a facts-only assistant, I cannot provide investment advice, "
    "fund comparisons, or return predictions. "
    "Please consult a SEBI-registered financial advisor."
)
SAFE_TEMPLATE = (
    "I'm sorry, I encountered an error verifying my response. "
    "Please check the official Groww page for accurate details."
)

BANNED_TOKENS = [
    "recommend", "should invest", "better than",
    "will outperform", "guaranteed", "best fund",
]

PII_PATTERNS = [
    r"[A-Z]{5}[0-9]{4}[A-Z]{1}",
    r"\b\d{4}\s?\d{4}\s?\d{4}\b",
    r"\b[6-9]\d{9}\b",
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b",
]

FUND_ALIAS_MAP = {
    "hdfc-equity-fund":      ["equity", "flexi", "flexicap", "flexi cap"],
    "hdfc-mid-cap-fund":     ["mid cap", "midcap", "mid-cap", "opportunities"],
    "hdfc-focused-fund":     ["focused"],
    "hdfc-elss":             ["elss", "tax saver", "tax-saver", "lock"],
    "hdfc-large-cap-fund":   ["large cap", "largecap", "large-cap"],
}

QUERY_ALIAS_MAP = {
    "equity fund":       "mutual-funds_hdfc-equity-fund-direct-growth",
    "equity":            "mutual-funds_hdfc-equity-fund-direct-growth",
    "flexi cap":         "mutual-funds_hdfc-equity-fund-direct-growth",
    "flexicap":          "mutual-funds_hdfc-equity-fund-direct-growth",
    "mid cap":           "mutual-funds_hdfc-mid-cap-fund-direct-growth",
    "midcap":            "mutual-funds_hdfc-mid-cap-fund-direct-growth",
    "mid-cap":           "mutual-funds_hdfc-mid-cap-fund-direct-growth",
    "opportunities":     "mutual-funds_hdfc-mid-cap-fund-direct-growth",
    "focused":           "mutual-funds_hdfc-focused-fund-direct-growth",
    "elss":              "mutual-funds_hdfc-elss-tax-saver-fund-direct-plan-growth",
    "tax saver":         "mutual-funds_hdfc-elss-tax-saver-fund-direct-plan-growth",
    "tax-saver":         "mutual-funds_hdfc-elss-tax-saver-fund-direct-plan-growth",
    "large cap":         "mutual-funds_hdfc-large-cap-fund-direct-growth",
    "largecap":          "mutual-funds_hdfc-large-cap-fund-direct-growth",
    "large-cap":         "mutual-funds_hdfc-large-cap-fund-direct-growth",
}

FIELD_MAP = [
    (["riskometer", "risk level", "risk rating", "risk class"], "risk level is rated"),
    (["expense ratio", "ter", "total expense"],                  "Expense Ratio"),
    (["exit load", "redemption charge", "exit charge"],          "Exit Load"),
    (["nav", "net asset value", "current price"],                "NAV"),
    (["aum", "assets under management", "fund size"],           "Assets Under Management"),
    (["sip", "minimum sip", "minimum investment"],              "minimum SIP"),
    (["benchmark", "benchmark index"],                          "benchmark index"),
    (["fund manager", "who manages", "managed by"],             "fund manager"),
    (["lock-in", "lock in", "elss lock", "3 year"],             "lock-in period"),
    (["holding", "portfolio", "top stock", "allocation"],       "Top holdings"),
]


def contains_pii(text):
    return any(re.search(p, text) for p in PII_PATTERNS)


def classify_intent(query):
    q = query.lower()
    advisory = ["should i", "recommend", "better", "invest in", "good investment", "which fund"]
    prediction = ["will it", "future return", "forecast", "grow", "expected return"]
    comparison = [" vs ", "compare", "difference between", "which is better"]
    if any(kw in q for kw in advisory):
        return "advisory"
    if any(kw in q for kw in prediction):
        return "prediction"
    if any(kw in q for kw in comparison):
        return "comparison"
    return "factual"


def load_chunks():
    chunks = []
    if CHUNKS_FILE.exists():
        with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    chunks.append(json.loads(line))
    return chunks


def _get_searchable(chunk):
    slug = chunk.get("chunk_id", "").replace("-", " ").replace("_", " ")
    scheme = chunk.get("metadata", {}).get("scheme", "")
    text = chunk.get("text", "")
    alias_tokens = ""
    for slug_key, tokens in FUND_ALIAS_MAP.items():
        if slug_key in chunk.get("chunk_id", ""):
            alias_tokens = " ".join(tokens)
            break
    return f"{slug} {scheme} {alias_tokens} {text}".lower()


def retrieve(chunks, query):
    q_lower = query.lower()
    q_terms = q_lower.split()
    # Alias shortcut
    for phrase in sorted(QUERY_ALIAS_MAP.keys(), key=len, reverse=True):
        if phrase in q_lower:
            target_id = QUERY_ALIAS_MAP[phrase]
            for chunk in chunks:
                if chunk.get("chunk_id") == target_id:
                    score = max(3, sum(1 for t in q_terms if t in _get_searchable(chunk)))
                    return chunk, score
    # Keyword scoring
    best_chunk, best_score = None, 0
    for chunk in chunks:
        searchable = _get_searchable(chunk)
        score = sum(1 for t in q_terms if t in searchable)
        if score > best_score:
            best_score, best_chunk = score, chunk
    return best_chunk, best_score


def extractive_generate(text, query):
    text = re.sub(r"https?://\S+", "", text).strip()
    q_lower = query.lower()
    matched = []
    for keywords, fragment in FIELD_MAP:
        if any(kw in q_lower for kw in keywords):
            matched.append(fragment.lower())
    if not matched:
        return text
    sentences = text.split(". ")
    relevant = []
    if sentences:
        relevant.append(sentences[0])
    for sentence in sentences[1:]:
        s_lower = sentence.lower()
        if any(frag in s_lower for frag in matched):
            relevant.append(sentence)
    return ". ".join(relevant) + ("." if relevant and not relevant[-1].endswith(".") else "")


def groq_generate(chunk_text, query, history=None):
    if not GROQ_API_KEY:
        return None
    try:
        import httpx

        hist_text = ""
        if history:
            hist_text = (
                "RECENT HISTORY:\n"
                + "\n".join(
                    [f"{h['role'].upper()}: {h['content']}" for h in history[-2:]]
                )
            )

        system_prompt = (
            "You are a professional, facts-only mutual fund information assistant.\n"
            "Rules:\n"
            "1. Answer ONLY from the provided context. Do NOT use prior knowledge.\n"
            "2. CONCISE MODE: If the user asks for a specific metric, return ONLY:\n"
            "   Fund: <fund_name>\n"
            "   <Metric>: <value>\n"
            "   Date: <as_of_date>\n"
            "3. If the user asks a general question, provide a brief summary.\n"
            "4. HISTORY: Use provided chat history to resolve pronouns.\n"
            "5. Do NOT include any URLs or links.\n"
            "6. Do NOT provide investment advice.\n"
            "7. If the context is insufficient, reply ONLY with: DONT_KNOW\n"
        )

        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"{hist_text}\n\nCONTEXT:\n{chunk_text}\n\nUSER QUERY:\n{query}",
                    },
                ],
                "temperature": 0.0,
                "max_tokens": 256,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            body = resp.json()["choices"][0]["message"]["content"].strip()
            if "DONT_KNOW" in body or not body:
                return None
            return re.sub(r"https?://\S+", "", body).strip()
    except Exception as e:
        print(f"[Groq] call failed: {e}")
    return None


def answer_query(query, chunks, history=None):
    """Full pipeline: PII -> Intent -> Retrieve -> Generate -> Post-process."""
    if contains_pii(query):
        return PII_BLOCK

    intent = classify_intent(query)
    if intent != "factual":
        chunk, _ = retrieve(chunks, query)
        ref_url = chunk["metadata"]["source_url"] if chunk else ALLOWED_URLS[0]
        return f"{REFUSAL}\n\nFor more information: {ref_url}"

    # History resolution
    processed_query = query
    if history and any(
        kw in query.lower() for kw in ["it", "its", "that fund", "this fund", "the fund"]
    ):
        for turn in reversed(history):
            if turn["role"] == "assistant" and "Fund:" in turn["content"]:
                last_fund = turn["content"].split("Fund:")[1].split("\n")[0].strip()
                processed_query = f"{query} ({last_fund})"
                break

    # Retrieve
    chunk, score = retrieve(chunks, processed_query)
    if score < CONFIDENCE_THRESHOLD and processed_query != query:
        chunk2, score2 = retrieve(chunks, query)
        if score2 > score:
            chunk, score = chunk2, score2

    if not chunk or score < CONFIDENCE_THRESHOLD:
        return DONT_KNOW

    # Generate
    text = chunk["text"]
    url = chunk["metadata"].get("source_url", "")
    fetch_date = chunk["metadata"].get("fetch_date", "N/A")

    body = groq_generate(text, query, history)
    if body is None:
        body = extractive_generate(text, query)

    if not body:
        return DONT_KNOW

    # Post-process
    if contains_pii(body) or any(b in body.lower() for b in BANNED_TOKENS):
        return SAFE_TEMPLATE
    if url not in ALLOWED_URLS:
        return SAFE_TEMPLATE

    draft = f"{body}\n\nSource: {url}\nLast updated from sources: {fetch_date}"
    if len(re.findall(r"https?://", draft)) != 1:
        return SAFE_TEMPLATE
    return draft


# ─────────────────────────────────────────────────────────────────────────────
# STREAMLIT APP
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Grow RAG — Mutual Fund FAQ Assistant",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
    :root {
        --bg: #121212; --bg-card: #1E1E1E; --bg-hover: #2C2C2C;
        --border: #333333; --text-primary: #FFFFFF; --text-secondary: #B3B3B3;
        --text-muted: #808080; --accent: #00d09c; --red: #eb5b3c;
        --blue: #4781ff; --radius: 12px;
    }
    .stApp { background: var(--bg) !important; }
    .stSidebar { background: var(--bg-card) !important; border-right: 1px solid var(--border) !important; }
    .user-message {
        background: var(--bg-hover); color: #fff; padding: 12px 18px;
        border-radius: 18px 18px 4px 18px; margin: 8px 0 8px auto;
        max-width: 80%; width: fit-content; font-size: 15px;
        border: 1px solid var(--border); animation: fadeIn 0.3s ease;
    }
    .ai-message {
        background: var(--bg-card); border: 1px solid var(--border);
        border-radius: var(--radius); padding: 18px 20px; margin: 8px 0;
        animation: fadeIn 0.3s ease;
    }
    .ai-message.refusal { border-color: rgba(235,91,60,0.4); }
    .ai-message.pii { border-color: var(--red); }
    .ai-header {
        display: flex; align-items: center; gap: 10px; margin-bottom: 12px;
        padding-bottom: 10px; border-bottom: 1px solid var(--border);
    }
    .ai-avatar {
        width: 28px; height: 28px; border-radius: 50%; background: var(--accent);
        display: flex; align-items: center; justify-content: center;
        font-size: 14px; color: var(--bg); font-weight: bold;
    }
    .ai-label { font-size: 14px; font-weight: 600; color: var(--text-primary); flex: 1; }
    .intent-badge {
        font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 4px;
    }
    .intent-badge.factual { background: rgba(0,208,156,0.15); color: var(--accent); }
    .intent-badge.advisory { background: rgba(235,91,60,0.15); color: var(--red); }
    .intent-badge.pii { background: rgba(239,68,68,0.1); color: var(--red); }
    .intent-badge.dont_know { background: rgba(71,129,255,0.1); color: var(--blue); }
    .ai-body { font-size: 15px; line-height: 1.65; color: var(--text-primary); white-space: pre-wrap; }
    .ai-footer { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border); display: flex; gap: 12px; font-size: 13px; color: var(--text-muted); }
    .source-block { margin-top: 12px; padding: 12px 14px; background: var(--bg-hover); border-radius: 8px; }
    .source-label { font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; display: block; }
    .source-link { font-size: 13px; color: var(--accent); text-decoration: none; }
    .scheme-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; margin-bottom: 10px; }
    .scheme-card .scheme-name { font-size: 15px; font-weight: 600; }
    .scheme-card .scheme-category { font-size: 13px; color: var(--text-secondary); }
    .welcome-banner { text-align: center; padding: 40px 20px; }
    .welcome-banner h1 {
        font-size: 32px; font-weight: 700;
        background: linear-gradient(135deg, var(--accent), #33d9b0);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        background-clip: text; margin-bottom: 8px;
    }
    .welcome-banner p { color: var(--text-secondary); font-size: 16px; margin: 0 auto 16px; }
    .welcome-banner .pill {
        display: inline-flex; background: rgba(0,208,156,0.1);
        border: 1px solid rgba(0,208,156,0.3); padding: 8px 16px;
        border-radius: 20px; font-size: 13px; color: var(--accent);
    }
    [data-testid="stChatInput"] textarea {
        background: var(--bg-card) !important; border: 1px solid var(--border) !important;
        border-radius: 24px !important; color: var(--text-primary) !important;
        font-size: 15px !important;
    }
    [data-testid="stChatInput"] button {
        background: var(--accent) !important; color: var(--bg) !important;
        border-radius: 50% !important;
    }
    .sidebar-logo { padding: 16px 20px; border-bottom: 1px solid var(--border); }
    .sidebar-logo h2 {
        font-size: 22px; font-weight: 700;
        background: linear-gradient(135deg, var(--accent), #33d9b0);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        background-clip: text; margin: 0;
    }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
</style>
"""

SCHEME_META = [
    ("HDFC Mid Cap Opportunities Fund", "Mid Cap", "What is the expense ratio of HDFC Mid Cap Fund?"),
    ("HDFC Equity Fund", "Large & Mid Cap", "What is the exit load of HDFC Equity Fund?"),
    ("HDFC Focused Fund", "Focused / Multi Cap", "Tell me about HDFC Focused Fund"),
    ("HDFC ELSS Tax Saver Fund", "ELSS", "What is the lock-in period for HDFC ELSS Tax Saver Fund?"),
    ("HDFC Large Cap Fund", "Large Cap", "Tell me about HDFC Large Cap Fund"),
]

QUICK_QUERIES = [
    "What is NAV of HDFC Mid Cap Fund?",
    "What is expense ratio of HDFC ELSS Tax Saver Fund?",
    "Tell me about HDFC Large Cap Fund",
]


def load_manifest():
    if not MANIFEST_PATH.exists():
        return {"total_schemes": 5, "last_ingested": "N/A", "amc": "HDFC Mutual Fund", "schemes": []}
    with open(MANIFEST_PATH, "r") as f:
        m = json.load(f)
    schemes = []
    for e in m.get("corpus_urls", []):
        schemes.append({"scheme": e.get("scheme", "?"), "category": e.get("category", "?")})
    return {
        "total_schemes": m.get("total_urls", 5),
        "last_ingested": m.get("last_ingested", "N/A"),
        "amc": m.get("amc", "HDFC"),
        "schemes": schemes,
    }


def parse_answer(raw):
    src = re.search(r"Source:\s*(https?://\S+)", raw)
    dt = re.search(r"Last updated from sources:\s*(\S+)", raw)
    edu = re.search(r"For more information:\s*(https?://\S+)", raw)
    body = raw
    source_url = None
    if src:
        source_url = src.group(1)
        body = body.replace(f"Source: {source_url}", "")
    last_updated = None
    if dt:
        last_updated = dt.group(1)
        body = body.replace(f"Last updated from sources: {last_updated}", "")
    if edu and not source_url:
        source_url = edu.group(1)
        body = body.replace(f"For more information: {source_url}", "")
    return body.strip(), source_url, last_updated


def get_intent_label(intent):
    labels = {
        "factual": ("Factual Answer", "factual"),
        "advisory": ("Advisory Refusal", "advisory"),
        "comparison": ("Comparison Refusal", "advisory"),
        "prediction": ("Prediction Refusal", "advisory"),
        "pii_blocked": ("PII Blocked", "pii"),
        "dont_know": ("Not in Corpus", "dont_know"),
    }
    return labels.get(intent, (intent.replace("_", " ").title(), "factual"))


# ── Session state ────────────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.orch_hist = []
    st.session_state.conversation_started = False
if "chunks" not in st.session_state:
    st.session_state.chunks = load_chunks()


# ── Layout ───────────────────────────────────────────────────────────────────

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
manifest = load_manifest()

# Sidebar
with st.sidebar:
    st.markdown('<div class="sidebar-logo"><h2>📊 Grow RAG</h2></div>', unsafe_allow_html=True)

    if st.button("✦ New Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.orch_hist = []
        st.session_state.conversation_started = False
        st.rerun()

    st.divider()
    st.metric("Schemes Indexed", manifest["total_schemes"])
    st.caption(f"AMC: {manifest['amc']} | Last ingested: {manifest['last_ingested'][:10]}")

    st.divider()
    st.markdown("#### 💡 Example Queries")
    for name, cat, q in SCHEME_META:
        if st.button(f"💬 {q}", key=f"ex_{name[:20]}", use_container_width=True):
            st.session_state.pending = q

    st.divider()
    st.markdown("#### 📋 Indexed Schemes")
    for s in manifest.get("schemes", []):
        st.markdown(
            f'<div class="scheme-card"><div class="scheme-name">{s["scheme"]}</div>'
            f'<div class="scheme-category">{s["category"]}</div></div>',
            unsafe_allow_html=True,
        )

    st.caption("⚠️ Facts-only. No investment advice.")

# Welcome banner
if not st.session_state.conversation_started and not st.session_state.messages:
    st.markdown(
        '<div class="welcome-banner"><h1>Grow RAG</h1>'
        "<p>Query verified documents for HDFC schemes. "
        "Concise, accurate, facts-only answers.</p>"
        '<div class="pill">🛡️ No investment advice</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("#### Quick Queries")
    cols = st.columns(3)
    for col, q in zip(cols, QUICK_QUERIES):
        with col:
            if st.button(q, use_container_width=True):
                st.session_state.pending = q

# Render chat
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(f'<div class="user-message">{msg["content"]}</div>', unsafe_allow_html=True)
    else:
        d = msg["data"]
        body = d.get("answer_body", d.get("answer", ""))
        intent = d.get("intent", "factual")
        label, cls = get_intent_label(intent)

        css = "ai-message"
        if intent in ("advisory", "comparison", "prediction"):
            css += " refusal"
        if intent == "pii_blocked":
            css += " pii"

        src_html = ""
        if d.get("source_url"):
            url_short = d["source_url"].replace("https://", "")
            src_html = (
                f'<div class="source-block"><span class="source-label">Source</span>'
                f'<a class="source-link" href="{d["source_url"]}" target="_blank">🔗 {url_short}</a></div>'
            )

        date_html = f'📅 Last updated: {d["last_updated"]}' if d.get("last_updated") else ""

        st.markdown(
            f'<div class="{css}">'
            f'<div class="ai-header"><div class="ai-avatar">AI</div>'
            f'<span class="ai-label">AI Assistant</span>'
            f'<span class="intent-badge {cls}">{label}</span></div>'
            f'<div class="ai-body">{body.replace(chr(10), "<br>")}</div>'
            f"{src_html}"
            f'<div class="ai-footer">{date_html}</div></div>',
            unsafe_allow_html=True,
        )

# Handle pending query
if "pending" in st.session_state and st.session_state.pending:
    q = st.session_state.pop("pending")
    st.session_state.messages.append({"role": "user", "content": q})
    st.session_state.conversation_started = True

    raw = answer_query(q, st.session_state.chunks, st.session_state.orch_hist)
    b, s, d = parse_answer(raw)
    intent = "pii_blocked" if contains_pii(q) else classify_intent(q)

    st.session_state.messages.append(
        {
            "role": "assistant",
            "data": {"answer": raw, "answer_body": b, "source_url": s, "last_updated": d, "intent": intent},
        }
    )
    st.session_state.orch_hist.append({"role": "user", "content": q})
    st.session_state.orch_hist.append({"role": "assistant", "content": raw})
    st.rerun()

# Chat input
if prompt := st.chat_input("Ask a factual question about HDFC schemes..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.conversation_started = True

    raw = answer_query(prompt, st.session_state.chunks, st.session_state.orch_hist)
    b, s, d = parse_answer(raw)
    intent = "pii_blocked" if contains_pii(prompt) else classify_intent(prompt)

    st.session_state.messages.append(
        {
            "role": "assistant",
            "data": {"answer": raw, "answer_body": b, "source_url": s, "last_updated": d, "intent": intent},
        }
    )
    st.session_state.orch_hist.append({"role": "user", "content": prompt})
    st.session_state.orch_hist.append({"role": "assistant", "content": raw})
    st.rerun()
