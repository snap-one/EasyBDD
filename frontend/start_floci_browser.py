#!/usr/bin/env python3
"""Launcher for the Easy BDD Floci Browser.

Usage:
    python frontend/start_floci_browser.py [--port 8092] [--host 0.0.0.0]

Talks to the Floci endpoint resolved by FlociService (FLOCI_ENDPOINT_URL in
the project .env or environment, default http://localhost:4566).
"""

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Floci Browser")
    parser.add_argument("--port", type=int, default=int(os.getenv("FLOCI_BROWSER_PORT", "8092")))
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    import uvicorn

    from floci_browser import app

    print(f"Easy BDD Floci Browser -> http://{args.host}:{args.port}/")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
