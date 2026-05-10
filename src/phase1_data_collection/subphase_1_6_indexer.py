"""
Sub-phase 1.6 — Indexer
========================
Goal: Build the dense (Chroma) and sparse (BM25) indexes that Phase 2 queries against.
Input: JSON chunk files from subphase 1.4.
Output: `data/index/` containing ChromaDB, BM25 index, canonical `chunks.jsonl`, and `manifest.json`.

Usage:
    python -m src.phase1_data_collection.subphase_1_6_indexer
"""

import json
import os
import shutil
import sys
import pickle
from pathlib import Path
from datetime import datetime, timezone

try:
    import chromadb
    from chromadb.utils import embedding_functions
    from rank_bm25 import BM25Okapi
    # Force disable ChromaDB due to Windows C++ redistributable issue
    HAS_CHROMADB = False
except ImportError as e:
    print(f"[WARNING] Skipping ChromaDB due to import error: {e}")
    HAS_CHROMADB = False
    from rank_bm25 import BM25Okapi

# ─── Constants ────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent.parent
OUTPUT_DIR = BASE_DIR / "src" / "phase1_data_collection" / "output"
DATA_INDEX_DIR = BASE_DIR / "data" / "index"
STAGING_DIR = DATA_INDEX_DIR / ".staging"

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2 (Chroma Default)"
COLLECTION_NAME = "mutual_funds_collection"


class Indexer:
    @staticmethod
    def _create_fund_document(fund_json: dict) -> str:
        """Convert structured JSON into a dense natural language paragraph."""
        scheme = fund_json.get("scheme", "Unknown Scheme")
        nav = fund_json.get("nav", "N/A")
        aum = fund_json.get("aum", "N/A")
        expense_ratio = fund_json.get("expense_ratio", "N/A")
        exit_load = fund_json.get("exit_load", "N/A")
        min_sip = fund_json.get("min_sip", "N/A")
        riskometer = fund_json.get("riskometer", "N/A")
        benchmark = fund_json.get("benchmark", "N/A")
        fund_manager = fund_json.get("fund_manager", "N/A")
        
        text = f"Fund Name: {scheme}.\n"
        text += f"The current NAV is {nav}. "
        text += f"The Assets Under Management (AUM) is {aum}. "
        text += f"The Expense Ratio is {expense_ratio}%. "
        text += f"The Exit Load is: {exit_load}. "
        text += f"The minimum SIP amount is ₹{min_sip}. "
        text += f"The risk level is rated as {riskometer}. "
        text += f"The benchmark index is {benchmark}. "
        text += f"The fund manager is {fund_manager}. "
        
        holdings = fund_json.get("top_5_holdings", [])
        if holdings:
            holdings_text = ", ".join([f"{h.get('company_name')} ({h.get('allocation_percent')}%)" for h in holdings])
            text += f"Top holdings include: {holdings_text}."
            
        return text

    @classmethod
    def build(cls):
        print("=" * 60)
        print("  Sub-phase 1.6 — Indexer (ChromaDB + BM25)")
        print("=" * 60)

        if not OUTPUT_DIR.exists():
            print(f"[ERROR] Output directory not found at {OUTPUT_DIR}")
            sys.exit(1)

        json_files = list(OUTPUT_DIR.glob("*.json"))
        if not json_files:
            print(f"[ERROR] No JSON chunks found in {OUTPUT_DIR}")
            sys.exit(1)

        # 1. Load Data
        print(f"[*] Loading {len(json_files)} fund files...")
        chunks = []
        for jf in json_files:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
                chunk_id = jf.stem
                text = cls._create_fund_document(data.get("fields", {}))
                
                metadata = {
                    "source_url": data.get("source_url", ""),
                    "scheme": data.get("scheme", ""),
                    "fetch_date": data.get("fetch_date", ""),
                    "category": data.get("fields", {}).get("category", "")
                }
                
                chunks.append({
                    "chunk_id": chunk_id,
                    "text": text,
                    "metadata": metadata
                })

        # 2. Setup Staging
        print("[*] Preparing staging directory...")
        if STAGING_DIR.exists():
            shutil.rmtree(STAGING_DIR)
        STAGING_DIR.mkdir(parents=True, exist_ok=True)

        # 3. Dense Index (ChromaDB + Embeddings)
        texts = [c["text"] for c in chunks]
        
        if HAS_CHROMADB:
            print(f"[*] Loading Embedding Model ({EMBEDDING_MODEL_NAME})...")
            
            # We use Chroma's default ONNX-based embedder to avoid PyTorch/MSVC++ Windows dependency issues
            default_ef = embedding_functions.DefaultEmbeddingFunction()
            
            print("[*] Generating embeddings & building ChromaDB index...")
            chroma_path = STAGING_DIR / "chroma"
            chroma_client = chromadb.PersistentClient(path=str(chroma_path))
            
            # Delete if exists to start fresh in staging
            try:
                chroma_client.delete_collection(name=COLLECTION_NAME)
            except Exception:
                pass
                
            collection = chroma_client.create_collection(name=COLLECTION_NAME, embedding_function=default_ef)
            
            collection.add(
                ids=[c["chunk_id"] for c in chunks],
                documents=texts,
                metadatas=[c["metadata"] for c in chunks]
            )
        else:
            print("[WARNING] Skipping ChromaDB dense index creation (dependency not available).")

        # 4. Sparse Index (BM25)
        print("[*] Building BM25 sparse index...")
        tokenized_corpus = [doc.lower().split(" ") for doc in texts]
        bm25 = BM25Okapi(tokenized_corpus)
        with open(STAGING_DIR / "bm25.pkl", "wb") as f:
            pickle.dump(bm25, f)

        # 5. Canonical Store
        print("[*] Writing canonical chunks.jsonl...")
        with open(STAGING_DIR / "chunks.jsonl", "w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

        # 6. Manifest
        print("[*] Writing manifest.json...")
        manifest = {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "embedder": EMBEDDING_MODEL_NAME,
            "n_chunks": len(chunks),
            "per_scheme_counts": {c["metadata"]["scheme"]: 1 for c in chunks},
        }
        with open(STAGING_DIR / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # 7. Atomic Swap
        print("[*] Performing atomic swap to production index...")
        if HAS_CHROMADB:
            try:
                # Force close chromadb connection so Windows allows moving the folder
                del chroma_client
                del collection
                import gc
                gc.collect()
            except Exception:
                pass
            
        # Ensure target doesn't block rename
        if DATA_INDEX_DIR.exists():
            for item in DATA_INDEX_DIR.iterdir():
                if item.name == ".staging":
                    continue
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
                    
        # Move everything from staging to index
        for item in STAGING_DIR.iterdir():
            shutil.move(str(item), str(DATA_INDEX_DIR / item.name))
            
        # Cleanup staging
        shutil.rmtree(STAGING_DIR, ignore_errors=True)

        print("\n" + "=" * 60)
        print("  Summary — Indexer.build() Complete")
        print("=" * 60)
        print(f"  Chunks Indexed: {len(chunks)}")
        print(f"  Embedder: {EMBEDDING_MODEL_NAME}")
        print(f"  Output Directory: {DATA_INDEX_DIR}")
        print("=" * 60)


if __name__ == "__main__":
    Indexer.build()
