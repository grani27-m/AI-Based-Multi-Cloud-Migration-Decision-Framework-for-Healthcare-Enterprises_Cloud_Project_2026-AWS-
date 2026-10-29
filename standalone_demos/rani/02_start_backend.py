"""
02 - Start the backend API (and the prebuilt React dashboard) on http://127.0.0.1:8000

    python 02_start_backend.py                # Ctrl+C to stop; data stays in runtime/app.db
    python 02_start_backend.py --port 8010

API docs: http://127.0.0.1:8000/docs · dashboard: http://127.0.0.1:8000 · health: /health, /ready, /metrics
"""

from __future__ import annotations

import argparse

from demo_common import load_env, require_env


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    load_env()
    require_env("SECRET_KEY")
    import uvicorn

    uvicorn.run("backend.app:create_app", factory=True, host=a.host, port=a.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
