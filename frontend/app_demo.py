"""
FastAPI backend for Easy BDD Framework Web Interface (Standalone Demo)
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="Easy BDD Framework",
    description="Modern web interface for the Easy BDD testing framework",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class TestRequest(BaseModel):
    test_path: str
    tags: Optional[List[str]] = None
    headless: bool = True
    export_format: Optional[str] = None

class TestFileContent(BaseModel):
    name: str
    description: str
    content: str

class ConfigUpdate(BaseModel):
    config: Dict[str, Any]

# Global variables for demo
running_tests: Dict[str, Dict] = {}
test_results: Dict[str, Any] = {}

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the main HTML page"""
    html_path = Path(__file__).parent / "static" / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse(content="<h1>Easy BDD Frontend</h1><p>HTML file not found</p>")

@app.get("/api/tests")
async def get_tests():
    """Get all available test files"""
    try:
        test_dir = Path("../tests/cases")
        tests = []
        
        if not test_dir.exists():
            # Return some sample data for demo
            return {
                "tests": [
                    {
                        "path": "tests/cases/demo_test.yaml",
                        "name": "Demo Test",
                        "description": "Sample test for demonstration",
                        "tags": ["demo", "sample"],
                        "size": 1024,
                        "modified": datetime.now().isoformat()
                    }
                ],
                "total": 1
            }
        
        for test_file in test_dir.glob("**/*.yaml"):
            tests.append({
                "path": str(test_file.relative_to(Path("../"))),
                "name": test_file.stem.replace("_", " ").title(),
                "description": "Test file",
                "tags": ["test"],
                "size": test_file.stat().st_size if test_file.exists() else 0,
                "modified": datetime.fromtimestamp(test_file.stat().st_mtime).isoformat() if test_file.exists() else datetime.now().isoformat()
            })
        
        return {"tests": tests, "total": len(tests)}
    except Exception as e:
        return {"tests": [], "total": 0, "error": str(e)}

@app.get("/api/tests/{test_path:path}")
async def get_test_content(test_path: str):
    """Get content of a specific test file"""
    try:
        full_path = Path(f"../{test_path}")
        if not full_path.exists():
            # Return sample content
            sample_content = '''name: "Sample Test"
description: "A sample test file for demonstration"
tags: ["demo", "sample"]

variables:
  app_url: "https://example.com"

steps:
  - action: Open browser
    url: "${app_url}"
    description: "Open the application"
    
  - action: Take screenshot
    name: "homepage"
    description: "Capture the homepage"
'''
            return {
                "path": test_path,
                "content": sample_content,
                "size": len(sample_content),
                "modified": datetime.now().isoformat()
            }
        
        with open(full_path, 'r') as f:
            content = f.read()
        
        return {
            "path": test_path,
            "content": content,
            "size": full_path.stat().st_size,
            "modified": datetime.fromtimestamp(full_path.stat().st_mtime).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tests/{test_path:path}")
async def save_test_content(test_path: str, test_content: TestFileContent):
    """Save content to a test file"""
    try:
        full_path = Path(f"../{test_path}")
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(full_path, 'w') as f:
            f.write(test_content.content)
        
        return {
            "message": "Test file saved successfully",
            "path": test_path,
            "size": full_path.stat().st_size
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tests/run")
async def run_tests(test_request: TestRequest, background_tasks: BackgroundTasks):
    """Run tests asynchronously (demo version)"""
    try:
        test_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Store test run info
        running_tests[test_id] = {
            "status": "running",
            "started": datetime.now().isoformat(),
            "test_path": test_request.test_path,
            "tags": test_request.tags,
            "progress": 0
        }
        
        # Simulate test execution
        background_tasks.add_task(simulate_test_execution, test_id, test_request)
        
        return {
            "test_id": test_id,
            "message": "Test execution started (demo mode)",
            "status": "running"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def simulate_test_execution(test_id: str, test_request: TestRequest):
    """Simulate test execution for demo purposes"""
    import asyncio
    
    try:
        # Simulate progress
        for progress in [10, 30, 50, 70, 90, 100]:
            running_tests[test_id]["progress"] = progress
            if progress < 100:
                running_tests[test_id]["status"] = "running"
                await asyncio.sleep(2)  # Simulate work
            else:
                running_tests[test_id]["status"] = "completed"
        
        # Store final results
        test_results[test_id] = {
            "test_id": test_id,
            "status": "completed",
            "completed": datetime.now().isoformat(),
            "results": {
                "overall_status": "PASSED",
                "execution_time_seconds": 10.5,
                "tests_passed": 1,
                "tests_failed": 0,
                "tests_skipped": 0
            }
        }
        
    except Exception as e:
        running_tests[test_id]["status"] = "failed"
        running_tests[test_id]["error"] = str(e)

@app.get("/api/tests/status/{test_id}")
async def get_test_status(test_id: str):
    """Get status of a running test"""
    if test_id not in running_tests:
        raise HTTPException(status_code=404, detail="Test run not found")
    
    return running_tests[test_id]

@app.get("/api/tests/results/{test_id}")
async def get_test_results(test_id: str):
    """Get results of a completed test"""
    if test_id not in test_results:
        raise HTTPException(status_code=404, detail="Test results not found")
    
    return test_results[test_id]

@app.get("/api/tests/results")
async def get_all_test_results():
    """Get all test results"""
    return {
        "results": list(test_results.values()),
        "total": len(test_results)
    }

@app.get("/api/config")
async def get_config():
    """Get current framework configuration"""
    return {
        "browser": {
            "default": "chrome",
            "headless": False,
            "timeout": 30,
            "window_size": [1920, 1080]
        },
        "api": {
            "timeout": 30,
            "verify_ssl": True,
            "max_retries": 3
        },
        "environments": {
            "default": {},
            "staging": {
                "base_url": "https://staging.example.com"
            }
        }
    }

@app.post("/api/config")
async def update_config(config_update: ConfigUpdate):
    """Update framework configuration"""
    return {"message": "Configuration updated successfully (demo mode)"}

@app.get("/api/screenshots")
async def get_screenshots():
    """Get list of available screenshots"""
    return {
        "screenshots": [
            {
                "filename": "sample_screenshot.png",
                "path": "/screenshots/sample_screenshot.png",
                "size": 125489,
                "created": datetime.now().isoformat()
            }
        ],
        "total": 1
    }

@app.get("/api/screenshots/{filename}")
async def get_screenshot(filename: str):
    """Serve a screenshot file"""
    # Return a placeholder for demo
    raise HTTPException(status_code=404, detail="Screenshot not available in demo mode")

@app.post("/api/tests/upload")
async def upload_test_file(file: UploadFile = File(...)):
    """Upload a new test file"""
    try:
        content = await file.read()
        filename = file.filename
        
        if not filename.endswith(('.yaml', '.yml', '.json')):
            raise HTTPException(status_code=400, detail="Only YAML and JSON files are allowed")
        
        upload_path = Path(f"../tests/cases/{filename}")
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(upload_path, 'wb') as f:
            f.write(content)
        
        return {
            "message": "File uploaded successfully",
            "filename": filename,
            "path": str(upload_path.relative_to(Path("../"))),
            "size": len(content)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/system/info")
async def get_system_info():
    """Get system information and framework status"""
    return {
        "framework_version": "1.0.0",
        "available_browsers": ["chrome", "firefox", "edge", "webkit"],
        "test_directories": ["tests/cases", "tests/web_ui"],
        "running_tests": len([t for t in running_tests.values() if t["status"] == "running"]),
        "total_results": len(test_results),
        "demo_mode": True
    }

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)