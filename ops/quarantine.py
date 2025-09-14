from __future__ import annotations

from typing import Dict, List, Tuple


def should_quarantine(validation: Dict[str, object], max_issues: int = 3) -> Tuple[bool, List[str]]:
    try:
        ok = bool(validation.get("ok", False))
        issues = list(validation.get("issues", []) or [])
        if not ok:
            return True, issues
        if len(issues) >= int(max_issues):
            return True, issues
        return False, issues
    except Exception:
        return True, ["validation_parse_error"]


__all__ = ["should_quarantine"]

