"""
Phase 3 — Reasoning & Guardrails (Orchestrator)
===============================================
Turns a query + retrieved chunks into a compliant answer, enforcing URL policies.

LLM: Groq (via openai-compatible API) — auto-enabled when GROQ_API_KEY is set.
     Falls back to extractive synthesis if key is absent or Groq call fails.

Usage:
    python -m src.phase3_reasoning.orchestrator
    GROQ_API_KEY=your_key python -m src.phase3_reasoning.orchestrator
"""

import re
import os
import json
from pathlib import Path

# Load .env automatically (python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env", override=False)
except ImportError:
    pass  # dotenv not installed; rely on system env vars

BASE_DIR = Path(__file__).parent.parent.parent
CHUNKS_FILE = BASE_DIR / "src" / "phase2_chunking" / "output" / "chunks.jsonl"

# Whitelist — only these URLs may appear in any reply
ALLOWED_URLS = [
    "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-focused-fund-direct-growth",
    "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
    "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
]

# Canned response templates
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

# Banned advisory tokens (post-check)
BANNED_TOKENS = [
    "recommend", "should invest", "better than",
    "will outperform", "guaranteed", "best fund"
]

GROQ_MODEL         = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_TEMPERATURE   = float(os.environ.get("GROQ_TEMPERATURE", "0.1"))
GROQ_MAX_TOKENS    = int(os.environ.get("GROQ_MAX_TOKENS", "512"))
CONFIDENCE_THRESHOLD = 1   # min keyword hits to treat as a confident retrieval


# ── PII Detector ──────────────────────────────────────────────────────────────
class PIIDetector:
    _patterns = [
        r'[A-Z]{5}[0-9]{4}[A-Z]{1}',                           # PAN
        r'\b\d{4}\s?\d{4}\s?\d{4}\b',                           # Aadhaar
        r'\b[6-9]\d{9}\b',                                       # Indian mobile
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b' # Email
    ]

    @classmethod
    def contains_pii(cls, text: str) -> bool:
        return any(re.search(p, text) for p in cls._patterns)


# ── Intent Classifier ─────────────────────────────────────────────────────────
class IntentClassifier:
    _advisory   = ["should i", "recommend", "better", "invest in", "good investment", "which fund"]
    _prediction = ["will it", "future return", "forecast", "grow", "expected return"]
    _comparison = [" vs ", "compare", "difference between", "which is better"]

    @classmethod
    def classify(cls, query: str) -> str:
        q = query.lower()
        if any(kw in q for kw in cls._advisory):   return "advisory"
        if any(kw in q for kw in cls._prediction):  return "prediction"
        if any(kw in q for kw in cls._comparison):  return "comparison"
        return "factual"


# ── Mock BM25-style Retriever ─────────────────────────────────────────────────
# Alias map: user-facing names -> URL slug keywords (to fix Groww naming mismatches)
# e.g. Groww stores 'hdfc-equity-fund' URL but scheme name is 'HDFC Flexi Cap'
FUND_ALIAS_MAP = {
    # slug keywords          -> canonical search tokens to inject
    "hdfc-equity-fund":      ["equity", "flexi", "flexicap", "flexi cap"],
    "hdfc-mid-cap-fund":     ["mid cap", "midcap", "mid-cap", "opportunities"],
    "hdfc-focused-fund":     ["focused"],
    "hdfc-elss":             ["elss", "tax saver", "tax-saver", "lock"],
    "hdfc-large-cap-fund":   ["large cap", "largecap", "large-cap"],
}

# Reverse alias: user query words -> which chunk to prefer
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

class MockRetriever:
    """Keyword retriever with alias resolution for Groww fund name mismatches."""

    def __init__(self):
        self.chunks: list = []
        if CHUNKS_FILE.exists():
            with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self.chunks.append(json.loads(line))

    def _get_searchable(self, chunk: dict) -> str:
        """Build a rich searchable string including chunk_id slug and metadata."""
        slug = chunk.get("chunk_id", "").replace("-", " ").replace("_", " ")
        scheme = chunk.get("metadata", {}).get("scheme", "")
        text = chunk.get("text", "")
        # Inject aliases for this chunk's slug
        alias_tokens = ""
        for slug_key, tokens in FUND_ALIAS_MAP.items():
            if slug_key in chunk.get("chunk_id", ""):
                alias_tokens = " ".join(tokens)
                break
        return f"{slug} {scheme} {alias_tokens} {text}".lower()

    def retrieve(self, query: str):
        q_lower = query.lower()
        q_terms = q_lower.split()

        # 1. Alias shortcut: check multi-word phrases first (longest match wins)
        for phrase in sorted(QUERY_ALIAS_MAP.keys(), key=len, reverse=True):
            if phrase in q_lower:
                target_id = QUERY_ALIAS_MAP[phrase]
                for chunk in self.chunks:
                    if chunk.get("chunk_id") == target_id:
                        # Score normally but guarantee minimum 3 for alias hit
                        score = max(3, sum(1 for t in q_terms if t in self._get_searchable(chunk)))
                        print(f"[Retriever]: Alias match '{phrase}' -> {target_id} (score={score})")
                        return chunk, score

        # 2. Normal keyword scoring over enriched searchable text
        best_chunk, best_score = None, 0
        for chunk in self.chunks:
            searchable = self._get_searchable(chunk)
            score = sum(1 for t in q_terms if t in searchable)
            if score > best_score:
                best_score, best_chunk = score, chunk
        return best_chunk, best_score


