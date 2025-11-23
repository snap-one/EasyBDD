#!/usr/bin/env python3
"""
Easy BDD Framework Frontend Server Launcher
"""

import os
import sys
import subprocess
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import fastapi
        import uvicorn
        print("✅ All dependencies are installed")
        return True
    except ImportError as e:
        print(f"❌ Missing dependencies: {e}")
        print("Please install dependencies with: pip install -r requirements.txt")
        return False

def start_server():
    """Start the FastAPI server"""
    if not check_dependencies():
        return False
    
    # Change to frontend directory
    frontend_dir = Path(__file__).parent
    os.chdir(frontend_dir)
    
    print("🚀 Starting Easy BDD Framework Web Interface...")
    print("📍 Frontend URL: http://localhost:8000")
    print("📖 API Documentation: http://localhost:8000/docs")
    print("🔧 Admin Interface: http://localhost:8000/redoc")
    print("\n" + "="*50)
    print("Press Ctrl+C to stop the server")
    print("="*50 + "\n")
    
    try:
        # Start uvicorn server
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "app:app", 
            "--host", "0.0.0.0", 
            "--port", "8000", 
            "--reload",
            "--reload-dir", ".",
            "--log-level", "info"
        ], check=True)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error starting server: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = start_server()
    sys.exit(0 if success else 1)