"""
run_scheduler.py -- Local Scheduler Test Runner
================================================
Run this script from the project root to simulate a full pipeline
refresh locally, exactly as GitHub Actions would run it.

Usage:
    python run_scheduler.py              # Normal run
    python run_scheduler.py --force      # Force-run (bypass freeze logic)
    python run_scheduler.py --dry-run    # Validate imports only, no network calls

Exit Codes:
    0  — Pipeline completed with outcome: ok or partial
    1  — Pipeline failed (hard error)
    2  — Pipeline frozen (drift across ≥2 URLs detected, index not overwritten)
"""

import sys
import io
import argparse
import time

# Force UTF-8 output on Windows to avoid cp1252 UnicodeEncodeError
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from pathlib import Path
from datetime import datetime, timezone

# ── Ensure project root is on sys.path ────────────────────────────────────────
ROOT = Path(__file__).parent.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _banner(title: str, width: int = 60) -> None:
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def _section(msg: str) -> None:
    print(f"\n{'=' * 50}")
    print(f"  {msg}")
    print('=' * 50)


def check_env():
    """Validate required environment variables are loadable."""
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        print("[OK] .env loaded successfully")
    except ImportError:
        print("[!] python-dotenv not installed -- skipping .env load")

    import os
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key and groq_key.startswith("gsk_"):
        print(f"[OK] GROQ_API_KEY found: {groq_key[:12]}***")
    else:
        print("[!] GROQ_API_KEY not set or invalid - extractive-only mode will be used")


def check_imports():
    """Verify all critical dependencies can be imported."""
    _section("Dependency Check")
    deps = [
        ("requests",             "HTTP fetching"),
        ("bs4",                  "HTML parsing (BeautifulSoup4)"),
        ("rank_bm25",            "BM25 sparse index"),
        ("dotenv",               "Environment loading"),
    ]
    optional_deps = [
        ("playwright.sync_api",  "Headless browser (Playwright)"),
        ("chromadb",             "ChromaDB vector store"),
        ("sentence_transformers","Sentence embeddings"),
        ("groq",                 "Groq LLM API client"),
        ("fastapi",              "FastAPI web server"),
    ]

    all_ok = True
    for module, label in deps:
        try:
            __import__(module)
            print(f"  [OK] {label} ({module})")
        except ImportError:
            print(f"  [MISSING] {label} ({module})")
            all_ok = False

    print("\n  Optional dependencies:")
    for module, label in optional_deps:
        try:
            __import__(module)
            print(f"  [OK] {label} ({module})")
        except (ImportError, OSError, Exception) as exc:
            # OSError/Exception catches Windows DLL load failures (torch, etc.)
            reason = "DLL/OS error" if isinstance(exc, OSError) else "not installed"
            print(f"  [SKIP] {reason}: {label} ({module}) - some features disabled")

    return all_ok


def check_manifest():
    """Validate corpus_manifest.json exists and has the expected 5 URLs."""
    _section("Manifest Validation")
    import json
    manifest_path = ROOT / "src" / "phase0_corpus_registry" / "corpus_manifest.json"

    if not manifest_path.exists():
        print(f"  [!] corpus_manifest.json NOT FOUND at {manifest_path}")
        return False

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    urls = manifest.get("corpus_urls", [])
    print(f"  [OK] Manifest found - corpus_version: {manifest.get('corpus_version')}")
    print(f"  [OK] Total URLs in manifest: {len(urls)} (expected: 5)")

    for entry in urls:
        status = entry.get("status", "unknown")
        scheme  = entry.get("scheme", "?")
        status_icon = "OK" if status not in ("soft_404", "failed") else "!"
        print(f"    [{status_icon}] {scheme}: status={status}")

    return len(urls) == 5


