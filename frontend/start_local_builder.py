#!/usr/bin/env python3
"""Launcher for the Easy BDD Local Test Builder.

Usage:
    python frontend/start_local_builder.py [--port 9093] [--host 0.0.0.0]

No TestRail credentials required — cases, shared steps, and variables are
stored as local YAML files under LOCAL_BUILDER_TESTS_DIR (default:
tests/cases).
"""

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Easy BDD Local Test Builder")
    parser.add_argument("--port", type=int, default=int(os.getenv("LOCAL_BUILDER_PORT", "9093")))
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    import uvicorn

    from local_builder import app

    print(f"Easy BDD Local Test Builder → http://{args.host}:{args.port}/")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
