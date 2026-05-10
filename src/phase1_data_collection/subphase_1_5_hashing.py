"""
Subphase 1.5 — Content Hashing & Manifest Update
================================================
Goal: Compute a content hash per page and update `corpus_manifest.json` with fetch results. 
This enables change detection on future runs, preventing redundant re-ingestion.

Usage:
    python -m src.phase1_data_collection.subphase_1_5_hashing
"""

import json
import hashlib
import sys
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

# ─── Constants ────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
RAW_HTML_DIR = BASE_DIR / "raw_html"
MANIFEST_PATH = BASE_DIR.parent / "phase0_corpus_registry" / "corpus_manifest.json"

# ─── Hashing Logic ────────────────────────────────────────────────────────────

def compute_sha256(filepath: Path) -> str:
    """Compute the SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def run_hashing():
    if not MANIFEST_PATH.exists():
        print(f"[ERROR] Manifest not found at {MANIFEST_PATH}")
        sys.exit(1)
        
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
        
    print("=" * 60)
    print("  Subphase 1.5 — Content Hashing & Manifest Update")
    print("=" * 60)
    
    current_time = datetime.now(timezone.utc).isoformat()
    urls = manifest.get("corpus_urls", [])
    
    stats = {"unchanged": 0, "changed": 0, "ingested_first_time": 0, "missing": 0}
    
    for entry in urls:
        url = entry["url"]
        scheme = entry["scheme"]
        entry_id = entry["id"]
        previous_hash = entry.get("content_hash")
        
        # Determine the filename that was saved in 1.2 / 1.3
        url_slug = urlparse(url).path.strip("/").replace("/", "_")
        html_filepath = RAW_HTML_DIR / f"{url_slug}.html"
        
        print(f"\n[{entry_id}] {scheme}")
        
        if not html_filepath.exists():
            print(f"  [!] Missing raw HTML: {html_filepath.name}")
            entry["status"] = "missing_data"
            stats["missing"] += 1
            continue
            
        # Compute new hash
        new_hash = compute_sha256(html_filepath)
        
        # Compare and update status
        if previous_hash is None:
            status = "ingested_first_time"
            stats["ingested_first_time"] += 1
            print(f"  [+] First time ingestion. Hash: {new_hash[:8]}...")
        elif previous_hash == new_hash:
            status = "unchanged"
            stats["unchanged"] += 1
            print(f"  [=] Unchanged. Hash: {new_hash[:8]}...")
        else:
            status = "changed"
            stats["changed"] += 1
            print(f"  [~] Changed! Old: {previous_hash[:8]}... -> New: {new_hash[:8]}...")
            
        # Update entry
        entry["content_hash"] = new_hash
        entry["last_fetched"] = current_time
        entry["status"] = status
        
    # Update global manifest metadata
    manifest["last_ingested"] = current_time
    
    # Save Manifest
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    print(f"  Total processed: {len(urls)}")
    print(f"  First time: {stats['ingested_first_time']}")
    print(f"  Changed: {stats['changed']}")
    print(f"  Unchanged: {stats['unchanged']}")
    print(f"  Missing: {stats['missing']}")
    print("=" * 60)
    print(f"[SAVED] Manifest updated successfully at: {MANIFEST_PATH.name}")
    
    if stats["missing"] > 0:
        sys.exit(1)

if __name__ == "__main__":
    run_hashing()
