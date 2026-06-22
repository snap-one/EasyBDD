#!/usr/bin/env python3
"""
DEPRECATED — Start the Test Builder Web Application

The web builder is no longer the primary authoring surface.
Author test cases in TestRail instead and run them via:
    python -m easy_bdd testrail-run --project-id <id>
"""

import os
import subprocess
import sys
from pathlib import Path

print(
    "\n[DEPRECATED] The Easy BDD web builder is deprecated.\n"
    "  Author test cases in TestRail and run via:\n"
    "    python -m easy_bdd testrail-run --project-id <id>\n",
    file=sys.stderr,
)

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    print("🚀 Starting Easy BDD Test Builder...")
    print("=" * 60)
    print()
    print("📍 Access the application at: http://localhost:8000")
    print("📚 Documentation: http://localhost:8000/docs")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    print()

    # Change to frontend directory
    os.chdir(Path(__file__).parent)

    # Run uvicorn with keep-alive settings
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "test_builder_app:app",
                "--host",
                "0.0.0.0",  # nosec B104 - Development server binding
                "--port",
                "8000",
                "--reload",
                "--timeout-keep-alive",
                "300",  # Keep connections alive for 5 minutes
                "--timeout-graceful-shutdown",
                "30",  # Graceful shutdown timeout
            ]
        )
    except KeyboardInterrupt:
        print("\n\n✅ Server stopped")
        sys.exit(0)


if __name__ == "__main__":
    main()
