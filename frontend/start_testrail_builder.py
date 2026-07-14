#!/usr/bin/env python3
"""Launcher for the Easy BDD TestRail Test Builder.

Usage:
    python frontend/start_testrail_builder.py [--port 8091] [--host 0.0.0.0]

Requires TESTRAIL_URL / TESTRAIL_USERNAME / TESTRAIL_API_KEY in the project
.env (same credentials the runner uses).
"""

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the TestRail Test Builder")
    parser.add_argument("--port", type=int, default=int(os.getenv("BUILDER_PORT", "8091")))
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    import uvicorn

    from testrail_builder import app

    print(f"Easy BDD TestRail Test Builder → http://{args.host}:{args.port}/")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
