import traceback
import sys
from pathlib import Path

# Ensure project root on sys.path when running from tools/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import mt5_adapter

    print("OK:", mt5_adapter.__file__)
    print("has min_stop_distance_points=", hasattr(mt5_adapter, "min_stop_distance_points"))
except Exception:
    traceback.print_exc()