# ── Groq Generator ────────────────────────────────────────────────────────────
class Generator:
    """
    use_groq=None  -> auto: use Groq when GROQ_API_KEY is in env (default)
    use_groq=True  -> force Groq
    use_groq=False -> extractive-only regardless of env
    """

    SYSTEM_PROMPT = (
        "You are a professional, facts-only mutual fund information assistant.\n"
        "Rules:\n"
        "1. Answer ONLY from the provided context. Do NOT use prior knowledge.\n"
        "2. CONCISE MODE: If the user asks for a specific metric (NAV, Expense Ratio, Exit Load, etc.), return ONLY a focused response in this format:\n"
        "   Fund: <fund_name>\n"
        "   <Metric>: <value>\n"
        "   Date: <as_of_date>\n"
        "   (No other text, no explanations, no 'Here is the information')\n"
        "3. If the user asks a general question, provide a brief summary from context.\n"
        "4. HISTORY: Use the provided chat history to resolve pronouns (like 'it', 'its', 'the fund').\n"
        "5. Do NOT include any URLs or links.\n"
        "6. Do NOT provide investment advice.\n"
        "7. If the context is insufficient, reply ONLY with: DONT_KNOW\n"
    )

    def __init__(self, use_groq=None):
        self.groq_key = os.environ.get("GROQ_API_KEY")
        self.use_groq = bool(self.groq_key) if use_groq is None else use_groq
        self._client = None

        if self.use_groq and self.groq_key:
            try:
                from groq import Groq
                self._client = Groq(api_key=self.groq_key)
                print(f"[Generator]: Groq enabled — model: {GROQ_MODEL}")
            except ImportError:
                print("[Generator]: groq package not installed — falling back to extractive. Run: pip install groq")
                self.use_groq = False
        else:
            print("[Generator]: Extractive mode (set GROQ_API_KEY to enable Groq LLM).")

    # Maps query keywords -> sentence fragment that contains the answer
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

    def _find_relevant_sentences(self, text: str, query: str) -> str:
        text = re.sub(r'https?://\S+', '', text).strip()
        q_lower = query.lower()
        
        matched_fragments = []
        for keywords, fragment in self.FIELD_MAP:
            if any(kw in q_lower for kw in keywords):
                matched_fragments.append(fragment.lower())
                
        if not matched_fragments:
            return text

        sentences = text.split(". ")
        relevant_sentences = []
        if sentences:
            relevant_sentences.append(sentences[0])
            
        for sentence in sentences[1:]:
            s_lower = sentence.lower()
            if any(frag in s_lower for frag in matched_fragments):
                relevant_sentences.append(sentence)
                
        return ". ".join(relevant_sentences) + ("." if not relevant_sentences[-1].endswith(".") else "")

    def _extractive(self, text: str, query: str = "") -> str:
        return self._find_relevant_sentences(text, query)

    def _groq_call(self, chunk_text: str, query: str, history: list = None):
        hist_text = ""
        if history:
            hist_text = "RECENT HISTORY:\n" + "\n".join([f"{h['role'].upper()}: {h['content']}" for h in history[-2:]])

        try:
            resp = self._client.chat.completions.create(
                model=GROQ_MODEL,
                temperature=0.0,
                max_tokens=256,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user",   "content": f"{hist_text}\n\nCONTEXT:\n{chunk_text}\n\nUSER QUERY:\n{query}"}
                ]
            )
            body = resp.choices[0].message.content.strip()
            if "DONT_KNOW" in body or not body:
                return None
            return re.sub(r'https?://\S+', '', body).strip()
        except Exception as e:
            print(f"[Generator]: Groq call failed ({e}) — falling back to extractive.")
            return None

    def generate(self, chunk: dict, query: str = "", history: list = None):
        """Returns (body, source_url, fetch_date). body='' signals don't-know."""
        text       = chunk["text"]
        source_url = chunk["metadata"].get("source_url", "")
        fetch_date = chunk["metadata"].get("fetch_date", "N/A")

        if self.use_groq and self._client:
            body = self._groq_call(text, query, history)
            if body is None:
                return "", source_url, fetch_date   # signals dont_know
        else:
            body = self._extractive(text, query)

        return body, source_url, fetch_date


