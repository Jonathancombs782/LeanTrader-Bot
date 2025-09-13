"""Child wrapper: print environment and module resolution diagnostics then run a module.

Usage: python -u tools/child_wrapper.py <module.name> [args...]

This is a temporary debugging helper used by the supervisor to capture the
child process' sys.executable, cwd, sys.path[0], and find_spec origins for
critical modules before the actual application code runs.
"""

from __future__ import annotations

import importlib.util
import os
import runpy
import sys


def diag_module(name: str):
    try:
        spec = importlib.util.find_spec(name)
        origin = spec.origin if spec is not None else None
    except Exception:
        origin = None
    return origin


def main():
    if len(sys.argv) < 2:
        print("[child_wrapper] usage: child_wrapper.py <module.name> [args...]")
        return 2

    target = sys.argv[1]
    args = sys.argv[2:]

    try:
        print(f"[child_wrapper] start target={target} pid={os.getpid()}")
        print(
            f"[child_wrapper] exe={getattr(sys, 'executable', None)} cwd={os.getcwd()} sys.path0={sys.path[0] if sys.path else None}"
        )
        # show a few repo files if available
        try:
            repo_root = os.getcwd()
            sample = sorted([f for f in os.listdir(repo_root) if f.endswith(".py")])[:12]
            print(f"[child_wrapper] repo_py_files={sample}")
        except Exception:
            pass

        # write a small sentinel diag file so supervisor logs are not the only evidence
        try:
            diag_dir = os.path.join(repo_root, "runtime", "logs")
            os.makedirs(diag_dir, exist_ok=True)
            diag_file = os.path.join(diag_dir, f"child_wrapper_{target.replace('.', '_')}_{os.getpid()}.diag")
            with open(diag_file, "w", encoding="utf-8") as fh:
                fh.write(f"pid={os.getpid()} exe={getattr(sys, 'executable', None)} cwd={os.getcwd()}\n")
        except Exception:
            pass

        # Ensure repository root is first on sys.path so local modules resolve to the repo files
        try:
            if repo_root not in sys.path:
                sys.path.insert(0, repo_root)
                print(f"[child_wrapper] inserted repo_root into sys.path[0]={sys.path[0]}")
        except Exception:
            pass

        # Evict stray/partially-initialized mt5_adapter modules that may point
        # to different file locations (causes ImportError for members).
        try:
            for candidate in list(sys.modules.keys()):
                if candidate in ("mt5_adapter", "traders_core.mt5_adapter"):
                    mod = sys.modules.get(candidate)
                    try:
                        mfile = getattr(mod, "__file__", None)
                    except Exception:
                        mfile = None
                    # If module exists but file is not in repo_root, evict it so
                    # local file-loader can import the repo copy.
                    if mfile and repo_root and repo_root not in str(mfile):
                        try:
                            del sys.modules[candidate]
                            print(f"[child_wrapper] evicted stray module {candidate} ({mfile})")
                            with open(diag_file, "a", encoding="utf-8") as fh:
                                fh.write(f"evicted {candidate} -> {mfile}\n")
                        except Exception:
                            pass
        except Exception:
            pass

        # Load local .env if available so the child process has the same env vars
        try:
            from dotenv import load_dotenv

            envfile = os.path.join(repo_root, ".env")
            if os.path.exists(envfile):
                load_dotenv(envfile)
                print(f"[child_wrapper] loaded .env from {envfile}")
                # append masked TELEGRAM envs to diag file
                try:
                    with open(diag_file, "a", encoding="utf-8") as fh:
                        bot = os.getenv("TELEGRAM_BOT_TOKEN", "")
                        chat = os.getenv("TELEGRAM_CHAT_ID", "")
                        bot_mask = (bot[:4] + "..." + bot[-4:]) if bot else "<empty>"
                        fh.write(f"TELEGRAM_BOT_TOKEN={bot_mask} CHAT_ID={chat}\n")
                except Exception:
                    pass
        except Exception:
            # dotenv optional; continue
            pass

        # check key module resolution and attempt a diagnostic import for risk_guard to capture errors
        try:
            with open(diag_file, "a", encoding="utf-8") as fh:
                # Check the canonical module names: full target, last name, and common tools.<name>
                names_to_check = [target, target.split(".")[-1], f"tools.{target.split('.')[-1]}"]
                for name in ("mt5_adapter", "risk_guard") + tuple(names_to_check):
                    try:
                        origin = diag_module(name)
                        msg = f"find_spec {name} -> {origin}\n"
                        print(f"[child_wrapper] {msg.strip()}")
                        fh.write(msg)
                    except Exception as _e:
                        msg = f"find_spec {name} -> error: {_e}\n"
                        print(f"[child_wrapper] {msg.strip()}")
                        fh.write(msg)

                # Try importing risk_guard for diagnostics (capture errors but don't stop execution)
                try:
                    import importlib

                    try:
                        rg = importlib.import_module("risk_guard")
                        attrs = [a for a in dir(rg) if not a.startswith("__")]
                        msg = f"import risk_guard ok; public attrs={attrs}\n"
                        print(f"[child_wrapper] {msg.strip()}")
                        fh.write(msg)
                    except Exception as _ie:
                        msg = f"import risk_guard -> exception: {_ie}\n"
                        print(f"[child_wrapper] {msg.strip()}")
                        fh.write(msg)
                except Exception:
                    # ignore importlib errors; already printed
                    pass
        except Exception:
            # If writing diag file fails, continue; we already printed to stdout
            pass

        # Set sys.argv for the module and run it as __main__.
        sys.argv = [target] + args
        # Prefer running by module name, but if the module isn't importable try the repo-relative file.
        try:
            if importlib.util.find_spec(target) is not None:
                runpy.run_module(target, run_name="__main__", alter_sys=True)
                return 0
            # attempt file fallback: convert dotted name to path and run file
            candidate = os.path.join(repo_root, *target.split(".")) + ".py"
            if os.path.exists(candidate):
                print(f"[child_wrapper] running fallback file {candidate}")
                with open(diag_file, "a", encoding="utf-8") as fh:
                    fh.write(f"fallback_file {candidate}\n")
                runpy.run_path(candidate, run_name="__main__")
                return 0
            # final attempt: try running last-name module (e.g., continuous_demo.py)
            last_name = target.split(".")[-1]
            candidate2 = os.path.join(repo_root, last_name + ".py")
            if os.path.exists(candidate2):
                print(f"[child_wrapper] running fallback file {candidate2}")
                with open(diag_file, "a", encoding="utf-8") as fh:
                    fh.write(f"fallback_file {candidate2}\n")
                runpy.run_path(candidate2, run_name="__main__")
                return 0
            # otherwise try import normally to surface the ImportError
            runpy.run_module(target, run_name="__main__", alter_sys=True)
            return 0
        except Exception:
            # let the outer exception handler print the error and re-raise
            raise
    except SystemExit as se:
        # propagate explicit exits
        print(f"[child_wrapper] exit status {se.code}")
        raise
    except Exception as _e:
        print(f"[child_wrapper] exception before module exec: {_e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
