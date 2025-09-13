"""Helper to start the webhook server with .env loaded."""

import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(".env")

# Make repo root importable so `import runtime.webhook_server` works
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("runtime.webhook_server:app", host="0.0.0.0", port=8080, log_level="info")
