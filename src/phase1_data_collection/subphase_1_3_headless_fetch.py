"""
Subphase 1.3 — Headless Browser Fetch (Playwright Fallback)
===========================================================
Goal: For pages where static fetch yields insufficient content (JS-rendered SPAs),
use Playwright to fully render the page before extracting HTML.

Trigger: Only activated when Subphase 1.2 returns content < 2,000 chars
         or missing key fund data fields.

Usage:
    python -m src.phase1_data_collection.subphase_1_3_headless_fetch

    This module can be run standalone (fetches all 5 URLs via headless)
    or called programmatically from the pipeline for specific URLs
    that Subphase 1.2 escalated.
"""

import json
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from pathlib import Path

# ─── Constants ────────────────────────────────────────────────────────────────

MANIFEST_PATH = Path(__file__).parent.parent / "phase0_corpus_registry" / "corpus_manifest.json"
RAW_HTML_DIR = Path(__file__).parent / "raw_html"
ALLOWED_DOMAIN = "groww.in"
MIN_CONTENT_LENGTH = 2000
NAVIGATION_TIMEOUT = 60_000       # 60 seconds for page navigation
NETWORK_IDLE_TIMEOUT = 30_000     # 30 seconds for network idle wait
MAX_RETRIES = 3
BASE_BACKOFF = 3                  # seconds

# Key CSS selectors that indicate the page data has fully loaded
# These are fund-data elements on Groww mutual fund pages
KEY_DATA_SELECTORS = [
    "[class*='fundHeader']",           # Fund name/header area
    "[class*='schemeTable']",          # Scheme info table
    "[class*='navValue']",             # NAV display
    "[class*='contentPrimary']",       # Primary content blocks
    "table",                           # Any data table
]


# ─── Fetch Result Container ──────────────────────────────────────────────────

class HeadlessFetchResult:
    """Container for a single URL's headless browser fetch result."""

    def __init__(self, url: str, scheme: str, entry_id: int):
        self.url = url
        self.scheme = scheme
        self.entry_id = entry_id
        self.content_length: int = 0
        self.raw_html: str = ""
        self.fetch_method: str = "headless"
        self.render_time_ms: float = 0
        self.error: str | None = None
        self.key_fields_found: list[str] = []
        self.fetch_timestamp: str | None = None

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "scheme": self.scheme,
            "url": self.url,
            "content_length": self.content_length,
            "fetch_method": self.fetch_method,
            "render_time_ms": self.render_time_ms,
            "key_fields_found": self.key_fields_found,
            "error": self.error,
            "fetch_timestamp": self.fetch_timestamp,
        }

    @property
    def success(self) -> bool:
        return (
            self.content_length >= MIN_CONTENT_LENGTH
            and self.error is None
        )


# ─── Playwright Availability Check ───────────────────────────────────────────

def check_playwright_installed() -> bool:
    """Check if Playwright is installed and browsers are available."""
    try:
        from playwright.sync_api import sync_playwright
        return True
    except ImportError:
        return False


def install_playwright_browsers():
    """Attempt to install Playwright Chromium browser."""
    import subprocess
    print("[*] Installing Playwright Chromium browser...")
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            capture_output=True,
            text=True,
        )
        print("[✓] Playwright Chromium installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[✗] Failed to install Playwright browsers: {e.stderr}")
        return False


# ─── Core Headless Fetch ─────────────────────────────────────────────────────

