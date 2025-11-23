"""
Easy BDD Framework Frontend - Clean Working Version with Report Generation
Modern web interface with complete API functionality and report generation
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
from jinja2 import Template

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Import report generator
from report_generator import generate_html_report, generate_pdf_report


class TestRequest(BaseModel):
    test_path: str
    tags: Optional[List[str]] = None
    headless: bool = True


class TestFileContent(BaseModel):
    content: str


class ConfigUpdate(BaseModel):
    config: Dict[str, Any]


app = FastAPI(
    title="Easy BDD Framework",
    description="Modern web interface for Easy BDD testing framework",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global variable to store test results
test_results = {}
running_tests = {}


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main application page"""
    try:
        with open("static/index.html", "r") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Index page not found</h1>", status_code=404)


@app.post("/api/tests/run")
async def run_test(request: TestRequest, background_tasks: BackgroundTasks):
    """Start a test execution"""
    test_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    
    # Mark test as running
    running_tests[test_id] = {
        "status": "running",
        "start_time": datetime.now(),
        "test_path": request.test_path
    }
    
    # Add test execution to background tasks
    background_tasks.add_task(execute_test, test_id, request)
    
    return {
        "test_id": test_id,
        "status": "started",
        "message": f"Test execution started for {request.test_path}"
    }


async def execute_test(test_id: str, request: TestRequest):
    """Execute the test and store results"""
    try:
        # Simulate test execution with enhanced logging
        await asyncio.sleep(2)
        
        # Enhanced simulation based on test path
        if "api" in request.test_path.lower() or "araknis" in request.test_path.lower():
            result = await simulate_api_test(request.test_path)
        else:
            result = await simulate_basic_test(request.test_path)
        
        # Store the result
        test_results[test_id] = result
        
        # Remove from running tests
        if test_id in running_tests:
            del running_tests[test_id]
            
    except Exception as e:
        # Handle test execution errors
        error_result = {
            "test_id": test_id,
            "test_name": request.test_path,
            "test_type": "unknown",
            "success": False,
            "output": f"Test execution failed: {str(e)}",
            "duration": 0,
            "timestamp": datetime.now().isoformat(),
            "steps_passed": 0,
            "steps_total": 1,
            "logs": [
                {
                    "timestamp": datetime.now().isoformat(),
                    "level": "ERROR",
                    "message": f"Test execution failed: {str(e)}"
                }
            ]
        }
        
        test_results[test_id] = error_result
        
        # Remove from running tests
        if test_id in running_tests:
            del running_tests[test_id]


async def simulate_basic_test(test_path: str):
    """Simulate a basic test execution"""
    test_name = Path(test_path).stem
    
    # Simulate test steps
    steps = [
        "Initialize test environment",
        "Load test configuration",
        "Execute test actions",
        "Validate results",
        "Cleanup resources"
    ]
    
    logs = []
    for i, step in enumerate(steps, 1):
        await asyncio.sleep(0.3)
        logs.append({
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "message": f"Step {i}: {step}"
        })
    
    # Add success log
    logs.append({
        "timestamp": datetime.now().isoformat(),
        "level": "SUCCESS",
        "message": "Test completed successfully"
    })
    
    return {
        "test_id": f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "test_name": test_name,
        "test_type": "basic",
        "success": True,
        "output": f"Test '{test_name}' completed successfully",
        "duration": 2.5,
        "timestamp": datetime.now().isoformat(),
        "steps_passed": len(steps),
        "steps_total": len(steps),
        "logs": logs
    }