def check_data_index():
    """Check the data/index directory and log its contents."""
    _section("Data Index Status")
    index_dir = ROOT / "data" / "index"
    if not index_dir.exists():
        print(f"  [!] data/index/ does not exist yet — will be created by pipeline")
        return

    files = list(index_dir.rglob("*"))
    print(f"  [OK] data/index/ exists with {len(files)} items:")
    for f in sorted(files)[:20]:
        rel = f.relative_to(index_dir)
        size = f.stat().st_size if f.is_file() else "-"
        print(f"      {rel}  ({size} bytes)" if f.is_file() else f"      {rel}/")

    # Show refresh log tail
    refresh_log = index_dir / "refresh_log.jsonl"
    if refresh_log.exists():
        import json
        lines = refresh_log.read_text(encoding="utf-8").strip().splitlines()
        print(f"\n  Last {min(3, len(lines))} pipeline run(s):")
        for line in lines[-3:]:
            try:
                entry = json.loads(line)
                print(f"    • {entry.get('timestamp')} | outcome={entry.get('outcome')} | "
                      f"drift={entry.get('drift_count')} | soft404={entry.get('soft_404_count')} | "
                      f"duration={entry.get('duration_seconds')}s")
            except Exception:
                print(f"    • {line}")


def run_pipeline(force: bool = False) -> int:
    """Import and invoke Pipeline.refresh(). Returns exit code."""
    _section("Running Pipeline.refresh()")
    print(f"  Timestamp (UTC): {datetime.now(timezone.utc).isoformat()}")
    print(f"  Force mode: {force}")
    print()

    try:
        from src.phase1_data_collection.pipeline import Pipeline
    except ImportError as e:
        print(f"  [ERROR] Could not import Pipeline: {e}")
        print("  Make sure you are running from the project root directory.")
        return 1

    start = time.perf_counter()
    try:
        Pipeline.refresh(force=force)
        elapsed = time.perf_counter() - start
        print(f"  [OK] Pipeline.refresh() completed in {elapsed:.1f}s")
        return 0
    except SystemExit as e:
        elapsed = time.perf_counter() - start
        code = e.code if isinstance(e.code, int) else 1
        print(f"\n  [!] Pipeline exited with code {code} after {elapsed:.1f}s")
        return code
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"\n  [ERROR] Unexpected error after {elapsed:.1f}s: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Local scheduler test runner for the Mutual Fund data pipeline"
    )
    parser.add_argument("--force",   action="store_true",
                        help="Bypass drift-freeze logic (same as Pipeline.refresh(force=True))")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run pre-flight checks only; do not execute the pipeline")
    args = parser.parse_args()

    _banner("Mutual Fund Pipeline — Local Scheduler Test")
    print(f"  Mode:      {'DRY RUN' if args.dry_run else ('FORCE' if args.force else 'NORMAL')}")
    print(f"  Root dir:  {ROOT}")

    # ── Pre-flight checks ──────────────────────────────────────────────────────
    _section("Pre-flight Checks")
    check_env()

    imports_ok = check_imports()
    manifest_ok = check_manifest()
    check_data_index()

    if not imports_ok:
        print("\n[FAIL] Some required dependencies are missing.")
        print("    Run:  pip install -r requirements.txt")
        sys.exit(1)

    if not manifest_ok:
        print("\n[FAIL] Manifest validation failed - cannot run pipeline.")
        sys.exit(1)

    if args.dry_run:
        _banner("DRY RUN COMPLETE — No pipeline executed")
        print("  All pre-flight checks passed. Run without --dry-run to execute.")
        sys.exit(0)

    # ── Execute Pipeline ───────────────────────────────────────────────────────
    exit_code = run_pipeline(force=args.force)

    # ── Post-run status ────────────────────────────────────────────────────────
    check_data_index()

    _banner("Scheduler Run Complete")
    if exit_code == 0:
        print("  Result: SUCCESS")
    elif exit_code == 2:
        print("  Result: FROZEN (drift across >=2 URLs - index not overwritten)")
    else:
        print(f"  Result: FAILED (exit code {exit_code})")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
