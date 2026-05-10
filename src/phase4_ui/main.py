"""
Phase 4 — FastAPI Backend
=========================
Endpoints:
  POST /ask      — Submit a query, returns compliant answer + metadata
  GET  /meta     — Source freshness metadata for all 5 schemes
  GET  /health   — Liveness check

No login, no cookies beyond session, no analytics that capture raw query text.
Structured logs written per-request (PII-free, queries are hashed).
"""

import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env", override=False)
except ImportError:
    pass

# ── Internal imports ──────────────────────────────────────────────────────────
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.phase3_reasoning.orchestrator import Orchestrator, PIIDetector

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent.parent.parent
MANIFEST_PATH = BASE_DIR / "src" / "phase0_corpus_registry" / "corpus_manifest.json"
REFRESH_LOG   = BASE_DIR / "data" / "index" / "refresh_log.jsonl"
STATIC_DIR    = BASE_DIR / "src" / "phase4_ui" / "static"
LOG_DIR       = BASE_DIR / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
ACCESS_LOG    = LOG_DIR / "access_log.jsonl"

# ── Boot the Orchestrator (singleton) ─────────────────────────────────────────
_orchestrator = Orchestrator()   # use_groq=None (auto: Groq if key set)

# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Mutual Fund FAQ Assistant",
    description="Facts-only. No investment advice.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # lock down in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Pydantic Models ───────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    query: str
    history: list[dict] = []   # list of {"role": "user"|"assistant", "content": "..."}

class AskResponse(BaseModel):
    request_id: str
    answer: str
    answer_body: str
    source_url: str | None
    last_updated: str | None
    intent: str
    post_check_passed: bool
    latency_ms: int

# ── Helpers ───────────────────────────────────────────────────────────────────
def _parse_answer(raw: str) -> dict:
    """Split the orchestrator's raw reply into body, source_url, last_updated."""
    source_url   = None
    last_updated = None
    body         = raw

    # Extract Source line
    src_match = re.search(r"Source:\s*(https?://\S+)", raw)
    if src_match:
        source_url = src_match.group(1).strip()
        body = body.replace(f"Source: {source_url}", "").strip()

    # Extract Last updated line
    date_match = re.search(r"Last updated from sources:\s*(\S+)", raw)
    if date_match:
        last_updated = date_match.group(1).strip()
        body = body.replace(f"Last updated from sources: {last_updated}", "").strip()

    # Also handle educational link (refusal path)
    edu_match = re.search(r"For more information:\s*(https?://\S+)", raw)
    if edu_match and not source_url:
        source_url = edu_match.group(1).strip()
        body = body.replace(f"For more information: {source_url}", "").strip()

    return {
        "body":         body.strip(),
        "source_url":   source_url,
        "last_updated": last_updated,
    }


def _write_log(entry: dict):
    """Append a structured log entry (no raw query text — only hash)."""
    with open(ACCESS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
def health():
    """Liveness check — returns 200 if the server is up."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
    }


@app.get("/meta", tags=["ops"])
def meta():
    """
    Source freshness metadata for all 5 schemes.
    Returns corpus_version, last_ingested, and per-scheme freshness dates.
    """
    if not MANIFEST_PATH.exists():
        raise HTTPException(status_code=503, detail="Corpus manifest not found.")

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Attach last refresh outcome from refresh_log.jsonl
    last_run_outcome = None
    last_run_ts      = None
    if REFRESH_LOG.exists():
        with open(REFRESH_LOG, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        if lines:
            last_run = json.loads(lines[-1])
            last_run_outcome = last_run.get("outcome")
            last_run_ts      = last_run.get("timestamp")

    schemes = []
    for entry in manifest.get("corpus_urls", []):
        schemes.append({
            "scheme":             entry.get("scheme"),
            "category":           entry.get("category"),
            "url":                entry.get("url"),
            "last_updated_from_source": entry.get("last_updated_from_source"),
            "status":             entry.get("status"),
        })

    return {
        "corpus_version":   manifest.get("corpus_version"),
        "amc":              manifest.get("amc"),
        "total_schemes":    manifest.get("total_urls"),
        "last_ingested":    manifest.get("last_ingested"),
        "last_run_outcome": last_run_outcome,
        "last_run_ts":      last_run_ts,
        "schemes":          schemes,
    }


@app.post("/ask", response_model=AskResponse, tags=["assistant"])
async def ask(body: AskRequest, request: Request):
    """
    Submit a user query. Returns a compliant answer with URL policy enforced:
    - PII detected   -> 0 URLs, no answer
    - Don't know     -> 0 URLs
    - Advisory       -> 1 educational Groww URL
    - Factual        -> 1 whitelisted source URL + Last updated date
    """
    start_ms = time.time()
    request_id = str(uuid.uuid4())

    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    # Detect intent before calling orchestrator (for structured log)
    from src.phase3_reasoning.orchestrator import IntentClassifier, PIIDetector
    is_pii = PIIDetector.contains_pii(query)
    intent = "pii_blocked" if is_pii else IntentClassifier.classify(query)

    # Call Phase 3 Orchestrator with history
    raw_answer = _orchestrator.ask(query, history=body.history)

    # Parse structured parts
    parsed     = _parse_answer(raw_answer)
    url_count  = len(re.findall(r"https?://", raw_answer))

    # Post-check: PII and don't-know replies must have 0 URLs
    post_check = True
    if is_pii and url_count > 0:
        post_check = False
    elif intent == "factual" and url_count != 1:
        post_check = False

    latency_ms = int((time.time() - start_ms) * 1000)

    # Structured log — raw query is hashed, never stored as-is
    log_entry = {
        "request_id":       request_id,
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "query_hash":       hashlib.sha256(query.encode()).hexdigest()[:16],
        "intent":           intent,
        "source_url":       parsed["source_url"],
        "url_count":        url_count,
        "post_check_passed": post_check,
        "latency_ms":       latency_ms,
    }
    _write_log(log_entry)

    return AskResponse(
        request_id      = request_id,
        answer          = raw_answer,
        answer_body     = parsed["body"],
        source_url      = parsed["source_url"],
        last_updated    = parsed["last_updated"],
        intent          = intent,
        post_check_passed = post_check,
        latency_ms      = latency_ms,
    )


# ── Serve static SPA at / ─────────────────────────────────────────────────────
# Frontend files go in src/phase4_ui/static/
# We only mount if the folder exists so the API is usable without the frontend
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