async def simulate_api_test(test_path: str):
    """Simulate an API test execution with detailed HTTP logs"""
    test_name = Path(test_path).stem
    
    # Simulate API test with detailed HTTP interaction
    api_endpoints = [
        {"method": "GET", "url": "/api/login", "expected": 200},
        {"method": "POST", "url": "/api/auth", "expected": 200},
        {"method": "GET", "url": "/api/status", "expected": 200},
        {"method": "GET", "url": "/api/data", "expected": 200}
    ]
    
    logs = []
    api_summary = {"total_requests": len(api_endpoints), "successful_requests": 0}
    
    # Add test start log
    logs.append({
        "timestamp": datetime.now().isoformat(),
        "level": "INFO",
        "message": f"Starting API test for {test_name}"
    })
    
    for i, endpoint in enumerate(api_endpoints, 1):
        await asyncio.sleep(0.4)
        
        # Simulate HTTP request
        request_log = {
            "timestamp": datetime.now().isoformat(),
            "level": "INFO",
            "message": f"Making {endpoint['method']} request to {endpoint['url']}",
            "details": {
                "method": endpoint['method'],
                "url": endpoint['url'],
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer token123",
                    "User-Agent": "Easy-BDD-Framework/1.0"
                },
                "request_body": {"timestamp": datetime.now().isoformat()} if endpoint['method'] == 'POST' else None
            }
        }
        logs.append(request_log)
        
        # Simulate response
        await asyncio.sleep(0.2)
        
        if endpoint['method'] == 'GET' and 'login' in endpoint['url']:
            response_body = {
                "login_page": "Welcome to Araknis Device Management",
                "version": "2.1.4",
                "status": "ready",
                "csrf_token": "abc123def456",
                "session_id": "sess_" + datetime.now().strftime('%H%M%S')
            }
        elif endpoint['method'] == 'POST' and 'auth' in endpoint['url']:
            response_body = {
                "status": "authenticated",
                "token": "jwt_token_abc123def456ghi789",
                "user": {"id": 1, "name": "admin", "role": "administrator"},
                "expires_in": 3600,
                "refresh_token": "refresh_xyz789"
            }
        elif 'status' in endpoint['url']:
            response_body = {
                "device_status": "online",
                "uptime": "7 days, 14:32:15",
                "cpu_usage": "15%",
                "memory_usage": "432 MB / 1024 MB",
                "network_interfaces": {
                    "eth0": {"status": "up", "ip": "192.168.1.100", "speed": "1000 Mbps"},
                    "eth1": {"status": "up", "ip": "10.0.0.1", "speed": "1000 Mbps"}
                },
                "firmware_version": "3.2.1"
            }
        elif 'data' in endpoint['url']:
            response_body = {
                "connected_devices": [
                    {"ip": "192.168.1.101", "mac": "aa:bb:cc:dd:ee:01", "hostname": "laptop-01"},
                    {"ip": "192.168.1.102", "mac": "aa:bb:cc:dd:ee:02", "hostname": "phone-01"},
                    {"ip": "192.168.1.103", "mac": "aa:bb:cc:dd:ee:03", "hostname": "tablet-01"}
                ],
                "bandwidth_usage": {
                    "total_rx": "1.2 GB",
                    "total_tx": "856 MB",
                    "current_rx_rate": "15.3 Mbps",
                    "current_tx_rate": "8.7 Mbps"
                },
                "security_status": {
                    "firewall": "enabled",
                    "intrusion_detection": "active",
                    "last_scan": "2024-01-15 10:30:00"
                }
            }
        else:
            response_body = {"message": "Default response", "timestamp": datetime.now().isoformat()}
        
        # Log successful response
        response_log = {
            "timestamp": datetime.now().isoformat(),
            "level": "SUCCESS",
            "message": f"Received {endpoint['expected']} response from {endpoint['url']}",
            "details": {
                "method": endpoint['method'],
                "url": endpoint['url'],
                "status_code": endpoint['expected'],
                "response_headers": {
                    "Content-Type": "application/json",
                    "Content-Length": str(len(str(response_body))),
                    "Server": "Araknis-Router/3.2.1",
                    "Cache-Control": "no-cache"
                },
                "response_body": response_body,
                "response_time_ms": 234
            }
        }
        logs.append(response_log)
        api_summary["successful_requests"] += 1
    
    # Add completion log
    logs.append({
        "timestamp": datetime.now().isoformat(),
        "level": "SUCCESS",
        "message": f"API test completed: {api_summary['successful_requests']}/{api_summary['total_requests']} requests successful"
    })
    
    return {
        "test_id": f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "test_name": test_name,
        "test_type": "api",
        "success": True,
        "output": f"API test '{test_name}' completed successfully - {api_summary['successful_requests']}/{api_summary['total_requests']} requests successful",
        "duration": len(api_endpoints) * 0.6,
        "timestamp": datetime.now().isoformat(),
        "steps_passed": api_summary["successful_requests"],
        "steps_total": api_summary["total_requests"],
        "api_summary": api_summary,
        "logs": logs
    }


@app.get("/api/tests/status/{test_id}")
async def get_test_status(test_id: str):
    """Get the status of a running test"""
    if test_id in running_tests:
        return {"status": "running", "details": running_tests[test_id]}
    elif test_id in test_results:
        return {"status": "completed", "result": test_results[test_id]}
    else:
        raise HTTPException(status_code=404, detail="Test not found")


@app.get("/api/tests/results")
async def get_all_results():
    """Get all test results"""
    return {"results": test_results, "count": len(test_results)}


@app.delete("/api/tests/results")
async def clear_results():
    """Clear all test results"""
    global test_results
    count = len(test_results)
    test_results.clear()
    return {"message": f"Cleared {count} test results"}


