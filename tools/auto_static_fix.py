import ast  # noqa: F401  # intentionally kept
import json
import re
import shutil
import time
from pathlib import Path

# Try import the analyzer from tools/static_check or load by path
try:
    from tools.static_check import analyze_project
except Exception:
    import importlib.util  # noqa: F401  # intentionally kept

    p = Path(__file__).resolve().parent / "static_check.py"
    spec = importlib.util.spec_from_file_location("tools.static_check", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    analyze_project = getattr(mod, "analyze_project")

ROOT = Path(".").resolve()
OUTDIR = Path("runtime")
OUTDIR.mkdir(parents=True, exist_ok=True)


def try_parse(src: str):
    try:
        ast.parse(src)
        return True, None
    except Exception as e:
        return False, str(e)


def safe_autofix_text(path: Path, src: str):
    """Apply conservative text-only heuristics to fix common paste/layout issues."""
    lines = src.splitlines()
    changed = False
    new_lines = []

    # Heuristic 1: remove stray lines that start with a dash indicating a pasted diff line
    for ln in lines:
        if re.match(r"^\s*-\s+", ln):
            changed = True
            continue
        new_lines.append(ln)
    lines = new_lines
    new_lines = []

    # Heuristic 2: if a line contains '.items()' and does not end with ':' add colon
    for ln in lines:
        stripped = ln.rstrip()
        if ".items()" in stripped and not stripped.endswith(":"):
            # avoid adding colon to commented lines
            if not re.match(r"^\s*#", stripped):
                ln = ln + ":"
                changed = True
        new_lines.append(ln)
    src2 = "\n".join(new_lines) + ("\n" if src.endswith("\n") else "")
    return src2, changed


def backup_and_write(path: Path, new_src: str):
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        shutil.copyfile(path, bak)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_src)


def run_autofix(root: Path = ROOT):
    report = {"ts": int(time.time()), "root": str(root), "files": {}}
    rep = analyze_project(str(root))
    for rel, info in rep.get("files", {}).items():
        p = root / rel
        pe = info.get("parse_error")
        if not pe:
            continue
        entry = {"parse_error": pe, "fixed": False, "attempts": []}
        try:
            src = p.read_text(encoding="utf-8")
        except Exception as e:
            entry["attempts"].append({"err": f"read_failed:{e}"})
            report["files"][rel] = entry
            continue

        # attempt heuristics
        new_src, changed = safe_autofix_text(p, src)
        entry["attempts"].append({"heuristic_changed": changed})
        if changed:
            ok, err = try_parse(new_src)
            if ok:
                backup_and_write(p, new_src)
                entry["fixed"] = True
                entry["attempts"].append({"result": "parsed_ok_after_fix"})
            else:
                # try one more pass: add missing colons on common keywords if they look missing
                src_lines = new_src.splitlines()
                for i, ln in enumerate(src_lines):
                    if re.search(r"\b(for|if|while|def|class)\b.*\)\s*$", ln) and not ln.rstrip().endswith(":"):
                        src_lines[i] = ln + ":"
                new_src2 = "\n".join(src_lines) + ("\n" if new_src.endswith("\n") else "")
                ok2, err2 = try_parse(new_src2)
                entry["attempts"].append({"second_pass_ok": ok2, "second_pass_err": err2})
                if ok2:
                    backup_and_write(p, new_src2)
                    entry["fixed"] = True
                else:
                    entry["attempts"].append({"final_parse_error": err2})
        else:
            entry["attempts"].append({"note": "no-heuristic-change"})

        report["files"][rel] = entry

    out = OUTDIR / f"auto_fix_report_{int(time.time())}.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"Auto-fix report written to {out}")
    return out


if __name__ == "__main__":
    run_autofix(ROOT)
