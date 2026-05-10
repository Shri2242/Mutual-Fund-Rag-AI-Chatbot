"""
Subphase 1.2 — Static HTML Fetch (Requests Attempt)
===================================================
Goal: Attempt a lightweight static fetch of each URL using requests.
This is the fast path — used only if the page is not JS-rendered.

If content is too short (< 2,000 chars), it means Groww is rendering
via JavaScript (SPA) and we need to escalate to Subphase 1.3.

Usage:
    python -m src.phase1_data_collection.subphase_1_2_static_fetch
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from pathlib import Path

# Fix Windows console encoding for special characters
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    import requests
except ImportError:
    print("[ERROR] 'requests' library not found. Run: pip install requests")
    sys.exit(1)

# ─── Constants ────────────────────────────────────────────────────────────────

MANIFEST_PATH = Path(__file__).parent.parent / "phase0_corpus_registry" / "corpus_manifest.json"
RAW_HTML_DIR = Path(__file__).parent / "raw_html"
MIN_CONTENT_LENGTH = 2000   # Below this = likely JS shell, escalate to 1.3
ALLOWED_DOMAIN = "groww.in"
REQUEST_TIMEOUT = 15        # seconds
MAX_RETRIES = 3             # Retry attempts with exponential backoff
BASE_BACKOFF = 2            # Base backoff in seconds

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


# ─── Fetch Result Container ──────────────────────────────────────────────────

class FetchResult:
    """Container for a single URL's static fetch result."""

    def __init__(self, url: str, scheme: str, entry_id: int):
        self.url = url
        self.scheme = scheme
        self.entry_id = entry_id
        self.status_code: int | None = None
        self.content_length: int = 0
        self.raw_html: str = ""
        self.fetch_method: str = "static"
        self.needs_headless: bool = False
        self.error: str | None = None
        self.final_url: str | None = None
        self.fetch_timestamp: str | None = None

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "scheme": self.scheme,
            "url": self.url,
            "status_code": self.status_code,
            "content_length": self.content_length,
            "fetch_method": self.fetch_method,
            "needs_headless": self.needs_headless,
            "final_url": self.final_url,
            "error": self.error,
            "fetch_timestamp": self.fetch_timestamp,
        }

    @property
    def success(self) -> bool:
        return (
            self.status_code == 200
            and self.content_length >= MIN_CONTENT_LENGTH
            and not self.needs_headless
            and self.error is None
        )


# ─── Core Fetch Logic ────────────────────────────────────────────────────────