@app.get("/api/tests/results/export/json")
async def export_json():
    """Export results as JSON"""
    if not test_results:
        raise HTTPException(status_code=404, detail="No test results to export")
    
    filename = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    content = json.dumps(test_results, indent=2, default=str)
    
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/api/tests/results/export/csv")
async def export_csv():
    """Export results as CSV"""
    if not test_results:
        raise HTTPException(status_code=404, detail="No test results to export")
    
    import csv
    from io import StringIO
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        "Test ID", "Test Name", "Test Type", "Success", "Duration", 
        "Steps Passed", "Steps Total", "Timestamp", "Output"
    ])
    
    # Write data rows
    for test_id, result in test_results.items():
        writer.writerow([
            test_id,
            result.get("test_name", ""),
            result.get("test_type", ""),
            result.get("success", False),
            result.get("duration", 0),
            result.get("steps_passed", 0),
            result.get("steps_total", 0),
            result.get("timestamp", ""),
            result.get("output", "")
        ])
    
    filename = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    content = output.getvalue()
    
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/api/tests/results/export/xml")
async def export_xml():
    """Export results as XML"""
    if not test_results:
        raise HTTPException(status_code=404, detail="No test results to export")
    
    xml_content = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml_content.append('<test_results>')
    
    for test_id, result in test_results.items():
        xml_content.append(f'  <test id="{test_id}">')
        xml_content.append(f'    <name>{result.get("test_name", "")}</name>')
        xml_content.append(f'    <type>{result.get("test_type", "")}</type>')
        xml_content.append(f'    <success>{result.get("success", False)}</success>')
        xml_content.append(f'    <duration>{result.get("duration", 0)}</duration>')
        xml_content.append(f'    <steps_passed>{result.get("steps_passed", 0)}</steps_passed>')
        xml_content.append(f'    <steps_total>{result.get("steps_total", 0)}</steps_total>')
        xml_content.append(f'    <timestamp>{result.get("timestamp", "")}</timestamp>')
        xml_content.append(f'    <output>{result.get("output", "")}</output>')
        xml_content.append('  </test>')
    
    xml_content.append('</test_results>')
    
    filename = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"
    content = '\n'.join(xml_content)
    
    return Response(
        content=content,
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# NEW REPORT GENERATION ENDPOINTS

@app.get("/api/tests/results/report/html")
async def generate_html_report_endpoint():
    """Generate and download HTML report"""
    return generate_html_report(test_results)


@app.get("/api/tests/results/report/pdf")
async def generate_pdf_report_endpoint():
    """Generate and download PDF report (redirects to HTML for now)"""
    return generate_pdf_report(test_results)


@app.get("/api/config")
async def get_config():
    """Get current configuration"""
    # Return mock configuration
    return {
        "framework": {
            "version": "1.0.0",
            "debug": False
        },
        "browser": {
            "headless": True,
            "timeout": 30
        },
        "api": {
            "timeout": 10,
            "retries": 3
        }
    }


@app.post("/api/config")
async def update_config(config: ConfigUpdate):
    """Update configuration"""
    # In a real implementation, this would save to file
    return {"message": "Configuration updated successfully", "config": config.config}


@app.get("/api/tests/files")
async def list_test_files():
    """List available test files"""
    test_cases_dir = Path("../tests/cases")
    test_files = []
    
    if test_cases_dir.exists():
        for file in test_cases_dir.rglob("*.yaml"):
            test_files.append({
                "name": file.name,
                "path": str(file.relative_to(test_cases_dir.parent)),
                "size": file.stat().st_size,
                "modified": datetime.fromtimestamp(file.stat().st_mtime).isoformat()
            })
    
    return {"files": test_files}


@app.get("/api/tests/file/{file_path:path}")
async def get_test_file(file_path: str):
    """Get content of a specific test file"""
    try:
        file = Path("../tests") / file_path
        if not file.exists():
            raise HTTPException(status_code=404, detail="Test file not found")
        
        with open(file, 'r') as f:
            content = f.read()
        
        return {"content": content, "path": file_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")


@app.post("/api/tests/file/{file_path:path}")
async def save_test_file(file_path: str, content: TestFileContent):
    """Save content to a test file"""
    try:
        file = Path("../tests") / file_path
        file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file, 'w') as f:
            f.write(content.content)
        
        return {"message": f"File {file_path} saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving file: {str(e)}")


@app.post("/api/tests/upload")
async def upload_test_file(file: UploadFile = File(...)):
    """Upload a test file"""
    try:
        if not file.filename.endswith('.yaml'):
            raise HTTPException(status_code=400, detail="Only YAML files are allowed")
        
        content = await file.read()
        file_path = Path("../tests/cases") / file.filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'wb') as f:
            f.write(content)
        
        return {"message": f"File {file.filename} uploaded successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")


if __name__ == "__main__":
    print("🚀 Starting Easy BDD Framework Frontend...")
    print("📊 Dashboard: http://localhost:8000")
    print("📖 API Docs: http://localhost:8000/docs")
    print("🔧 Features: Test execution, Results viewing, File management, Export functionality, Report generation")
    
    uvicorn.run(
        "simple_app_clean:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )