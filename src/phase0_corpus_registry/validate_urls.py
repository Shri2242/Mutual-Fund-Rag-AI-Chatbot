"""
Phase 0 — Corpus URL Registry
=================================
Loads and validates the corpus_manifest.json.
Enforces the scope-lock rule: exactly 5 Groww URLs, no additions allowed.

Usage:
    python validate_urls.py             # Validate all 5 URLs (HTTP check only)
    python validate_urls.py --update    # Validate and update statuses in manifest
"""

import json
import re
import sys
import hashlib
import argparse
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("[ERROR] 'requests' library not found. Run: pip install requests")
    sys.exit(1)

# ─── Constants ────────────────────────────────────────────────────────────────

MANIFEST_PATH = Path(__file__).parent / "corpus_manifest.json"
ALLOWED_DOMAIN = "groww.in"
EXPECTED_URL_COUNT = 5
REQUEST_TIMEOUT = 15  # seconds

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ─── Manifest Loader ──────────────────────────────────────────────────────────

def load_manifest() -> dict:
    """Load and parse corpus_manifest.json. Raises if file is missing or invalid."""
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"[FATAL] corpus_manifest.json not found at: {MANIFEST_PATH}\n"
            "This file must exist before ingestion can proceed."
        )
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    _validate_manifest_schema(manifest)
    return manifest


def save_manifest(manifest: dict) -> None:
    """Save the updated manifest back to disk."""
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\n[✓] Manifest saved to: {MANIFEST_PATH}")


def _validate_manifest_schema(manifest: dict) -> None:
    """Enforce schema and scope-lock rules on the manifest."""
    required_keys = {"project", "corpus_version", "scope_locked", "total_urls", "corpus_urls"}
    missing = required_keys - manifest.keys()
    if missing:
        raise ValueError(f"[FATAL] Manifest is missing required keys: {missing}")

    if not manifest.get("scope_locked"):
        raise ValueError(
            "[FATAL] scope_locked is False in manifest. "
            "v1 corpus must be scope-locked. Do not modify this field."
        )

    url_entries = manifest.get("corpus_urls", [])
    if len(url_entries) != EXPECTED_URL_COUNT:
        raise ValueError(
            f"[FATAL] Expected exactly {EXPECTED_URL_COUNT} URLs in corpus, "
            f"but found {len(url_entries)}. "
            "The corpus is scope-locked. Do not add or remove URLs."
        )

    for entry in url_entries:
        entry_required = {"id", "scheme", "category", "url", "status"}
        missing_fields = entry_required - entry.keys()
        if missing_fields:
            raise ValueError(
                f"[FATAL] URL entry id={entry.get('id')} is missing fields: {missing_fields}"
            )


# ─── URL Validators ───────────────────────────────────────────────────────────

def validate_domain(url: str) -> tuple[bool, str]:
    """Check that the URL belongs to the allowed domain (groww.in)."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower().replace("www.", "")
    if domain != ALLOWED_DOMAIN:
        return False, f"Domain '{domain}' is not allowed. Only '{ALLOWED_DOMAIN}' is permitted."
    return True, "OK"


def validate_url_reachable(url: str) -> tuple[bool, str, str | None]:
    """
    Check that the URL is reachable (HTTP 200) and does not redirect
    outside groww.in. Returns (ok, message, final_url).
    """
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )

        final_url = response.url
        final_domain = urlparse(final_url).netloc.lower().replace("www.", "")

        # Check for redirect to external domain
        if final_domain != ALLOWED_DOMAIN:
            return (
                False,
                f"Redirected to external domain: '{final_url}'. Only groww.in is allowed.",
                final_url
            )

        if response.status_code == 200:
            # Check for suspicious empty content (anti-bot shell)
            if len(response.text) < 2000:
                return (
                    False,
                    f"Page returned HTTP 200 but content is suspiciously short "
                    f"({len(response.text)} chars). Possible anti-bot response.",
                    final_url
                )
            return True, f"HTTP {response.status_code} — OK", final_url

        return (
            False,
            f"HTTP {response.status_code} — Unexpected status code.",
            final_url
        )

    except requests.exceptions.Timeout:
        return False, f"Request timed out after {REQUEST_TIMEOUT}s.", None
    except requests.exceptions.ConnectionError:
        return False, "Connection error — unable to reach the URL.", None
    except requests.exceptions.RequestException as e:
        return False, f"Request failed: {e}", None


def compute_content_hash(url: str) -> str | None:
    """Fetch URL and return SHA-256 hash of the content for change detection."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            return hashlib.sha256(response.content).hexdigest()
    except Exception:
        pass
    return None