# ── Post Processor ────────────────────────────────────────────────────────────
class PostProcessor:

    @staticmethod
    def _url_count(text: str) -> int:
        return len(re.findall(r'https?://', text))

    @classmethod
    def process(cls, body: str, url: str, fetch_date: str, path: str) -> str:

        if path in ("pii", "dont_know"):
            # Zero URLs — hard rule
            return PII_BLOCK if path == "pii" else DONT_KNOW

        if path == "refusal":
            # At most one whitelisted URL
            safe_url = url if url in ALLOWED_URLS else ALLOWED_URLS[0]
            clean_body = re.sub(r'https?://\S+', '', body).strip()
            return f"{clean_body}\n\nFor more information: {safe_url}"

        if path == "factual":
            # Defensive PII scan
            if PIIDetector.contains_pii(body):
                return SAFE_TEMPLATE
            # Banned token check
            if any(b in body.lower() for b in BANNED_TOKENS):
                return SAFE_TEMPLATE
            # Removed the 3-sentence cap here so the whole data can be served.
            # URL whitelist check
            if url not in ALLOWED_URLS:
                return SAFE_TEMPLATE

            draft = f"{body}\n\nSource: {url}\nLast updated from sources: {fetch_date}"

            # Exactly one URL in the response
            if cls._url_count(draft) != 1:
                return SAFE_TEMPLATE

            return draft

        return SAFE_TEMPLATE


# ── Master Orchestrator ───────────────────────────────────────────────────────
class Orchestrator:
    def __init__(self, use_groq=None):
        self.retriever = MockRetriever()
        self.generator = Generator(use_groq=use_groq)
        self.default_url = (
            self.retriever.chunks[0]["metadata"]["source_url"]
            if self.retriever.chunks else ALLOWED_URLS[0]
        )

    def ask(self, query: str, history: list = None) -> str:
        print(f"\n[User]: {query}")

        # 1. PII Guard — zero URLs on block
        if PIIDetector.contains_pii(query):
            print("[System]: PII Block -> 0 URLs")
            return PostProcessor.process("", "", "", "pii")

        # 2. Intent Classification
        intent = IntentClassifier.classify(query)
        print(f"[System]: Intent -> {intent}")

        if intent != "factual":
            chunk, _ = self.retriever.retrieve(query)
            ref_url = chunk["metadata"]["source_url"] if chunk else self.default_url
            return PostProcessor.process(REFUSAL, ref_url, "", "refusal")

        # 3. Enhanced Retrieval (Check if query needs history resolution)
        processed_query = query
        if history and any(kw in query.lower() for kw in ["it", "its", "that fund", "this fund", "the fund"]):
            # Find the last fund mentioned in history
            for turn in reversed(history):
                if turn["role"] == "assistant" and "Fund:" in turn["content"]:
                    last_fund = turn["content"].split("Fund:")[1].split("\n")[0].strip()
                    processed_query = f"{query} ({last_fund})"
                    print(f"[System]: History resolution -> {processed_query}")
                    break

        # 4. Retrieval with confidence gate
        chunk, score = self.retriever.retrieve(processed_query)
        print(f"[System]: Retrieval score -> {score}")
        
        # If low confidence on processed query, try again with original if different
        if score < CONFIDENCE_THRESHOLD and processed_query != query:
            chunk2, score2 = self.retriever.retrieve(query)
            if score2 > score:
                chunk, score = chunk2, score2

        if not chunk or score < CONFIDENCE_THRESHOLD:
            print("[System]: Low confidence -> dont_know (0 URLs)")
            return PostProcessor.process("", "", "", "dont_know")

        # 5. Generation (Groq or extractive)
        body, url, date = self.generator.generate(chunk, query, history)
        if not body:
            return PostProcessor.process("", "", "", "dont_know")

        # 6. Post-Process + URL policy enforcement
        return PostProcessor.process(body, url, date, "factual")


# ── CLI Test Run ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    groq_status = f"Groq ({GROQ_MODEL})" if os.environ.get("GROQ_API_KEY") else "Extractive (set GROQ_API_KEY to enable Groq)"
    print("=" * 60)
    print("  Phase 3 — Orchestrator Test Run")
    print(f"  LLM: {groq_status}")
    print("=" * 60)

    orch = Orchestrator()

    test_cases = [
        ("PII block -> 0 URLs",     "What is my PAN ABCDE1234F status?"),
        ("Unknown -> 0 URLs",        "What is the capital of France?"),
        ("Advisory -> 1 URL",        "Should I invest in HDFC Mid Cap?"),
        ("Factual -> 1 URL",         "What is the exit load for HDFC Mid Cap Fund?"),
        ("Factual -> 1 URL",         "What is the expense ratio of HDFC ELSS Tax Saver Fund?"),
    ]

    for label, query in test_cases:
        print(f"\n{'-'*50}\n[Test]: {label}")
        ans = orch.ask(query)
        url_count = len(re.findall(r'https?://', ans))
        print(f"[Assistant]:\n{ans}")
        print(f"[Post-check]: URLs in response = {url_count}")

    print("\n" + "=" * 60)
    print("  Orchestrator Run Complete")
    print("=" * 60)
