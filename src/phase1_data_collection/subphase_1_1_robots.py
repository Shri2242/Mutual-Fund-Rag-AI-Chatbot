"""
Subphase 1.1 — robots.txt Compliance Check
==========================================
Verifies that the target URLs from the corpus manifest are allowed
to be scraped according to the site's robots.txt.
"""

import json
import os
import sys
import urllib.robotparser
from urllib.parse import urlparse
import requests

class RobotsBlocked(Exception):
    """Exception raised when robots.txt disallows scraping."""
    pass

def check_robots_compliance(urls: list[str], user_agent: str = "*") -> str:
    """
    Verifies that robots.txt permits scraping of the given URLs.
    
    Args:
        urls: List of URLs to check.
        user_agent: The user agent string to use for checking compliance.
        
    Returns:
        'allowed' if all URLs are permitted, otherwise raises RobotsBlocked.
    """
    if not urls:
        return "allowed"
        
    # Group URLs by domain to minimize robots.txt fetches
    domains = {}
    for url in urls:
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        if base_url not in domains:
            domains[base_url] = []
        domains[base_url].append(url)
        
    for base_url, domain_urls in domains.items():
        robots_url = f"{base_url}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        
        try:
            print(f"[*] Fetching {robots_url}...")
            # We use requests to fetch so we can set a timeout and handle errors gracefully
            response = requests.get(robots_url, timeout=10, headers={"User-Agent": user_agent})
            if response.status_code == 200:
                rp.parse(response.text.splitlines())
            else:
                print(f"[-] Could not fetch {robots_url} (HTTP {response.status_code}). Assuming allowed.")
                continue
        except requests.RequestException as e:
            print(f"[-] Error fetching {robots_url}: {e}. Assuming allowed.")
            continue
            
        for url in domain_urls:
            # Check compliance
            if not rp.can_fetch(user_agent, url):
                print(f"[X] Blocked by robots.txt: {url}")
                raise RobotsBlocked(f"Path disallowed by {robots_url} for {url}")
            print(f"[+] Allowed by robots.txt: {url}")
            
    return "allowed"

def main():
    # Load URLs from Phase 0 manifest
    manifest_path = os.path.join(
        os.path.dirname(__file__), "..", "phase0_corpus_registry", "corpus_manifest.json"
    )
    
    if not os.path.exists(manifest_path):
        print(f"[ERROR] Manifest not found at {manifest_path}")
        sys.exit(1)
        
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
        
    urls = [entry["url"] for entry in manifest.get("corpus_urls", [])]
    
    print("=" * 60)
    print("  Subphase 1.1 — robots.txt Compliance Check")
    print("=" * 60)
    
    try:
        # We check with a standard user-agent or '*'
        result = check_robots_compliance(urls, user_agent="*")
        print(f"\nFinal Result: {result}")
        print("=" * 60)
    except RobotsBlocked as e:
        print(f"\n[!] Final Result: blocked")
        print(f"[!] {e}")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()
