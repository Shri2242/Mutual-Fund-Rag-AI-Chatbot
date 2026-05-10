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
CONFIDENCE_THRESHOLD = 2   # min keyword hits to treat as a confident retrieval


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
class MockRetriever:
    """Keyword retriever standing in for ChromaDB until Windows DLL is resolved."""

    def __init__(self):
        self.chunks: list = []
        if CHUNKS_FILE.exists():
            with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self.chunks.append(json.loads(line))

    def retrieve(self, query: str):
        q_terms = query.lower().split()
        best_chunk, best_score = None, 0
        for chunk in self.chunks:
            score = sum(1 for t in q_terms if t in chunk["text"].lower())
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
        "You are a facts-only mutual fund information assistant.\n"
        "Rules:\n"
        "1. Answer ONLY from the provided context. Do NOT use prior knowledge.\n"
        "2. Answer ONLY the specific field or metric the user asked about. "
        "If the user asks for NAV, return ONLY the NAV. If they ask for expense ratio, return ONLY the expense ratio. "
        "Do NOT return all fund details. Be concise and precise.\n"
        "3. Format your response as:\n"
        "   Fund Name: <name>\n"
        "   <Requested Field>: <value>\n"
        "   (add Date/as of date if available for NAV)\n"
        "4. Do NOT include any URLs, links, or source lines — those are added by code.\n"
        "5. Do NOT provide investment advice, opinions, or return predictions.\n"
        "6. Be lenient with mutual fund name matching. If the context fund name is similar to the user's query "
        "(e.g. 'HDFC Mid Cap Fund' vs 'HDFC Mid Cap Opportunities Fund'), assume they are the same.\n"
        "7. If the context does not contain ANY relevant information to answer the question, reply ONLY with: DONT_KNOW\n"
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

    def _groq_call(self, chunk_text: str, query: str):
        try:
            resp = self._client.chat.completions.create(
                model=GROQ_MODEL,
                temperature=0.1,
                max_tokens=256,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user",   "content": f"CONTEXT:\n{chunk_text}\n\nUSER QUERY:\n{query}"}
                ]
            )
            body = resp.choices[0].message.content.strip()
            if body == "DONT_KNOW" or not body:
                return None
            return re.sub(r'https?://\S+', '', body).strip()
        except Exception as e:
            print(f"[Generator]: Groq call failed ({e}) — falling back to extractive.")
            return None

    def generate(self, chunk: dict, query: str = ""):
        """Returns (body, source_url, fetch_date). body='' signals don't-know."""
        text       = chunk["text"]
        source_url = chunk["metadata"].get("source_url", "")
        fetch_date = chunk["metadata"].get("fetch_date", "N/A")

        if self.use_groq and self._client:
            body = self._groq_call(text, query)
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

    def ask(self, query: str) -> str:
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

        # 3. Retrieval with confidence gate
        chunk, score = self.retriever.retrieve(query)
        print(f"[System]: Retrieval score -> {score}")
        if not chunk or score < CONFIDENCE_THRESHOLD:
            print("[System]: Low confidence -> dont_know (0 URLs)")
            return PostProcessor.process("", "", "", "dont_know")

        # 4. Generation (Groq or extractive)
        body, url, date = self.generator.generate(chunk, query)
        if not body:
            return PostProcessor.process("", "", "", "dont_know")

        # 5. Post-Process + URL policy enforcement
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
