"""Conservative strategy collector.

This module provides a scaffold to collect and store public strategy snippets
for offline review and potential featurization. It does NOT execute or
directly apply scraped strategies. The collector respects robots.txt by
requiring the caller to provide allowed URLs or raw text.
"""
from __future__ import annotations

from pathlib import Path
from typing import List


def store_snippet(source: str, title: str, text: str) -> Path:
    outdir = Path("runtime") / "strategies"
    outdir.mkdir(parents=True, exist_ok=True)
    safe = source.replace("/", "_").replace(":", "_")
    fname = outdir / f"{safe}_{int(__import__('time').time())}.txt"
    with fname.open("w", encoding="utf-8") as f:
        f.write(f"# source: {source}\n# title: {title}\n\n{text}")
    return fname


def list_snippets() -> List[str]:
    outdir = Path("runtime") / "strategies"
    if not outdir.exists():
        return []
    return [str(p) for p in sorted(outdir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)]