def fetch_url_static(url: str, scheme: str, entry_id: int) -> FetchResult:
    """
    Attempt a static HTTP GET for a single URL with retry + backoff.

    Returns a FetchResult indicating whether the content is sufficient
    or whether Subphase 1.3 (headless) is needed.
    """
    result = FetchResult(url=url, scheme=scheme, entry_id=entry_id)
    result.fetch_timestamp = datetime.now(timezone.utc).isoformat()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"    [Attempt {attempt}/{MAX_RETRIES}] GET {url}")
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )

            result.status_code = response.status_code
            result.final_url = response.url

            # ── Redirect safety: final domain must still be groww.in ──
            final_domain = urlparse(response.url).netloc.lower().replace("www.", "")
            if final_domain != ALLOWED_DOMAIN:
                result.error = (
                    f"Redirected to external domain '{final_domain}'. "
                    f"Only '{ALLOWED_DOMAIN}' is permitted."
                )
                result.needs_headless = False  # Don't escalate — this is a domain error
                print(f"    [X] {result.error}")
                return result

            # ── HTTP status check ──
            if response.status_code != 200:
                result.error = f"HTTP {response.status_code} -- non-200 status."
                if attempt < MAX_RETRIES:
                    backoff = BASE_BACKOFF ** attempt
                    print(f"    [X] {result.error} Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
                print(f"    ✗ {result.error} All retries exhausted.")
                return result

            # ── Content length check ──
            result.raw_html = response.text
            result.content_length = len(result.raw_html)

            if result.content_length < MIN_CONTENT_LENGTH:
                result.needs_headless = True
                result.error = (
                    f"Content too short ({result.content_length} chars < {MIN_CONTENT_LENGTH}). "
                    "Likely JS-rendered SPA -- escalating to Subphase 1.3 (Playwright)."
                )
                print(f"    [!] {result.error}")
                return result

            # -- All checks passed --
            print(
                f"    [OK] Static fetch OK -- "
                f"{result.content_length:,} chars, HTTP {result.status_code}"
            )
            return result

        except requests.exceptions.Timeout:
            result.error = f"Request timed out after {REQUEST_TIMEOUT}s."
            if attempt < MAX_RETRIES:
                backoff = BASE_BACKOFF ** attempt
                print(f"    [X] Timeout. Retrying in {backoff}s...")
                time.sleep(backoff)
            else:
                print(f"    [X] {result.error} All retries exhausted.")
                result.needs_headless = True

        except requests.exceptions.ConnectionError:
            result.error = "Connection error -- unable to reach the URL."
            if attempt < MAX_RETRIES:
                backoff = BASE_BACKOFF ** attempt
                print(f"    [X] Connection error. Retrying in {backoff}s...")
                time.sleep(backoff)
            else:
                print(f"    [X] {result.error} All retries exhausted.")

        except requests.exceptions.RequestException as e:
            result.error = f"Request failed: {e}"
            print(f"    [X] {result.error}")
            return result

    return result


def save_raw_html(result: FetchResult) -> Path | None:
    """
    Save raw HTML to disk if fetch was successful.
    Returns the path to the saved file, or None if skipped.
    """
    if not result.raw_html:
        return None

    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)

    # Use a slug from the URL path for the filename
    url_slug = urlparse(result.url).path.strip("/").replace("/", "_")
    filename = f"{url_slug}.html"
    filepath = RAW_HTML_DIR / filename

    with open(filepath, "w", encoding="utf-8", errors="replace") as f:
        f.write(result.raw_html)

    print(f"    [SAVED] {filepath.name} ({result.content_length:,} chars)")
    return filepath


# ─── Main Runner ──────────────────────────────────────────────────────────────

def run_static_fetch() -> list[FetchResult]:
    """
    Run static fetch for all 5 corpus URLs.
    Returns a list of FetchResult objects.
    """
    if not MANIFEST_PATH.exists():
        print(f"[ERROR] Manifest not found at {MANIFEST_PATH}")
        sys.exit(1)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    urls = manifest.get("corpus_urls", [])
    results: list[FetchResult] = []

    print("=" * 60)
    print("  Subphase 1.2 — Static HTML Fetch (Requests)")
    print("=" * 60)

    for entry in urls:
        url = entry["url"]
        scheme = entry["scheme"]
        entry_id = entry["id"]

        print(f"\n[{entry_id}] {scheme}")
        result = fetch_url_static(url=url, scheme=scheme, entry_id=entry_id)

        # Save HTML if we got meaningful content (even if it needs headless)
        if result.raw_html:
            save_raw_html(result)

        results.append(result)

    # ── Summary ──
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)

    successful = [r for r in results if r.success]
    needs_headless = [r for r in results if r.needs_headless]
    failed = [r for r in results if not r.success and not r.needs_headless and r.error]

    print(f"  [OK] Static fetch OK:     {len(successful)}/5")
    print(f"  [!!] Needs headless (1.3): {len(needs_headless)}/5")
    print(f"  [X]  Failed:              {len(failed)}/5")

    if needs_headless:
        print("\n  URLs escalated to Subphase 1.3 (Playwright):")
        for r in needs_headless:
            print(f"    -> [{r.entry_id}] {r.scheme}")

    if failed:
        print("\n  Failed URLs:")
        for r in failed:
            print(f"    [X] [{r.entry_id}] {r.scheme} -- {r.error}")

    print("=" * 60)
    return results


def main():
    results = run_static_fetch()

    # Exit with code 0 if all fetched (even if some need headless — that's expected)
    failed = [r for r in results if not r.success and not r.needs_headless and r.error]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
