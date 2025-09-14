import os
import py_compile
import sys


def should_prune_dir(parent: str, dirname: str) -> bool:
    """Return True if this directory should be skipped.

    - Skip virtualenvs and caches: .venv, __pycache__
    - Skip incoming bundles: _incoming
    - Skip runtime backups: runtime/backups
    Works cross-platform by checking names rather than raw paths.
    """
    if dirname in {".venv", "__pycache__", "_incoming"}:
        return True
    # Specifically avoid descending into runtime/backups
    if dirname == "backups" and os.path.basename(parent) == "runtime":
        return True
    return False


bad = []
for root, dirs, files in os.walk(".", topdown=True):
    # Prune directories in-place so os.walk doesn't descend into them
    dirs[:] = [d for d in dirs if not should_prune_dir(root, d)]

    for f in files:
        if f.endswith(".py"):
            path = os.path.join(root, f)
            try:
                py_compile.compile(path, doraise=True)
            except Exception as e:
                print("ERR", path, e)
                bad.append((path, str(e)))
print("done, errors:", len(bad))
if bad:
    sys.exit(2)
