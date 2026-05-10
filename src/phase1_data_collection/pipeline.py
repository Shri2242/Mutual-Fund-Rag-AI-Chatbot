"""
Sub-phase 1.7 — Refresh & Health Orchestrator
=============================================
Goal: Orchestrate sub-phases 1.1 through 1.6 as a re-runnable pipeline.
Implements drift detection, stable hashing, and index freezing.

Usage:
    python -m src.phase1_data_collection.pipeline
"""

import json
import hashlib
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
DATA_INDEX_DIR = BASE_DIR.parent.parent / "data" / "index"
MANIFEST_PATH = BASE_DIR.parent / "phase0_corpus_registry" / "corpus_manifest.json"
REFRESH_LOG = DATA_INDEX_DIR / "refresh_log.jsonl"

VOLATILE_FIELDS = ["nav", "aum"]

class Pipeline:
    @staticmethod
    def _compute_stable_hash(fund_json: dict) -> str:
        """Compute a hash of the JSON fields, excluding volatile fields like NAV and AUM."""
        fields = fund_json.get("fields", {})
        stable_dict = {k: v for k, v in fields.items() if k not in VOLATILE_FIELDS}
        # Include scheme name
        stable_dict["scheme"] = fund_json.get("scheme", "")
        
        json_str = json.dumps(stable_dict, sort_keys=True)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    @classmethod
    def refresh(cls, force=False):
        print("\n" + "=" * 60)
        print("  Starting Sub-phase 1.7: Refresh & Health Orchestrator")
        print("=" * 60)
        
        start_time = datetime.now(timezone.utc)
        
        # 1. Load Manifest
        if not MANIFEST_PATH.exists():
            print("[ERROR] corpus_manifest.json not found!")
            sys.exit(1)
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
            
        urls = manifest.get("corpus_urls", [])
        
        # 2. Run Data Collection (1.1 -> 1.4)
        print("\n[*] Running Data Collection (Robots -> Fetch -> Extract)...")
        # For MVP, we use subprocess to orchestrate the existing scripts
        try:
            subprocess.run([sys.executable, "-m", "src.phase1_data_collection.subphase_1_1_robots"], check=True)
            subprocess.run([sys.executable, "-m", "src.phase1_data_collection.subphase_1_2_static_fetch"], check=True)
            subprocess.run([sys.executable, "-m", "src.phase1_data_collection.subphase_1_4_extraction"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Pipeline failed during data collection: {e}")
            sys.exit(1)
            
        # 3. Drift Detection (Stable Hashing)
        print("\n[*] Running Drift Detection & Soft-404 Checks...")
        json_files = list(OUTPUT_DIR.glob("*.json"))
        
        drift_count = 0
        soft_404_count = 0
        
        for entry in urls:
            # Find the matching JSON file
            target_url = entry["url"]
            matched_file = None
            for jf in json_files:
                with open(jf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("source_url") == target_url:
                        matched_file = jf
                        break
            
            if not matched_file:
                print(f"  [!] Soft-404 or missing extraction for: {target_url}")
                soft_404_count += 1
                entry["status"] = "soft_404"
                continue
                
            # Compute stable hash
            with open(matched_file, "r", encoding="utf-8") as f:
                fund_data = json.load(f)
                
            stable_hash = cls._compute_stable_hash(fund_data)
            previous_hash = entry.get("stable_content_hash")
            
            if previous_hash is None:
                print(f"  [+] First time stable hash for: {entry['scheme']}")
                entry["stable_content_hash"] = stable_hash
                entry["last_updated_from_source"] = start_time.isoformat()
                drift_count += 1 # First time counts as a change
            elif stable_hash != previous_hash:
                print(f"  [~] DRIFT DETECTED for: {entry['scheme']}")
                entry["stable_content_hash"] = stable_hash
                entry["last_updated_from_source"] = start_time.isoformat()
                drift_count += 1
            else:
                print(f"  [=] Stable (No drift) for: {entry['scheme']}")
                
        # 4. Evaluate Health & Freeze Logic
        outcome = "ok"
        if soft_404_count > 0:
            outcome = "partial"
            
        # If >= 2 URLs drifted in a single window, freeze the index
        if drift_count >= 2 and len(urls) > 2 and not force:
            print("\n[CRITICAL ALERT] Drift detected across >= 2 URLs!")
            print("[*] Freezing index. Aborting Phase 1.6 Indexer overwrite.")
            outcome = "frozen"
        else:
            print("\n[*] Health checks passed. Running Phase 1.6 Indexer...")
            try:
                subprocess.run([sys.executable, "-m", "src.phase1_data_collection.subphase_1_6_indexer"], check=True)
            except subprocess.CalledProcessError as e:
                print(f"[ERROR] Indexer failed: {e}")
                outcome = "failed"

        # 5. Save Manifest & Log
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        log_entry = {
            "timestamp": start_time.isoformat(),
            "duration_seconds": round(duration, 2),
            "drift_count": drift_count,
            "soft_404_count": soft_404_count,
            "outcome": outcome
        }
        
        DATA_INDEX_DIR.mkdir(parents=True, exist_ok=True)
        with open(REFRESH_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
            
        print("\n" + "=" * 60)
        print(f"  Pipeline Complete. Outcome: {outcome.upper()}")
        print(f"  Log saved to: {REFRESH_LOG}")
        print("=" * 60)


if __name__ == "__main__":
    Pipeline.refresh()