def fetch_url_headless(
    url: str,
    scheme: str,
    entry_id: int,
    playwright_context=None,
) -> HeadlessFetchResult:
    """
    Fetch a single URL using a headless Chromium browser.

    If a playwright browser context is provided, reuses it.
    Otherwise, creates a temporary one (slower for batch calls).
    """
    result = HeadlessFetchResult(url=url, scheme=scheme, entry_id=entry_id)
    result.fetch_timestamp = datetime.now(timezone.utc).isoformat()

    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

    owns_context = playwright_context is None

    for attempt in range(1, MAX_RETRIES + 1):
        pw = None
        browser = None
        try:
            print(f"    [Attempt {attempt}/{MAX_RETRIES}] Headless GET {url}")
            start_time = time.time()

            if owns_context:
                pw = sync_playwright().start()
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1920, "height": 1080},
                    java_script_enabled=True,
                )
            else:
                context = playwright_context

            page = context.new_page()

            # ── Navigate and wait for network idle ──
            try:
                page.goto(url, wait_until="networkidle", timeout=NAVIGATION_TIMEOUT)
            except PlaywrightTimeout:
                # If networkidle times out, try with domcontentloaded
                print(f"    ⚠ networkidle timeout, falling back to domcontentloaded...")
                page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)
                # Give extra time for JS rendering
                page.wait_for_timeout(5000)

            # ── Redirect safety: verify domain ──
            current_url = page.url
            current_domain = urlparse(current_url).netloc.lower().replace("www.", "")
            if current_domain != ALLOWED_DOMAIN:
                result.error = (
                    f"Redirected to external domain '{current_domain}'. "
                    f"Only '{ALLOWED_DOMAIN}' is permitted."
                )
                print(f"    ✗ {result.error}")
                page.close()
                return result

            # ── Wait for key content selectors ──
            _wait_for_key_selectors(page, result)

            # ── Scroll to load lazy content ──
            _scroll_full_page(page)

            # ── Extract rendered HTML ──
            result.raw_html = page.content()
            result.content_length = len(result.raw_html)
            result.render_time_ms = round((time.time() - start_time) * 1000, 1)

            page.close()

            # ── Content length validation ──
            if result.content_length < MIN_CONTENT_LENGTH:
                result.error = (
                    f"Even headless fetch returned short content "
                    f"({result.content_length} chars). "
                    "Page may be blocked or broken."
                )
                if attempt < MAX_RETRIES:
                    backoff = BASE_BACKOFF ** attempt
                    print(f"    ⚠ {result.error} Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                print(f"    ✗ {result.error} All retries exhausted.")
                return result

            print(
                f"    ✓ Headless fetch OK — "
                f"{result.content_length:,} chars, "
                f"rendered in {result.render_time_ms:.0f}ms"
            )
            return result

        except PlaywrightTimeout:
            result.error = f"Page navigation timed out after {NAVIGATION_TIMEOUT / 1000}s."
            if attempt < MAX_RETRIES:
                backoff = BASE_BACKOFF ** attempt
                print(f"    ✗ Timeout. Retrying in {backoff}s...")
                time.sleep(backoff)
            else:
                print(f"    ✗ {result.error} All retries exhausted.")

        except Exception as e:
            result.error = f"Playwright error: {type(e).__name__}: {e}"
            if attempt < MAX_RETRIES:
                backoff = BASE_BACKOFF ** attempt
                print(f"    ✗ {result.error} Retrying in {backoff}s...")
                time.sleep(backoff)
            else:
                print(f"    ✗ {result.error} All retries exhausted.")

        finally:
            if owns_context and browser:
                browser.close()
            if owns_context and pw:
                pw.stop()

    return result


def _wait_for_key_selectors(page, result: HeadlessFetchResult):
    """
    Wait for key fund data elements to appear on the page.
    Records which selectors were found.
    """
    for selector in KEY_DATA_SELECTORS:
        try:
            page.wait_for_selector(selector, timeout=5000)
            result.key_fields_found.append(selector)
        except Exception:
            pass  # Not all selectors are expected on every page

    if result.key_fields_found:
        print(f"    ✓ Key selectors found: {len(result.key_fields_found)}/{len(KEY_DATA_SELECTORS)}")
    else:
        print(f"    ⚠ No key selectors found — page structure may have changed")


def _scroll_full_page(page):
    """Scroll the page to trigger lazy-loaded content."""
    try:
        page.evaluate("""
            async () => {
                await new Promise((resolve) => {
                    let totalHeight = 0;
                    const distance = 400;
                    const timer = setInterval(() => {
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        if (totalHeight >= document.body.scrollHeight) {
                            clearInterval(timer);
                            window.scrollTo(0, 0);
                            resolve();
                        }
                    }, 100);
                });
            }
        """)
        # Wait a moment for any lazy content to render
        page.wait_for_timeout(2000)
    except Exception:
        pass  # Scroll failure is not critical


def save_raw_html(result: HeadlessFetchResult) -> Path | None:
    """
    Save rendered HTML to disk.
    Returns the path to the saved file, or None if skipped.
    """
    if not result.raw_html:
        return None

    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)

    url_slug = urlparse(result.url).path.strip("/").replace("/", "_")
    filename = f"{url_slug}.html"
    filepath = RAW_HTML_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(result.raw_html)

    print(f"    💾 Saved: {filepath.name} ({result.content_length:,} chars)")
    return filepath


# ─── Batch Runner ─────────────────────────────────────────────────────────────

