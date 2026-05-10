"""
Phase 2 — Preprocessing & Chunking
==================================
Goal: Convert the highly structured JSON data extracted in Phase 1 into 
semantic, retrievable text chunks for the vector database.

Usage:
    python -m src.phase2_chunking.chunker
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent
PHASE1_OUTPUT_DIR = BASE_DIR / "src" / "phase1_data_collection" / "output"
PHASE2_OUTPUT_DIR = BASE_DIR / "src" / "phase2_chunking" / "output"

class Chunker:
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
    def run_chunking(cls):
        print("=" * 60)
        print("  Phase 2 — Preprocessing & Chunking")
        print("=" * 60)

        if not PHASE1_OUTPUT_DIR.exists():
            print(f"[ERROR] Phase 1 output directory not found at {PHASE1_OUTPUT_DIR}")
            sys.exit(1)

        json_files = list(PHASE1_OUTPUT_DIR.glob("*.json"))
        if not json_files:
            print(f"[ERROR] No JSON chunks found in {PHASE1_OUTPUT_DIR}")
            sys.exit(1)

        PHASE2_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        processed_count = 0
        chunks = []

        print(f"[*] Converting JSON to Natural Language Chunks...")
        for jf in json_files:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
                
                chunk_id = jf.stem
                fields = data.get("fields", {})
                
                # Inject top-level scheme name into fields so the text chunk
                # says "Fund Name: HDFC Mid Cap Fund..." instead of "Unknown Scheme"
                fields["scheme"] = data.get("scheme", fields.get("scheme", "Unknown Scheme"))
                
                # Convert to text
                text = cls._create_fund_document(fields)
                
                # Extract Metadata
                metadata = {
                    "source_url": data.get("source_url", ""),
                    "scheme": data.get("scheme", ""),
                    "fetch_date": data.get("fetch_date", ""),
                    "category": fields.get("category", "")
                }
                
                chunk_payload = {
                    "chunk_id": chunk_id,
                    "text": text,
                    "metadata": metadata
                }
                chunks.append(chunk_payload)
                
                # Save chunk payload
                output_file = PHASE2_OUTPUT_DIR / f"{chunk_id}_chunk.json"
                with open(output_file, "w", encoding="utf-8") as out_f:
                    json.dump(chunk_payload, out_f, indent=2, ensure_ascii=False)
                    
                processed_count += 1
                print(f"  [OK] Chunked {metadata['scheme']}")

        # Save Canonical Chunk Store
        chunks_jsonl_path = PHASE2_OUTPUT_DIR / "chunks.jsonl"
        with open(chunks_jsonl_path, "w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

        print("\n" + "=" * 60)
        print("  Summary — Chunking Complete")
        print("=" * 60)
        print(f"  Total funds processed: {processed_count}")
        print(f"  Saved chunks to: {PHASE2_OUTPUT_DIR}")
        print(f"  Canonical store: {chunks_jsonl_path.name}")
        print("=" * 60)


if __name__ == "__main__":
    Chunker.run_chunking()
