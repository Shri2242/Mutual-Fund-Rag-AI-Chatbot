"""
Subphase 1.4 — Content Extraction & Chunking (Parser)
=====================================================
Goal: Parse the validated `.html` files by extracting the embedded Next.js JSON state
(`__NEXT_DATA__`) to build a clean JSON schema for RAG.

Usage:
    python -m src.phase1_data_collection.subphase_1_4_extraction
"""

import os
import sys
import json
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime, timezone

# ─── Constants ────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
RAW_HTML_DIR = BASE_DIR / "raw_html"
OUTPUT_DIR = BASE_DIR / "output"
ERROR_LOG_FILE = OUTPUT_DIR / "parsing_errors.log"

# Fix Windows console encoding for special characters
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ─── Extraction Logic ─────────────────────────────────────────────────────────

def extract_fund_data(html_content: str, url: str) -> dict:
    """
    Extract key fund data from the __NEXT_DATA__ JSON payload in the HTML.
    """
    soup = BeautifulSoup(html_content, "lxml")
    script_tag = soup.find("script", id="__NEXT_DATA__")
    
    if not script_tag:
        raise ValueError("Could not find __NEXT_DATA__ script tag in the HTML.")
    
    data = json.loads(script_tag.string)
    
    # Navigate the JSON payload
    props = data.get("props", {})
    page_props = props.get("pageProps", {})
    mf_data = page_props.get("mfServerSideData", {})
    
    if not mf_data:
        raise ValueError("Missing 'mfServerSideData' in the Next.js payload.")
    
    # Extract specific fields
    return_stats = mf_data.get("return_stats", [{}])[0] if mf_data.get("return_stats") else {}
    category_info = mf_data.get("category_info", {})
    lock_in_info = mf_data.get("lock_in", {})
    
    # Map to Target Fields
    extracted_data = {
        "expense_ratio": mf_data.get("expense_ratio"),
        "exit_load": mf_data.get("exit_load"),
        "min_sip": mf_data.get("min_sip_investment"),
        "riskometer": return_stats.get("risk"),
        "benchmark": mf_data.get("benchmark_name") or mf_data.get("benchmark"),
        "lock_in_period": lock_in_info.get("years") if lock_in_info else None,
        "fund_manager": mf_data.get("fund_manager"),
        "nav": mf_data.get("nav"),
        "category": category_info.get("category"),
        "sub_category": mf_data.get("sub_category"),
        "aum": mf_data.get("aum"),
        "top_5_holdings": []
    }
    
    # Parse Holdings
    holdings = mf_data.get("holdings", [])
    for h in holdings[:5]:
        extracted_data["top_5_holdings"].append({
            "company_name": h.get("company_name"),
            "allocation_percent": h.get("corpus_per")
        })
        
    return extracted_data

# ─── Main Runner ──────────────────────────────────────────────────────────────

def run_extraction():
    if not RAW_HTML_DIR.exists():
        print(f"[ERROR] Raw HTML directory not found at {RAW_HTML_DIR}")
        sys.exit(1)
        
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    html_files = list(RAW_HTML_DIR.glob("*.html"))
    if not html_files:
        print(f"[ERROR] No HTML files found in {RAW_HTML_DIR}")
        sys.exit(1)
        
    print("=" * 60)
    print("  Subphase 1.4 — Content Extraction (Next.js JSON parsing)")
    print("=" * 60)
    
    results = []
    errors = []
    
    for html_file in html_files:
        print(f"\nProcessing: {html_file.name}")
        
        with open(html_file, "r", encoding="utf-8") as f:
            html_content = f.read()
            
        try:
            fund_data = extract_fund_data(html_content, html_file.name)
            
            # Check for partial data
            missing_fields = [k for k, v in fund_data.items() if v is None and k != "lock_in_period"] # lock_in is often null naturally
            partial_data = len(missing_fields) > 4  # Require at least 6/10 fields
            
            if missing_fields:
                print(f"  [!] Missing fields: {', '.join(missing_fields)}")
            
            # Retrieve scheme name from JSON, but place it at the top level
            soup = BeautifulSoup(html_content, "lxml")
            script_tag = soup.find("script", id="__NEXT_DATA__")
            if script_tag:
                data = json.loads(script_tag.string)
                mf_data = data.get("props", {}).get("pageProps", {}).get("mfServerSideData", {})
                scheme_name = mf_data.get("scheme_name", "Unknown Scheme")
                
                # Derive source URL from filename (e.g. mutual-funds_hdfc-mid-cap-fund-direct-growth.html -> https://groww.in/mutual-funds/...)
                url_slug = html_file.stem.replace("_", "/")
                source_url = f"https://groww.in/{url_slug}"
            else:
                scheme_name = "Unknown Scheme"
                source_url = "Unknown URL"
                
            entry = {
                "scheme": scheme_name,
                "source_url": source_url,
                "fetch_date": datetime.now(timezone.utc).date().isoformat(),
                "fetch_method": "static", # Assuming static since we read from raw_html. Real pipeline would track this.
                "fields": fund_data,
                "partial_data": partial_data
            }
            results.append(entry)
            
            # Save individual JSON per scheme
            url_slug = html_file.stem
            output_filepath = OUTPUT_DIR / f"{url_slug}.json"
            with open(output_filepath, "w", encoding="utf-8") as f:
                json.dump(entry, f, indent=2, ensure_ascii=False)
                
            print(f"  [OK] Extracted data saved to {output_filepath.name}")
            
        except Exception as e:
            error_msg = f"{html_file.name}: {str(e)}"
            errors.append(error_msg)
            print(f"  [X] Extraction failed: {e}")
            
    # Save Errors
    if errors:
        with open(ERROR_LOG_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(errors))
        print(f"\n[SAVED] Error log saved to: {ERROR_LOG_FILE}")
        
    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    print(f"  Total processed: {len(html_files)}")
    print(f"  Successfully extracted: {len(results)}")
    print(f"  Failed: {len(errors)}")
    print("=" * 60)
    
    if errors:
        sys.exit(1)

if __name__ == "__main__":
    run_extraction()
