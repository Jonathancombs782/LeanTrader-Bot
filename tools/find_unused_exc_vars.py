"""Scan Python files and report ExceptHandler nodes that bind the name 'e' but never use it
in the except block body. This helps safely renaming unused exception variables to `_e`.

Usage: python tools/find_unused_exc_vars.py [root]
"""
from __future__ import annotations
import ast
import os
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
EXCLUDE = {"venv", "env", ".venv", "__pycache__", "node_modules", "backups"}


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & EXCLUDE)


def name_used_in_nodes(name: str, nodes: list) -> bool:
    for node in ast.walk(ast.Module(body=nodes)):
        if isinstance(node, ast.Name) and node.id == name:
            return True
    return False


for p in sorted(ROOT.rglob("*.py")):
    if should_skip(p):
        continue
    try:
        src = p.read_text(encoding="utf-8")
    except Exception:
        continue
    try:
        tree = ast.parse(src, filename=str(p))
    except Exception:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.name == 'e':
            # Check if name 'e' is referenced in the handler body
            if not name_used_in_nodes('e', node.body):
                # get lineno of the except
                lineno = getattr(node, 'lineno', None)
                print(f"{p}:{lineno}: except Exception as e -> 'e' not used")

