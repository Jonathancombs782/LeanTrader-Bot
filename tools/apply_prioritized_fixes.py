from __future__ import annotations

"""
Small script to apply two low-risk repo-wide fixes:
- Replace bare `except:` with `except Exception:` (unless it's already `except Exception` or `except BaseException`)
- For files that call `load_dotenv()` before local imports, append `# noqa: E402` to import lines after the call to silence E402

Backs up files with a .bak extension before modifying.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY_FILES = [p for p in ROOT.rglob("*.py") if "site-packages" not in str(p) and ".venv" not in str(p)]

except_pattern = re.compile(r"^([ \t]*)except\s*:\s*(#.*)?$", flags=re.MULTILINE)

for p in PY_FILES:
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        continue
    new_text = text

    # 1) Replace bare except: with except Exception: (skip lines that already contain Exception or BaseException)
    def except_repl(m):
        # if 'except Exception' already present nearby, skip
        # we matched only bare 'except:', so safe to replace
        indent = m.group(1)
        comment = m.group(2) or ""
        return f"{indent}except Exception:{('  ' + comment.strip()) if comment else ''}"

    new_text = except_pattern.sub(except_repl, new_text)

    # 2) If load_dotenv() appears before import lines, append # noqa: E402 to those import lines
    if "load_dotenv()" in new_text:
        # find position of load_dotenv
        ld_idx = new_text.find("load_dotenv()")
        # split into lines and operate on those after the load_dotenv line
        lines = new_text.splitlines()
        # compute which line contains load_dotenv()
        ld_line_index = None
        for i, L in enumerate(lines):
            if "load_dotenv()" in L:
                ld_line_index = i
                break
        if ld_line_index is not None:
            changed = False
            for i in range(ld_line_index + 1, len(lines)):
                line = lines[i]
                stripped = line.lstrip()
                if stripped.startswith("import ") or stripped.startswith("from "):
                    if "# noqa: E402" not in line:
                        lines[i] = line + "  # noqa: E402"
            new_text = "\n".join(lines)

    if new_text != text:
        try:
            p.with_suffix(p.suffix + ".bak").write_text(text, encoding="utf-8")
            p.write_text(new_text, encoding="utf-8")
        except Exception:
            pass

print("Done")
