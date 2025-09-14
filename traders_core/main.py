from __future__ import annotations

import os  # noqa: F401  # intentionally kept

from dotenv import load_dotenv

load_dotenv()
MODE = os.getenv("MODE", "api").lower()  # api | loop

if MODE == "api":
    import uvicorn  # noqa: E402

    uvicorn.run(
        "traders_core.api.app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        reload=False,
    )
else:
    from traders_core.orchestration.jobs import run_forever  # noqa: E402

    run_forever()
