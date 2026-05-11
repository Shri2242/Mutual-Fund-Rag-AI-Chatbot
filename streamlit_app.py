"""
Streamlit App — Mutual Fund FAQ Assistant
==========================================
A single-file Streamlit deployment that wraps the Phase 3 Orchestrator
(PII guard + Intent classification + Keyword retrieval + Groq/extractive generation)
into a professional chatbot UI with a dashboard, source freshness modal,
and chat history.

Usage:
    streamlit run streamlit_app.py
"""

import sys
import os
import re
import json
import hashlib
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone

import streamlit as st

# ── Ensure project root is on sys.path ────────────────────────────────────────
ROOT = Path(__file__).parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass

# ── Import the orchestrator ───────────────────────────────────────────────────
from src.phase3_reasoning.orchestrator import Orchestrator, PIIDetector, IntentClassifier
import src.phase3_reasoning.orchestrator as orch_mod

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

PAGE_TITLE = "Grow RAG — Mutual Fund FAQ Assistant"
PAGE_ICON = "📈"
LAYOUT = "wide"

MANIFEST_PATH = ROOT / "src" / "phase0_corpus_registry" / "corpus_manifest.json"
REFRESH_LOG   = ROOT / "data" / "index" / "refresh_log.jsonl"

SCHEME_META = {
    "HDFC Mid Cap Opportunities Fund": {
        "url": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
        "category": "Mid Cap",
        "slug": "hdfc-mid-cap-fund",
        "example_q": "What is the expense ratio of HDFC Mid Cap Fund?",
        "color": "#00d09c",
    },
    "HDFC Equity Fund": {
        "url": "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
        "category": "Large & Mid Cap",
        "slug": "hdfc-equity-fund",
        "example_q": "What is the exit load of HDFC Equity Fund?",
        "color": "#4781ff",
    },
    "HDFC Focused Fund": {
        "url": "https://groww.in/mutual-funds/hdfc-focused-fund-direct-growth",
        "category": "Focused / Multi Cap",
        "slug": "hdfc-focused-fund",
        "example_q": "Tell me about HDFC Focused Fund",
        "color": "#a855f7",
    },
    "HDFC ELSS Tax Saver Fund": {
        "url": "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
        "category": "ELSS",
        "slug": "hdfc-elss",
        "example_q": "What is the lock-in period for HDFC ELSS Tax Saver Fund?",
        "color": "#eb5b3c",
    },
    "HDFC Large Cap Fund": {
        "url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        "category": "Large Cap",
        "slug": "hdfc-large-cap-fund",
        "example_q": "Tell me about HDFC Large Cap Fund",
        "color": "#f59e0b",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout=LAYOUT,
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────────────────────────────────────

CUSTOM_CSS = """
<style>
    /* ── Global theme ── */
    :root {
        --bg: #121212;
        --bg-card: #1E1E1E;
        --bg-hover: #2C2C2C;
        --border: #333333;
        --text-primary: #FFFFFF;
        --text-secondary: #B3B3B3;
        --text-muted: #808080;
        --accent: #00d09c;
        --accent-light: #33d9b0;
        --red: #eb5b3c;
        --blue: #4781ff;
        --radius: 12px;
    }

    /* Override Streamlit defaults */
    .stApp {
        background: var(--bg);
        color: var(--text-primary);
    }
    
    .stAppHeader, .stAppToolbar, .st-emotion-cache-1dp5vir, .st-emotion-cache-1wrcr25 {
        background: var(--bg) !important;
    }
    
    .stSidebar {
        background: var(--bg-card) !important;
        border-right: 1px solid var(--border) !important;
    }
    
    .stSidebar .st-emotion-cache-1wmy9hl {
        background: var(--bg-card) !important;
    }

    /* Main chat container */
    .chat-container {
        max-width: 800px;
        margin: 0 auto;
        padding: 0 16px;
    }
    
    /* Message bubbles */
    .user-message {
        background: var(--bg-hover);
        color: #fff;
        padding: 12px 18px;
        border-radius: 18px 18px 4px 18px;
        margin: 8px 0 8px auto;
        max-width: 80%;
        width: fit-content;
        font-size: 15px;
        line-height: 1.5;
        border: 1px solid var(--border);
        animation: fadeIn 0.3s ease;
    }
    
    .ai-message {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 18px 20px;
        margin: 8px 0;
        animation: fadeIn 0.3s ease;
    }
    
    .ai-message.refusal {
        border-color: rgba(235,91,60,0.4);
    }
    
    .ai-message.pii {
        border-color: var(--red);
    }

    .ai-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 12px;
        padding-bottom: 10px;
        border-bottom: 1px solid var(--border);
    }
    
    .ai-avatar {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: var(--accent);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
        color: var(--bg);
        font-weight: bold;
    }
    
    .ai-label {
        font-size: 14px;
        font-weight: 600;
        color: var(--text-primary);
        flex: 1;
    }
    
    .intent-badge {
        font-size: 11px;
        font-weight: 600;
        padding: 3px 10px;
        border-radius: 4px;
    }
    
    .intent-badge.factual { background: rgba(0,208,156,0.15); color: var(--accent); }
    .intent-badge.advisory { background: rgba(235,91,60,0.15); color: var(--red); }
    .intent-badge.pii { background: rgba(239,68,68,0.1); color: var(--red); }
    .intent-badge.dont_know { background: rgba(71,129,255,0.1); color: var(--blue); }
    
    .ai-body {
        font-size: 15px;
        line-height: 1.65;
        color: var(--text-primary);
        white-space: pre-wrap;
    }
    
    .ai-footer {
        margin-top: 14px;
        padding-top: 12px;
        border-top: 1px solid var(--border);
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-items: center;
        font-size: 13px;
    }
    
    .ai-source a {
        color: var(--accent);
        text-decoration: none;
    }
    
    .ai-source a:hover { text-decoration: underline; }
    
    .ai-date {
        color: var(--text-muted);
    }

    /* Source section in messages */
    .source-block {
        margin-top: 12px;
        padding: 12px 14px;
        background: var(--bg-hover);
        border-radius: 8px;
        border: 1px solid var(--border-soft, var(--border));
    }
    
    .source-label {
        font-size: 12px;
        font-weight: 600;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 6px;
        display: block;
    }
    
    .source-link {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 13px;
        color: var(--accent);
        text-decoration: none;
        padding: 4px 0;
    }
    
    .source-footer {
        font-size: 12px;
        color: var(--accent);
        margin-top: 6px;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    
    /* Error messages */
    .error-message {
        background: var(--bg-card);
        border: 1px solid var(--red);
        border-radius: var(--radius);
        padding: 14px 18px;
        margin: 8px 0;
        color: var(--red);
        animation: fadeIn 0.3s ease;
    }
    
    .error-message .error-title {
        font-weight: 600;
        font-size: 14px;
        margin-bottom: 4px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* Dashboard cards */
    .scheme-card {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 16px;
        margin-bottom: 10px;
        cursor: pointer;
        transition: all 0.2s;
    }
    
    .scheme-card:hover {
        border-color: var(--accent);
        background: var(--bg-hover);
    }
    
    .scheme-card .scheme-name {
        font-size: 15px;
        font-weight: 600;
        margin-bottom: 6px;
    }
    
    .scheme-card .scheme-category {
        font-size: 13px;
        color: var(--text-secondary);
    }
    
    .scheme-status {
        font-size: 12px;
        color: var(--accent);
        margin-top: 6px;
    }

    /* Welcome banner */
    .welcome-banner {
        text-align: center;
        padding: 40px 20px;
    }
    
    .welcome-banner h1 {
        font-size: 32px;
        font-weight: 700;
        margin-bottom: 8px;
        background: linear-gradient(135deg, var(--accent), var(--accent-light));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    
    .welcome-banner p {
        color: var(--text-secondary);
        font-size: 16px;
        max-width: 500px;
        margin: 0 auto 16px;
    }
    
    .welcome-banner .pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: rgba(0,208,156,0.1);
        border: 1px solid rgba(0,208,156,0.3);
        padding: 8px 16px;
        border-radius: 20px;
        font-size: 13px;
        color: var(--accent);
    }

    /* Chat input styling */
    [data-testid="stChatInput"] textarea {
        background: var(--bg-card) !important;
        border: 1px solid var(--border) !important;
        border-radius: 24px !important;
        color: var(--text-primary) !important;
        font-size: 15px !important;
        padding: 12px 20px !important;
    }
    
    [data-testid="stChatInput"] textarea:focus {
        border-color: var(--accent) !important;
    }
    
    [data-testid="stChatInput"] button {
        background: var(--accent) !important;
        color: var(--bg) !important;
        border-radius: 50% !important;
        width: 40px !important;
        height: 40px !important;
    }

    /* Sidebar elements */
    .sidebar-logo {
        padding: 16px 20px;
        border-bottom: 1px solid var(--border);
        margin-bottom: 16px;
    }
    
    .sidebar-logo h2 {
        font-size: 22px;
        font-weight: 700;
        background: linear-gradient(135deg, var(--accent), var(--accent-light));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        margin: 0;
    }
    
    .sidebar-logo span {
        font-size: 12px;
        color: var(--text-secondary);
    }
    
    .example-item {
        padding: 10px 14px;
        border-radius: 8px;
        cursor: pointer;
        font-size: 13px;
        color: var(--text-secondary);
        transition: all 0.2s;
        border: 1px solid transparent;
        margin-bottom: 6px;
    }
    
    .example-item:hover {
        background: var(--bg-hover);
        border-color: var(--border);
        color: var(--text-primary);
    }
    
    /* Metrics */
    [data-testid="stMetricValue"] {
        color: var(--text-primary) !important;
    }
    
    [data-testid="stMetricLabel"] {
        color: var(--text-secondary) !important;
    }

    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    /* Divider */
    hr {
        border-color: var(--border) !important;
        margin: 16px 0 !important;
    }
</style>
"""

# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def get_intent_label(intent: str) -> dict:
    """Return (display_label, css_class) for an intent type."""
    labels = {
        "factual":      ("Factual Answer", "factual"),
        "advisory":     ("Advisory Refusal", "advisory"),
        "comparison":   ("Comparison Refusal", "advisory"),
        "prediction":   ("Prediction Refusal", "advisory"),
        "pii_blocked":  ("PII Blocked", "pii"),
        "dont_know":    ("Not in Corpus", "dont_know"),
    }
    return labels.get(intent, (intent, "factual"))


def load_manifest_meta() -> dict:
    """Load corpus manifest metadata for the sidebar/dashboard."""
    if not MANIFEST_PATH.exists():
        return {"total_schemes": 5, "last_ingested": "N/A", "corpus_version": "v1", "schemes": []}
    
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    
    schemes = []
    for entry in manifest.get("corpus_urls", []):
        schemes.append({
            "scheme": entry.get("scheme", "?"),
            "category": entry.get("category", "?"),
            "url": entry.get("url", ""),
            "status": entry.get("status", "unknown"),
            "last_updated": entry.get("last_updated_from_source", ""),
        })
    
    return {
        "total_schemes": manifest.get("total_urls", 5),
        "last_ingested": manifest.get("last_ingested", "N/A"),
        "corpus_version": manifest.get("corpus_version", "v1"),
        "amc": manifest.get("amc", "HDFC Mutual Fund"),
        "schemes": schemes,
    }


def init_orchestrator():
    """Initialize or retrieve the cached Orchestrator singleton."""
    if "orchestrator" not in st.session_state:
        st.session_state.orchestrator = Orchestrator()
    return st.session_state.orchestrator


def init_chat_history():
    """Ensure chat history exists in session state."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "orch_history" not in st.session_state:
        st.session_state.orch_history = []
    if "conversation_started" not in st.session_state:
        st.session_state.conversation_started = False


def ask_question(query: str):
    """
    Send a query to the orchestrator, render the response, and update history.
    """
    orch = init_orchestrator()
    
    # Add user message to Streamlit history
    st.session_state.messages.append({"role": "user", "content": query})
    st.session_state.conversation_started = True
    
    # Build orchestrator history (last 4 turns max)
    orch_hist = st.session_state.orch_history[-4:] if st.session_state.orch_history else []
    
    # Call orchestrator
    try:
        raw_answer = orch.ask(query, history=orch_hist)
        
        # Parse the answer
        parsed = _parse_answer(raw_answer)
        url_count = len(re.findall(r"https?://", raw_answer))
        
        # Detect intent
        is_pii = PIIDetector.contains_pii(query)
        intent = "pii_blocked" if is_pii else IntentClassifier.classify(query)
        
        response_data = {
            "answer": raw_answer,
            "answer_body": parsed["body"],
            "source_url": parsed["source_url"],
            "last_updated": parsed["last_updated"],
            "intent": intent,
            "url_count": url_count,
        }
        
        # Update orchestrator history
        st.session_state.orch_history.append({"role": "user", "content": query})
        st.session_state.orch_history.append({"role": "assistant", "content": raw_answer})
        
    except Exception as e:
        response_data = {
            "answer": f"Error: {str(e)}",
            "answer_body": f"Something went wrong: {str(e)}",
            "source_url": None,
            "last_updated": None,
            "intent": "error",
            "url_count": 0,
        }
    
    st.session_state.messages.append({"role": "assistant", "data": response_data})


def _parse_answer(raw: str) -> dict:
    """Split the orchestrator's raw reply into body, source_url, last_updated."""
    source_url = None
    last_updated = None
    body = raw

    src_match = re.search(r"Source:\s*(https?://\S+)", raw)
    if src_match:
        source_url = src_match.group(1).strip()
        body = body.replace(f"Source: {source_url}", "").strip()

    date_match = re.search(r"Last updated from sources:\s*(\S+)", raw)
    if date_match:
        last_updated = date_match.group(1).strip()
        body = body.replace(f"Last updated from sources: {last_updated}", "").strip()

    edu_match = re.search(r"For more information:\s*(https?://\S+)", raw)
    if edu_match and not source_url:
        source_url = edu_match.group(1).strip()
        body = body.replace(f"For more information: {source_url}", "").strip()

    return {"body": body.strip(), "source_url": source_url, "last_updated": last_updated}


def render_ai_message(data: dict):
    """Render an AI message using HTML with source attribution."""
    body = data.get("answer_body", data.get("answer", ""))
    source_url = data.get("source_url")
    last_updated = data.get("last_updated")
    intent = data.get("intent", "factual")
    
    label, cls = get_intent_label(intent)
    
    css_cls = "ai-message"
    if intent in ("advisory", "comparison", "prediction"):
        css_cls += " refusal"
    if intent == "pii_blocked":
        css_cls += " pii"
    
    source_html = ""
    if source_url:
        source_html = f"""
        <div class="source-block">
            <span class="source-label">Source</span>
            <a href="{source_url}" target="_blank" rel="noopener noreferrer" class="source-link">
                🔗 {source_url.replace('https://', '')}
            </a>
            <div class="source-footer">✅ Verified from official source</div>
        </div>
        """
    
    date_html = f'<span class="ai-date">📅 Last updated: {last_updated}</span>' if last_updated else ""
    
    html = f"""
    <div class="{css_cls}">
        <div class="ai-header">
            <div class="ai-avatar">AI</div>
            <span class="ai-label">AI Assistant</span>
            <span class="intent-badge {cls}">{label}</span>
        </div>
        <div class="ai-body">{body.replace(chr(10), '<br>')}</div>
        {source_html}
        <div class="ai-footer">
            {date_html}
        </div>
    </div>
    """
    
    st.markdown(html, unsafe_allow_html=True)


def render_user_message(content: str):
    """Render a user message bubble."""
    st.markdown(f'<div class="user-message">{content}</div>', unsafe_allow_html=True)


def clear_chat():
    """Clear the chat history."""
    st.session_state.messages = []
    st.session_state.orch_history = []
    st.session_state.conversation_started = False


def handle_example_click(query: str):
    """Handle clicking an example question."""
    st.session_state.pending_query = query


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # Inject custom CSS
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    
    # Initialize state
    init_chat_history()
    init_orchestrator()
    manifest_meta = load_manifest_meta()
    
    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            f"""
            <div class="sidebar-logo">
                <h2>📊 Grow RAG</h2>
                <span>Professional Finance Assistant</span>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Clear chat button
        col1, col2 = st.columns([1, 3])
        with col1:
            st.button("🗑️", help="Clear chat", on_click=clear_chat, use_container_width=True)
        with col2:
            if st.button("✦ New Chat", use_container_width=True, type="secondary"):
                clear_chat()
        
        st.divider()
        
        # Corpus Status
        st.markdown("#### 📚 Corpus Status")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Schemes", manifest_meta["total_schemes"])
        with col2:
            st.metric("AMC", "HDFC")
        
        ingested = manifest_meta.get("last_ingested", "N/A")
        if ingested != "N/A" and len(ingested) > 10:
            ingested = ingested[:10]
        st.caption(f"Last ingested: {ingested}")
        
        st.divider()
        
        # Example questions
        st.markdown("#### 💡 Example Questions")
        st.markdown('<div class="example-list">', unsafe_allow_html=True)
        
        for name, meta in SCHEME_META.items():
            if st.button(
                f"💬 {meta['example_q']}",
                key=f"ex_{meta['slug']}",
                use_container_width=True,
                type="tertiary",
            ):
                st.session_state.pending_query = meta["example_q"]
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.divider()
        
        # Schemes overview
        st.markdown("#### 📋 Indexed Schemes")
        for scheme in manifest_meta.get("schemes", []):
            st.markdown(
                f"""<div class="scheme-card">
                    <div class="scheme-name">{scheme['scheme']}</div>
                    <div class="scheme-category">{scheme['category']}</div>
                    <div class="scheme-status">✅ Indexed</div>
                </div>""",
                unsafe_allow_html=True
            )
        
        st.divider()
        st.caption("⚠️ Facts-only. No investment advice.")
    
    # ── Main Chat Area ───────────────────────────────────────────────────────
    
    # Welcome banner (shown before first message)
    if not st.session_state.conversation_started and not st.session_state.messages:
        st.markdown(
            """
            <div class="welcome-banner">
                <h1>Grow RAG</h1>
                <p>Instantly query verified documents for listed HDFC schemes. 
                I synthesize complex financial data into concise, accurate answers.</p>
                <div class="pill">🛡️ Facts-only. No investment advice.</div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Quick action chips
        st.markdown("#### Quick Queries")
        cols = st.columns(3)
        example_queries = [
            "What is the expense ratio of HDFC Mid Cap Fund?",
            "What is the exit load of HDFC Equity Fund?",
            "What is the lock-in period for HDFC ELSS Tax Saver?",
        ]
        for i, (col, q) in enumerate(zip(cols, example_queries)):
            with col:
                if st.button(q, use_container_width=True, type="secondary"):
                    st.session_state.pending_query = q
    
    # Render chat history
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.messages:
            if msg["role"] == "user":
                render_user_message(msg["content"])
            elif msg["role"] == "assistant" and "data" in msg:
                render_ai_message(msg["data"])
    
    # Handle pending query (from example button clicks)
    if "pending_query" in st.session_state and st.session_state.pending_query:
        query = st.session_state.pending_query
        st.session_state.pending_query = None
        ask_question(query)
        st.rerun()
    
    # Chat input
    st.divider()
    if prompt := st.chat_input("Ask a factual question about listed HDFC schemes...", key="chat_input"):
        ask_question(prompt)
        st.rerun()


if __name__ == "__main__":
    main()