# ─── Main Validation Runner ───────────────────────────────────────────────────

def run_validation(update_manifest: bool = False) -> bool:
    """
    Validate all corpus URLs from the manifest.
    If update_manifest=True, write statuses + hashes back to the JSON.
    Returns True if all URLs are valid, False otherwise.
    """
    print("=" * 60)
    print("  Phase 0 — Corpus URL Validation")
    print(f"  Manifest: {MANIFEST_PATH.name}")
    print("=" * 60)

    manifest = load_manifest()
    entries = manifest["corpus_urls"]
    all_passed = True
    timestamp = datetime.now(timezone.utc).isoformat()

    for entry in entries:
        url = entry["url"]
        scheme = entry["scheme"]
        print(f"\n[{entry['id']}] {scheme}")
        print(f"    URL: {url}")

        # Step 1: Domain check
        domain_ok, domain_msg = validate_domain(url)
        if not domain_ok:
            print(f"    ✗ Domain check FAILED: {domain_msg}")
            entry["status"] = "domain_rejected"
            all_passed = False
            continue
        print(f"    ✓ Domain check: {domain_msg}")

        # Step 2: Reachability check
        reachable, reach_msg, final_url = validate_url_reachable(url)
        print(f"    {'✓' if reachable else '✗'} Reachability: {reach_msg}")

        if not reachable:
            entry["status"] = "fetch_failed"
            all_passed = False
        else:
            # Step 3: Content hash (change detection)
            content_hash = compute_content_hash(url)
            prev_hash = entry.get("content_hash")

            if prev_hash and prev_hash == content_hash:
                print(f"    ℹ Content unchanged since last fetch (hash match). Skipping re-ingest.")
                entry["status"] = "unchanged"
            else:
                if prev_hash:
                    print(f"    ↻ Content has changed since last fetch — re-ingestion required.")
                    entry["status"] = "changed"
                else:
                    print(f"    ✓ First-time validation — ready for ingestion.")
                    entry["status"] = "ready_for_ingestion"
                entry["content_hash"] = content_hash

            entry["last_fetched"] = timestamp

    # Summary
    print("\n" + "=" * 60)
    passed = [e for e in entries if e["status"] in ("ready_for_ingestion", "unchanged", "changed")]
    failed = [e for e in entries if e["status"] in ("fetch_failed", "domain_rejected")]

    print(f"  Results: {len(passed)}/{len(entries)} URLs passed validation")
    if failed:
        print(f"  Failed URLs:")
        for e in failed:
            print(f"    ✗ [{e['id']}] {e['scheme']} — Status: {e['status']}")

    if update_manifest:
        manifest["last_validated"] = timestamp
        save_manifest(manifest)

    print("=" * 60)
    return all_passed


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Phase 0: Validate corpus URLs from corpus_manifest.json"
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update statuses and content hashes in corpus_manifest.json after validation"
    )
    args = parser.parse_args()

    try:
        all_valid = run_validation(update_manifest=args.update)
        sys.exit(0 if all_valid else 1)
    except (FileNotFoundError, ValueError) as e:
        print(str(e))
        sys.exit(2)


if __name__ == "__main__":
    main()
