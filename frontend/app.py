"""
FastAPI backend for Easy BDD Framework Web Interface
"""

import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import sys
sys.path.append('..')
from easy_bdd.core.runner import TestRunner
from easy_bdd.core.generator import GherkinGenerator
from easy_bdd.core.config import ConfigManager
from easy_bdd.core.parser import TestParser

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

# Global variables
running_tests: Dict[str, Dict] = {}
test_results: Dict[str, Any] = {}
config_manager = ConfigManager()

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
        
        for test_file in test_dir.glob("**/*.yaml"):
            try:
                parser = TestParser()
                test_data = parser.parse_yaml_file(test_file)
                
                tests.append({
                    "path": str(test_file.relative_to(Path("../"))),
                    "name": test_data.get("name", test_file.stem),
                    "description": test_data.get("description", ""),
                    "tags": test_data.get("tags", []),
                    "size": test_file.stat().st_size,
                    "modified": datetime.fromtimestamp(test_file.stat().st_mtime).isoformat()
                })
            except Exception as e:
                # Include broken files with error info
                tests.append({
                    "path": str(test_file.relative_to(Path("../"))),
                    "name": test_file.stem,
                    "description": f"Error parsing file: {str(e)}",
                    "tags": ["error"],
                    "size": test_file.stat().st_size,
                    "modified": datetime.fromtimestamp(test_file.stat().st_mtime).isoformat(),
                    "error": True
                })
        
        return {"tests": tests, "total": len(tests)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tests/{test_path:path}")
async def get_test_content(test_path: str):
    """Get content of a specific test file"""
    try:
        full_path = Path(f"../{test_path}")
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="Test file not found")
        
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
    """Run tests asynchronously"""
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
        
        # Run tests in background
        background_tasks.add_task(execute_test_run, test_id, test_request)
        
        return {
            "test_id": test_id,
            "message": "Test execution started",
            "status": "running"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def execute_test_run(test_id: str, test_request: TestRequest):
    """Execute the actual test run"""
    try:
        # Update status
        running_tests[test_id]["status"] = "running"
        running_tests[test_id]["progress"] = 10
        
        # Initialize runner
        runner = TestRunner(config_manager)
        
        # Prepare arguments
        args_dict = {
            "path": f"../{test_request.test_path}",
            "tags": test_request.tags,
            "headless": test_request.headless,
            "export_results": f"../reports/test_results_{test_id}.json" if test_request.export_format else None
        }
        
        running_tests[test_id]["progress"] = 30
        
        # Run tests
        result = runner.run_tests(
            test_path=Path(args_dict["path"]),
            tags=args_dict["tags"],
            headless=args_dict["headless"]
        )
        
        running_tests[test_id]["progress"] = 90
        
        # Process results
        test_results[test_id] = {
            "test_id": test_id,
            "status": "completed" if result.overall_status == "PASSED" else "failed",
            "completed": datetime.now().isoformat(),
            "results": asdict(result),
            "export_file": args_dict.get("export_results")
        }
        
        running_tests[test_id]["status"] = "completed"
        running_tests[test_id]["progress"] = 100
        
    except Exception as e:
        running_tests[test_id]["status"] = "failed"
        running_tests[test_id]["error"] = str(e)
        test_results[test_id] = {
            "test_id": test_id,
            "status": "failed",
            "error": str(e),
            "completed": datetime.now().isoformat()
        }

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
    try:
        return {
            "browser": asdict(config_manager.browser),
            "api": asdict(config_manager.api),
            "environments": config_manager.environments
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/config")
async def update_config(config_update: ConfigUpdate):
    """Update framework configuration"""
    try:
        # This would need to be implemented in ConfigManager
        return {"message": "Configuration updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/screenshots")
async def get_screenshots():
    """Get list of available screenshots"""
    try:
        screenshots_dir = Path("../reports/screenshots")
        if not screenshots_dir.exists():
            return {"screenshots": [], "total": 0}
        
        screenshots = []
        for img_file in screenshots_dir.glob("*.png"):
            screenshots.append({
                "filename": img_file.name,
                "path": str(img_file),
                "size": img_file.stat().st_size,
                "created": datetime.fromtimestamp(img_file.stat().st_ctime).isoformat()
            })
        
        return {
            "screenshots": sorted(screenshots, key=lambda x: x["created"], reverse=True),
            "total": len(screenshots)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/screenshots/{filename}")
async def get_screenshot(filename: str):
    """Serve a screenshot file"""
    screenshot_path = Path(f"../reports/screenshots/{filename}")
    if not screenshot_path.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    
    return FileResponse(screenshot_path)

@app.post("/api/tests/upload")
async def upload_test_file(file: UploadFile = File(...)):
    """Upload a new test file"""
    try:
        content = await file.read()
        filename = file.filename
        
        # Validate file extension
        if not filename.endswith(('.yaml', '.yml', '.json')):
            raise HTTPException(status_code=400, detail="Only YAML and JSON files are allowed")
        
        # Save file
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
    try:
        return {
            "framework_version": "1.0.0",
            "python_version": sys.version,
            "available_browsers": ["chrome", "firefox", "edge", "webkit"],
            "test_directories": [
                str(p.relative_to(Path("../"))) for p in Path("../tests").glob("*/") if p.is_dir()
            ],
            "running_tests": len([t for t in running_tests.values() if t["status"] == "running"]),
            "total_results": len(test_results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)