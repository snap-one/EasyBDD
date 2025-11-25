#!/usr/bin/env python3
"""
Start the Test Builder Web Application
"""

import sys
import os
import subprocess
from pathlib import Path

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
    
    # Run uvicorn
    try:
        subprocess.run([
            sys.executable,
            "-m",
            "uvicorn",
            "test_builder_app:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload"
        ])
    except KeyboardInterrupt:
        print("\n\n✅ Server stopped")
        sys.exit(0)

if __name__ == "__main__":
    main()