def run_headless_fetch(
    url_entries: list[dict] | None = None,
) -> list[HeadlessFetchResult]:
    """
    Run headless fetch for the given URLs (or all 5 from manifest).

    Args:
        url_entries: Optional list of manifest entries to fetch.
                     If None, loads all from corpus_manifest.json.

    Returns:
        List of HeadlessFetchResult objects.
    """
    if not check_playwright_installed():
        print("[ERROR] Playwright is not installed. Run: pip install playwright")
        sys.exit(1)

    from playwright.sync_api import sync_playwright

    # Load manifest entries if not provided
    if url_entries is None:
        if not MANIFEST_PATH.exists():
            print(f"[ERROR] Manifest not found at {MANIFEST_PATH}")
            sys.exit(1)
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        url_entries = manifest.get("corpus_urls", [])

    results: list[HeadlessFetchResult] = []

    print("=" * 60)
    print("  Subphase 1.3 — Headless Browser Fetch (Playwright)")
    print("=" * 60)

    # Use a single browser instance for all URLs (much faster than per-URL launch)
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            java_script_enabled=True,
        )

        for entry in url_entries:
            url = entry["url"]
            scheme = entry["scheme"]
            entry_id = entry["id"]

            print(f"\n[{entry_id}] {scheme}")
            result = fetch_url_headless(
                url=url,
                scheme=scheme,
                entry_id=entry_id,
                playwright_context=context,
            )

            if result.raw_html:
                save_raw_html(result)

            results.append(result)

        context.close()
        browser.close()
    finally:
        pw.stop()

    # ── Summary ──
    print("\n" + "=" * 60)
    print("  Summary — Headless Fetch")
    print("=" * 60)

    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    print(f"  ✓ Headless fetch OK: {len(successful)}/{len(results)}")
    print(f"  ✗ Failed:            {len(failed)}/{len(results)}")

    if successful:
        avg_time = sum(r.render_time_ms for r in successful) / len(successful)
        print(f"  ⏱ Avg render time:   {avg_time:.0f}ms")

    if failed:
        print("\n  Failed URLs:")
        for r in failed:
            print(f"    ✗ [{r.entry_id}] {r.scheme} — {r.error}")

    print("=" * 60)
    return results


# ─── Integrated Pipeline: 1.2 → 1.3 ─────────────────────────────────────────

def run_fetch_pipeline() -> list[dict]:
    """
    Run the full fetch pipeline: static (1.2) → headless fallback (1.3).

    1. Attempts static fetch for all 5 URLs
    2. For URLs that need headless, automatically escalates to Playwright
    3. Returns combined results for all URLs

    This is the recommended entry point for the ingestion pipeline.
    """
    # Import subphase 1.2
    from src.phase1_data_collection.subphase_1_2_static_fetch import run_static_fetch

    print("\n" + "=" * 60)
    print("  Phase 1 — Fetch Pipeline (Subphase 1.2 → 1.3)")
    print("=" * 60)

    # ── Step 1: Run static fetch for all URLs ──
    static_results = run_static_fetch()

    # ── Step 2: Identify URLs that need headless ──
    needs_headless = [r for r in static_results if r.needs_headless]
    static_ok = [r for r in static_results if r.success]

    combined_results = []

    # Collect successful static fetches
    for r in static_ok:
        combined_results.append({
            **r.to_dict(),
            "raw_html_path": str(RAW_HTML_DIR / f"{urlparse(r.url).path.strip('/').replace('/', '_')}.html"),
        })

    # ── Step 3: Run headless for escalated URLs ──
    if needs_headless:
        print(f"\n{'─' * 60}")
        print(f"  Escalating {len(needs_headless)} URL(s) to Subphase 1.3 (Playwright)")
        print(f"{'─' * 60}")

        if not MANIFEST_PATH.exists():
            print(f"[ERROR] Manifest not found at {MANIFEST_PATH}")
            sys.exit(1)

        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        # Build entries to fetch via headless
        headless_entries = []
        for r in needs_headless:
            for entry in manifest.get("corpus_urls", []):
                if entry["url"] == r.url:
                    headless_entries.append(entry)
                    break

        headless_results = run_headless_fetch(url_entries=headless_entries)

        for r in headless_results:
            combined_results.append({
                **r.to_dict(),
                "raw_html_path": str(RAW_HTML_DIR / f"{urlparse(r.url).path.strip('/').replace('/', '_')}.html"),
            })
    else:
        print("\n  ✓ All URLs fetched via static — no headless escalation needed.")

    # ── Final Summary ──
    print("\n" + "=" * 60)
    print("  Phase 1 Fetch Pipeline — Final Summary")
    print("=" * 60)

    total = len(combined_results)
    ok = sum(1 for r in combined_results if r.get("error") is None)
    static_count = sum(1 for r in combined_results if r.get("fetch_method") == "static")
    headless_count = sum(1 for r in combined_results if r.get("fetch_method") == "headless")

    print(f"  Total URLs:    {total}")
    print(f"  Successful:    {ok}")
    print(f"  Via static:    {static_count}")
    print(f"  Via headless:  {headless_count}")
    print("=" * 60)

    # Save pipeline results to JSON
    results_path = Path(__file__).parent / "output" / "fetch_pipeline_results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "pipeline_run": datetime.now(timezone.utc).isoformat(),
                "total_urls": total,
                "successful": ok,
                "static_count": static_count,
                "headless_count": headless_count,
                "results": combined_results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\n  📄 Pipeline results saved to: {results_path}")

    return combined_results


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    """
    When run directly, fetch all 5 URLs via headless browser.
    For the integrated pipeline (1.2 → 1.3), use run_fetch_pipeline().
    """
    results = run_headless_fetch()
    failed = [r for r in results if not r.success]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
