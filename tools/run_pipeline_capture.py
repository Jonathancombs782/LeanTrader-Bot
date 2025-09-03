"""Run the pipeline.run_pipeline() and print structured output for capture."""
from __future__ import annotations

import os
import sys
import traceback

# ensure project root on sys.path
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

def main():
    # force the env flags to true for a full end-to-end run
    import os
    os.environ['ENABLE_LEARNING'] = 'true'
    os.environ['ENABLE_CRAWL'] = 'true'
    try:
        from tools.pipeline import run_pipeline
    except Exception as e:
        # write import failure to pipeline_run.txt as well
        msg = f'IMPORT pipeline failed: {e}\n'
        print(msg)
        traceback.print_exc()
        try:
            lp = Path('runtime') / 'logs' / 'pipeline_run.txt'
            lp.parent.mkdir(parents=True, exist_ok=True)
            with lp.open('a', encoding='utf-8') as lf:
                lf.write(msg)
        except Exception:
            pass
        return 2

    lp = Path('runtime') / 'logs' / 'pipeline_run.txt'
    lp.parent.mkdir(parents=True, exist_ok=True)
    try:
        # run pipeline and capture return code
        rc = run_pipeline()
        msg = f'PIPELINE_RETURN_CODE: {rc}\n'
        print(msg)
        with lp.open('a', encoding='utf-8') as lf:
            lf.write(msg)
        return int(rc or 0)
    except Exception as e:
        msg = f'PIPELINE_EXCEPTION: {e}\n'
        print(msg)
        traceback.print_exc()
        try:
            with lp.open('a', encoding='utf-8') as lf:
                lf.write(msg)
                import traceback as _tb
                lf.write(_tb.format_exc())
        except Exception:
            pass
        return 3


if __name__ == '__main__':
    rc = main()
    sys.exit(rc)
