"""
Phase 0 — Corpus Registry Package
===================================
Exports the manifest loader for use by downstream phases (Phase 1, 3, etc.)
"""

from .validate_urls import load_manifest, save_manifest, MANIFEST_PATH, ALLOWED_DOMAIN

__all__ = ["load_manifest", "save_manifest", "MANIFEST_PATH", "ALLOWED_DOMAIN"]
