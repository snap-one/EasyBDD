"""
Modern Test Builder Web Application
FastAPI backend for visual test creation and editing
"""

import asyncio
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

# Try to import psutil for better hardware stats, fallback to platform-specific methods
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

import yaml
from fastapi import (
    BackgroundTasks,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to import markdown for documentation rendering
try:
    import markdown

    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False

# Import action definitions from local file (no framework dependencies)
# E402: module level import not at top of file - required for sys.path setup
from action_definitions import (  # noqa: E402
    ACTION_DEFINITIONS,
    get_action_definition,
    get_actions_by_category,
    validate_action_parameters,
)

app = FastAPI(
    title="Easy BDD Test Builder",
    description="Visual test creation and management interface",
    version="2.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== DATA MODELS ====================


class TestStep(BaseModel):
    """Single test step"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    action: str
    parameters: Dict[str, Any] = {}
    description: Optional[str] = None


class TestDefinition(BaseModel):
    """Complete test definition"""

    name: str
    description: Optional[str] = None
    tags: List[str] = []
    variables: Dict[str, Any] = {}
    browser_config: Dict[str, Any] = {}
    setup: List[TestStep] = []
    steps: List[TestStep] = []
    cleanup: List[TestStep] = []


class TestFile(BaseModel):
    """Test file metadata"""

    id: str
    path: str
    name: str
    description: Optional[str]
    tags: List[str]
    step_count: int
    created: Optional[str]
    modified: str
    folder: Optional[str] = None  # Folder path relative to tests directory
    workspace: Optional[str] = None  # Workspace/category name


class TestExecutionRequest(BaseModel):
    """Request to execute a test"""

    test_path: str
    headless: bool = True
    tags: Optional[List[str]] = None


class TestValidationRequest(BaseModel):
    """Request to validate test"""

    test_definition: TestDefinition


class FolderInfo(BaseModel):
    """Folder information"""

    name: str
    path: str
    test_count: int
    description: Optional[str] = None


class RecordingSession(BaseModel):
    """Recording session information"""

    session_id: str
    url: str
    headless: bool = False


class RecordedAction(BaseModel):
    """A single recorded action"""

    action: str
    parameters: Dict[str, Any]
    description: Optional[str] = None
    timestamp: str


class TestSuiteItem(BaseModel):
    """A test item in a test suite"""

    test_id: str  # Test file path relative to tests directory
    enabled: bool = True  # Whether this test is enabled in the suite
    order: int = 0  # Execution order


class TestSuite(BaseModel):
    """Test suite definition"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: Optional[str] = None
    workspace: Optional[str] = None  # Workspace/category this suite belongs to
    tests: List[TestSuiteItem] = []  # List of tests in the suite
    created: Optional[str] = None
    modified: Optional[str] = None


class TestSuiteExecutionRequest(BaseModel):
    """Request to execute a test suite"""

    suite_id: str
    test_ids: Optional[
        List[str]
    ] = None  # Specific test IDs to run (if None, run all enabled)
    max_tests: Optional[int] = None  # Maximum number of tests to run
    headless: bool = True
    tags: Optional[List[str]] = None


class VariableDefinition(BaseModel):
    """A single variable definition"""

    key: str
    value: Any
    description: Optional[str] = None
    enabled: bool = True


class Environment(BaseModel):
    """Environment definition (like Postman environments)"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: Optional[str] = None
    variables: Dict[str, Any] = {}  # Key-value pairs
    is_active: bool = False  # Only one environment can be active at a time
    created: Optional[str] = None
    modified: Optional[str] = None


class Collection(BaseModel):
    """Collection/Workspace variables"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str  # Workspace/collection name
    description: Optional[str] = None
    variables: Dict[str, Any] = {}  # Key-value pairs
    created: Optional[str] = None
    modified: Optional[str] = None


class SuiteVariables(BaseModel):
    """Test suite variables"""

    suite_id: str
    variables: Dict[str, Any] = {}  # Key-value pairs


# ==================== GLOBAL STATE ====================

tests_directory = Path(__file__).parent.parent / "tests" / "cases"
reports_directory = Path(__file__).parent.parent / "reports"
reports_directory.mkdir(exist_ok=True)  # Ensure reports directory exists

# Test suites directory
test_suites_directory = Path(__file__).parent.parent / "test_suites"
test_suites_directory.mkdir(exist_ok=True)  # Ensure test suites directory exists

# Variables directories
environments_directory = Path(__file__).parent.parent / "environments"
environments_directory.mkdir(exist_ok=True)

collections_directory = Path(__file__).parent.parent / "collections"
collections_directory.mkdir(exist_ok=True)

running_tests: Dict[str, Dict] = {}
test_results: Dict[str, Any] = {}
websocket_connections: List[WebSocket] = []
recording_sessions: Dict[str, Dict[str, Any]] = {}  # session_id -> session data

# ==================== UTILITY FUNCTIONS ====================


def convert_test_to_yaml(test_def: TestDefinition) -> str:
    """Convert TestDefinition to YAML format"""
    yaml_dict = {
        "name": test_def.name,
        "description": test_def.description,
        "tags": test_def.tags,
    }

    # Add browser config if present
    if test_def.browser_config:
        yaml_dict["browser"] = test_def.browser_config

    # Add variables if present
    if test_def.variables:
        yaml_dict["variables"] = test_def.variables

    # Convert steps
    def convert_steps(steps: List[TestStep]) -> List[Dict]:
        result = []
        for step in steps:
            # Use new dot notation format
            step_dict = {step.action: step.parameters}
            if step.description:
                step_dict["description"] = step.description
            result.append(step_dict)
        return result

    if test_def.setup:
        yaml_dict["setup"] = convert_steps(test_def.setup)

    yaml_dict["steps"] = convert_steps(test_def.steps)

    if test_def.cleanup:
        yaml_dict["cleanup"] = convert_steps(test_def.cleanup)

    return yaml.dump(yaml_dict, sort_keys=False, allow_unicode=True)


def convert_yaml_to_test(yaml_content: str) -> TestDefinition:
    """Convert YAML to TestDefinition"""
    data = yaml.safe_load(yaml_content)

    def parse_steps(steps_data: List) -> List[TestStep]:
        result = []
        for step_dict in steps_data:
            # Handle both old and new syntax
            if "action" in step_dict:
                # Old syntax: action: "browser.open"
                action = step_dict["action"]
                params = {
                    k: v
                    for k, v in step_dict.items()
                    if k not in ["action", "description"]
                }
            else:
                # New syntax: browser.open: {url: ...}
                action = list(step_dict.keys())[0]
                if action == "description":
                    continue
                params = (
                    step_dict[action] if isinstance(step_dict[action], dict) else {}
                )

            result.append(
                TestStep(
                    action=action,
                    parameters=params,
                    description=step_dict.get("description"),
                )
            )
        return result

    return TestDefinition(
        name=data.get("name", "Untitled Test"),
        description=data.get("description"),
        tags=data.get("tags", []),
        variables=data.get("variables", {}),
        browser_config=data.get("browser", {}),
        setup=parse_steps(data.get("setup", [])),
        steps=parse_steps(data.get("steps", [])),
        cleanup=parse_steps(data.get("cleanup", [])),
    )


async def broadcast_message(message: Dict[str, Any]):
    """Broadcast message to all connected WebSocket clients"""
    for connection in websocket_connections:
        try:
            await connection.send_json(message)
        except Exception:
            pass


# ==================== API ENDPOINTS ====================


@app.get("/")
async def root():
    """Serve main application page"""
    html_path = Path(__file__).parent / "static" / "test_builder.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse("<h1>Test Builder</h1><p>Frontend not found</p>")


@app.get("/api/docs/{doc_name}", response_class=HTMLResponse)
async def get_documentation(doc_name: str):
    """
    Serve local markdown documentation files.
    Returns HTML-rendered markdown or raw markdown if markdown library is not available.
    """
    # Map document names to file paths
    base_dir = Path(__file__).parent.parent  # Go up from frontend/ to project root

    # Debug: log the request
    import logging

    logger = logging.getLogger(__name__)
    logger.info(f"Documentation request for: {doc_name}")
    logger.info(f"Base directory: {base_dir}")
    logger.info(f"Base directory exists: {base_dir.exists()}")
    doc_map = {
        "README": base_dir / "README.md",
        "setup": base_dir / "docs" / "setup.md",
        "syntax": base_dir / "docs" / "syntax.md",
        "examples": base_dir / "docs" / "examples.md",
        "TEST_BUILDER": base_dir / "docs" / "TEST_BUILDER.md",
        "TEST_BUILDER_QUICKREF": base_dir / "docs" / "TEST_BUILDER_QUICKREF.md",
        "actions": base_dir / "docs" / "actions.md",
        "assertions": base_dir / "docs" / "assertions.md",
        "conditional-steps": base_dir / "docs" / "conditional-steps.md",
        "data-driven": base_dir / "docs" / "data-driven.md",
        "soft-assertions": base_dir / "docs" / "soft-assertions.md",
        "aws-s3-integration": base_dir / "docs" / "aws-s3-integration.md",
        "jsonrpc-websocket": base_dir / "docs" / "jsonrpc-websocket.md",
        "api-authentication": base_dir / "docs" / "api-authentication.md",
        "datalake-logger": base_dir / "docs" / "datalake-logger.md",
        "advanced": base_dir / "docs" / "advanced.md",
        "CENTRALIZED_VARIABLES": base_dir / "docs" / "CENTRALIZED_VARIABLES.md",
        "WORKSPACE_MANAGEMENT": base_dir / "docs" / "WORKSPACE_MANAGEMENT.md",
        "troubleshooting": base_dir / "docs" / "troubleshooting.md",
        "LIVE_RECORDER": base_dir / "docs" / "LIVE_RECORDER.md",
        "PLAYWRIGHT_RECORDING": base_dir / "docs" / "PLAYWRIGHT_RECORDING.md",
    }

    file_path = doc_map.get(doc_name)
    if not file_path:
        # Default to README if not found
        file_path = base_dir / "README.md"

    logger.info(f"Resolved file path: {file_path}")
    logger.info(f"File exists: {file_path.exists()}")

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Documentation file not found: {doc_name} (path: {file_path})",
        )

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Convert markdown to HTML if markdown library is available
        if MARKDOWN_AVAILABLE:
            # Use markdown extensions for better rendering
            md = markdown.Markdown(extensions=["fenced_code", "tables", "toc"])
            html_content = md.convert(content)

            # Wrap in a styled HTML document with dark mode
            html_doc = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{doc_name} - Documentation</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #f1f5f9;
            max-width: 900px;
            margin: 0 auto;
            padding: 2rem;
            background: #0f172a;
            min-height: 100vh;
        }}
        h1, h2, h3, h4, h5, h6 {{
            margin-top: 1.5em;
            margin-bottom: 0.5em;
            font-weight: 600;
            color: #f1f5f9;
        }}
        h1 {{
            border-bottom: 2px solid #334155;
            padding-bottom: 0.3em;
            color: #3b82f6;
        }}
        h2 {{
            border-bottom: 1px solid #334155;
            padding-bottom: 0.3em;
            color: #60a5fa;
        }}
        h3 {{
            color: #93c5fd;
        }}
        code {{
            background: #1e293b;
            color: #e2e8f0;
            padding: 0.2em 0.4em;
            border-radius: 3px;
            font-size: 85%;
            border: 1px solid #334155;
        }}
        pre {{
            background: #1e293b;
            color: #e2e8f0;
            padding: 1em;
            border-radius: 6px;
            overflow-x: auto;
            border: 1px solid #334155;
        }}
        pre code {{
            background: none;
            padding: 0;
            border: none;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 1em 0;
        }}
        table th, table td {{
            border: 1px solid #334155;
            padding: 0.6em 1em;
        }}
        table th {{
            background: #1e293b;
            font-weight: 600;
            color: #f1f5f9;
        }}
        table td {{
            background: #0f172a;
            color: #e2e8f0;
        }}
        blockquote {{
            border-left: 4px solid #3b82f6;
            padding-left: 1em;
            color: #94a3b8;
            margin: 1em 0;
            background: #1e293b;
            padding: 1em;
            border-radius: 4px;
        }}
        a {{
            color: #60a5fa;
            text-decoration: none;
        }}
        a:hover {{
            color: #93c5fd;
            text-decoration: underline;
        }}
        ul, ol {{
            margin: 1em 0;
            padding-left: 2em;
            color: #e2e8f0;
        }}
        li {{
            margin: 0.5em 0;
        }}
        p {{
            color: #e2e8f0;
            margin: 1em 0;
        }}
        img {{
            max-width: 100%;
            height: auto;
            border-radius: 4px;
        }}
        strong {{
            color: #f1f5f9;
            font-weight: 600;
        }}
        em {{
            color: #cbd5e1;
        }}
        hr {{
            border: none;
            border-top: 1px solid #334155;
            margin: 2em 0;
        }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""
            return HTMLResponse(content=html_doc)
        else:
            # Fallback: return raw markdown with dark mode styling
            html_doc = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{doc_name} - Documentation</title>
    <style>
        body {{
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            white-space: pre-wrap;
            padding: 2rem;
            background: #0f172a;
            color: #e2e8f0;
            line-height: 1.6;
        }}
    </style>
</head>
<body>{content}</body>
</html>"""
            return HTMLResponse(content=html_doc)
    except Exception as e:
        import traceback

        error_detail = (
            f"Error reading documentation: {str(e)}\n{traceback.format_exc()}"
        )
        print(f"[ERROR] {error_detail}")
        raise HTTPException(
            status_code=500, detail=f"Error reading documentation: {str(e)}"
        )


@app.get("/api/actions")
async def get_actions():
    """Get all available actions grouped by category"""
    return {
        "categories": get_actions_by_category(),
        "total_actions": len(ACTION_DEFINITIONS),
    }


@app.get("/api/actions/{action_id}")
async def get_action(action_id: str):
    """Get detailed information about a specific action"""
    # URL decode the action_id in case it was encoded
    from urllib.parse import unquote

    action_id = unquote(action_id)

    definition = get_action_definition(action_id)
    if not definition:
        raise HTTPException(status_code=404, detail=f"Action not found: {action_id}")
    return definition


@app.get("/api/tests")
async def list_tests(
    folder: Optional[str] = None,
):
    """List all test files, optionally filtered by folder"""
    tests = []

    if not tests_directory.exists():
        tests_directory.mkdir(parents=True, exist_ok=True)

    # Determine search path
    search_path = tests_directory
    if folder:
        search_path = tests_directory / folder
        if not search_path.exists():
            raise HTTPException(status_code=404, detail=f"Folder not found: {folder}")

    for test_file in search_path.rglob("*.yaml"):
        try:
            with open(test_file, "r") as f:
                content = f.read()
                data = yaml.safe_load(content)

            # Count steps
            step_count = len(data.get("steps", []))
            step_count += len(data.get("setup", []))
            step_count += len(data.get("cleanup", []))

            # Get folder info
            relative_path = test_file.relative_to(tests_directory)
            folder_path = (
                str(relative_path.parent) if relative_path.parent != Path(".") else None
            )
            workspace_name = (
                relative_path.parts[0] if len(relative_path.parts) > 1 else None
            )

            tests.append(
                TestFile(
                    id=str(relative_path),
                    path=str(test_file),
                    name=data.get("name", test_file.stem),
                    description=data.get("description"),
                    tags=data.get("tags", []),
                    step_count=step_count,
                    created=None,
                    modified=datetime.fromtimestamp(
                        test_file.stat().st_mtime
                    ).isoformat(),
                    folder=folder_path,
                    workspace=workspace_name,
                )
            )
        except Exception as e:
            # Include broken files
            relative_path = test_file.relative_to(tests_directory)
            folder_path = (
                str(relative_path.parent) if relative_path.parent != Path(".") else None
            )
            workspace_name = (
                relative_path.parts[0] if len(relative_path.parts) > 1 else None
            )

            tests.append(
                TestFile(
                    id=str(relative_path),
                    path=str(test_file),
                    name=test_file.stem,
                    description=f"Error: {str(e)}",
                    tags=["error"],
                    step_count=0,
                    created=None,
                    modified=datetime.fromtimestamp(
                        test_file.stat().st_mtime
                    ).isoformat(),
                    folder=folder_path,
                    workspace=workspace_name,
                )
            )

    return {"tests": tests, "total": len(tests)}


@app.get("/api/tests/{test_id:path}/reports", response_model=Dict[str, Any])
async def get_test_reports(
    test_id: str,
):
    """Get all reports for a specific test"""
    reports = []

    if not reports_directory.exists():
        return {"reports": []}

    # Convert test_id (relative path) to full test path for matching
    # test_id is like "ovrc/ovrc_example.yaml" (relative to tests directory)
    # We need to match against test_path in reports which might be:
    # - "tests/cases/ovrc/ovrc_example.yaml" (full path)
    # - "ovrc/ovrc_example.yaml" (relative path)

    # Build possible test path variations
    test_path_variations = [
        test_id,  # Original test_id (e.g., "ovrc/ovrc-login-flow.yaml")
        f"tests/cases/{test_id}",  # Full path with tests/cases prefix
        f"tests/{test_id}",  # Full path with tests prefix
    ]

    # Also get just the filename for matching
    test_filename = Path(test_id).name if "/" in test_id or "\\" in test_id else test_id
    test_name_without_ext = Path(test_id).stem

    print(f"[DEBUG] Looking for reports for test_id: {test_id}")
    print(f"[DEBUG] Test filename: {test_filename}, stem: {test_name_without_ext}")
    print(f"[DEBUG] Variations: {test_path_variations}")

    for result_file in reports_directory.glob("*.json"):
        try:
            with open(result_file, "r") as f:
                result_data = json.load(f)

            # Check if test_path in result matches any variation
            test_path = result_data.get("test_path", "")
            filename = result_file.stem

            # Match by test_path in result data (most reliable)
            matched = False
            if test_path:
                test_path_normalized = test_path.replace("\\", "/").strip().lower()

                # Check against all variations
                for variation in test_path_variations:
                    variation_normalized = variation.replace("\\", "/").strip().lower()

                    # Check if paths match (exact or ends with)
                    # Also check if the test_id filename matches the test_path filename
                    test_path_filename = (
                        Path(test_path_normalized).name.lower()
                        if test_path_normalized
                        else ""
                    )
                    test_id_filename = Path(test_id).name.lower()

                    # Check exact match, ends with, or filename match
                    path_matches = (
                        variation_normalized == test_path_normalized
                        or test_path_normalized.endswith(variation_normalized)
                        or variation_normalized.endswith(test_path_normalized)
                    )
                    filename_matches = (
                        test_path_filename == test_id_filename and test_path_filename
                    )

                    if path_matches or filename_matches:
                        print(
                            f"[DEBUG] Matched report {result_file.name} by path: {test_path} (path_match={path_matches}, filename_match={filename_matches})"
                        )
                        reports.append(
                            {
                                "filename": result_file.name,
                                "build_id": result_data.get(
                                    "build_id"
                                ),  # Include unique build ID
                                "timestamp": result_data.get("timestamp")
                                or result_data.get("started")
                                or result_data.get("finished", ""),
                                "status": result_data.get("status", "unknown"),
                                "execution_time": result_data.get("execution_time", 0),
                                "test_path": test_path,
                                "size": result_file.stat().st_size,
                            }
                        )
                        matched = True
                        break

                # Also check if just the filename matches (without path)
                if not matched:
                    test_path_filename = Path(test_path_normalized).name.lower()
                    test_id_filename = Path(test_id).name.lower()
                    if test_path_filename == test_id_filename:
                        print(
                            f"[DEBUG] Matched report {result_file.name} by filename: {test_path_filename} == {test_id_filename}"
                        )
                        reports.append(
                            {
                                "filename": result_file.name,
                                "build_id": result_data.get(
                                    "build_id"
                                ),  # Include unique build ID
                                "timestamp": result_data.get("timestamp")
                                or result_data.get("started")
                                or result_data.get("finished", ""),
                                "status": result_data.get("status", "unknown"),
                                "execution_time": result_data.get("execution_time", 0),
                                "test_path": test_path,
                                "size": result_file.stat().st_size,
                            }
                        )
                        matched = True

            if matched:
                continue  # Skip filename matching if we already matched

            # Fallback: Match by filename (if test_path didn't match)
            # Check if filename contains test name
            if test_name_without_ext in filename or test_filename in filename:
                print(
                    f"[DEBUG] Matched report {result_file.name} by filename pattern: {test_name_without_ext} in {filename}"
                )
                reports.append(
                    {
                        "filename": result_file.name,
                        "build_id": result_data.get(
                            "build_id"
                        ),  # Include unique build ID
                        "timestamp": result_data.get("timestamp")
                        or result_data.get("started")
                        or result_data.get("finished", ""),
                        "status": result_data.get("status", "unknown"),
                        "execution_time": result_data.get("execution_time", 0),
                        "test_path": result_data.get("test_path", ""),
                        "size": result_file.stat().st_size,
                    }
                )
        except Exception as e:
            print(f"Error reading report file {result_file}: {e}")
            continue

    # Sort by timestamp (newest first)
    reports.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    print(f"[DEBUG] Found {len(reports)} reports for test_id: {test_id}")
    return {"reports": reports}


@app.get("/api/tests/{test_id:path}")
async def get_test(
    test_id: str,
):
    """Get a specific test by ID"""
    test_path = tests_directory / test_id

    if not test_path.exists():
        raise HTTPException(status_code=404, detail="Test not found")

    try:
        with open(test_path, "r") as f:
            content = f.read()

        test_def = convert_yaml_to_test(content)
        return test_def
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading test: {str(e)}")


@app.post("/api/tests")
async def create_test(
    test_def: TestDefinition,
    folder: Optional[str] = None,
):
    """Create a new test, optionally in a specific folder"""
    # Generate filename from test name
    filename = test_def.name.lower().replace(" ", "_").replace("/", "_")
    filename = "".join(c for c in filename if c.isalnum() or c == "_")
    filename = f"{filename}.yaml"

    # Determine target directory
    if folder:
        target_dir = tests_directory / folder
    else:
        target_dir = tests_directory

    test_path = target_dir / filename

    # Check if file already exists
    if test_path.exists():
        raise HTTPException(
            status_code=409, detail="Test with this name already exists in this folder"
        )

    try:
        yaml_content = convert_test_to_yaml(test_def)

        test_path.parent.mkdir(parents=True, exist_ok=True)
        with open(test_path, "w") as f:
            f.write(yaml_content)

        return {
            "success": True,
            "test_id": str(test_path.relative_to(tests_directory)),
            "path": str(test_path),
            "folder": folder,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating test: {str(e)}")


@app.put("/api/tests/{test_id:path}")
async def update_test(
    test_id: str,
    test_def: TestDefinition,
):
    """Update an existing test"""
    test_path = tests_directory / test_id

    if not test_path.exists():
        raise HTTPException(status_code=404, detail="Test not found")

    try:
        yaml_content = convert_test_to_yaml(test_def)

        with open(test_path, "w") as f:
            f.write(yaml_content)

        return {"success": True, "test_id": test_id, "path": str(test_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating test: {str(e)}")


@app.delete("/api/tests/{test_id:path}")
async def delete_test(
    test_id: str,
):
    """Delete a test"""
    test_path = tests_directory / test_id

    if not test_path.exists():
        raise HTTPException(status_code=404, detail="Test not found")

    try:
        test_path.unlink()
        return {"success": True, "message": "Test deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting test: {str(e)}")


@app.post("/api/tests/validate")
async def validate_test(
    request: TestValidationRequest,
):
    """Validate a test definition"""
    errors = []
    warnings = []

    try:
        # Validate test structure
        if not request.test_definition.name or not request.test_definition.name.strip():
            errors.append("Test name is required")

        # Count total steps (setup + steps + cleanup)
        total_steps = (
            len(request.test_definition.setup or [])
            + len(request.test_definition.steps or [])
            + len(request.test_definition.cleanup or [])
        )

        if total_steps == 0:
            errors.append(
                "Test must have at least one step (in setup, steps, or cleanup)"
            )

        # Validate each step
        all_steps = []
        step_context = []

        # Add setup steps
        for step in request.test_definition.setup or []:
            all_steps.append(step)
            step_context.append("setup")

        # Add main steps
        for step in request.test_definition.steps or []:
            all_steps.append(step)
            step_context.append("steps")

        # Add cleanup steps
        for step in request.test_definition.cleanup or []:
            all_steps.append(step)
            step_context.append("cleanup")

        for idx, (step, context) in enumerate(zip(all_steps, step_context), 1):
            if not step.action:
                errors.append(f"Step {idx} ({context}): Action is required")
                continue

            action_def = get_action_definition(step.action)

            if not action_def:
                errors.append(f"Step {idx} ({context}): Unknown action '{step.action}'")
                continue

            # Validate parameters
            step_params = step.parameters or {}
            valid, param_errors = validate_action_parameters(step.action, step_params)
            if not valid:
                for error in param_errors:
                    errors.append(f"Step {idx} ({context}, {step.action}): {error}")

    except Exception as e:
        errors.append(f"Validation error: {str(e)}")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


@app.post("/api/tests/execute")
async def execute_test(
    request: TestExecutionRequest,
    background_tasks: BackgroundTasks,
):
    """Execute a test"""
    test_id = str(uuid4())

    # Resolve test path - handle both absolute and relative paths
    project_root = Path(__file__).parent.parent
    test_path = Path(request.test_path)

    # If path is relative, make it relative to project root
    if not test_path.is_absolute():
        test_path = project_root / test_path
    else:
        # If absolute, ensure it's within project
        try:
            test_path = test_path.relative_to(project_root)
            test_path = project_root / test_path
        except ValueError:
            # Path is outside project, use as-is but log warning
            print(f"Warning: Test path is outside project root: {test_path}")

    # Verify test file exists
    if not test_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Test file not found: {test_path}. Please ensure the test is saved first.",
        )

    # Create execution record BEFORE background task
    running_tests[test_id] = {
        "test_path": str(test_path),
        "status": "queued",  # Start as queued, will change to running when task starts
        "started": datetime.now().isoformat(),
        "output": [],
        "command": None,
    }

    print(f"[API] Created execution record for: {test_id}")
    print(f"[API] running_tests now has {len(running_tests)} entries")

    # Run test in background
    async def run_test():
        print(f"[BACKGROUND TASK] Starting test execution for: {test_id}")

        # Update status to running
        if test_id in running_tests:
            running_tests[test_id]["status"] = "running"
            print(f"[BACKGROUND TASK] Updated status to running for: {test_id}")
        else:
            print(f"[BACKGROUND TASK] WARNING: test_id {test_id} not in running_tests!")
            # Recreate it
            running_tests[test_id] = {
                "test_path": str(test_path),
                "status": "running",
                "started": datetime.now().isoformat(),
                "output": [],
            }

        try:
            # Try to use venv Python if available, otherwise use sys.executable
            venv_python = project_root / ".venv" / "bin" / "python"
            python_executable = (
                str(venv_python) if venv_python.exists() else sys.executable
            )

            # Build command - use absolute path
            cmd = [python_executable, "-m", "easy_bdd", "run", str(test_path)]

            if request.headless:
                cmd.append("--headless")

            if request.tags:
                cmd.extend(["--tags", ",".join(request.tags)])

            # Store command as readable string
            command_str = " ".join(cmd)
            running_tests[test_id]["command"] = command_str

            # Log command being executed
            print(f"[TEST EXECUTION] Starting test: {test_id}")
            print(f"[TEST EXECUTION] Command: {command_str}")
            print(f"[TEST EXECUTION] Working directory: {Path(__file__).parent.parent}")

            # Execute test
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(Path(__file__).parent.parent),
            )

            print(f"[TEST EXECUTION] Process started with PID: {process.pid}")

            # Stream output
            line_count = 0
            async for line in process.stdout:
                line_str = line.decode("utf-8", errors="replace").strip()
                if line_str:  # Only add non-empty lines
                    running_tests[test_id]["output"].append(line_str)
                    line_count += 1

                    # Broadcast to WebSocket clients
                    await broadcast_message(
                        {"type": "test_output", "test_id": test_id, "line": line_str}
                    )

                    # Log first few lines for debugging
                    if line_count <= 5:
                        print(f"[TEST OUTPUT] {line_str}")

            return_code = await process.wait()
            print(f"[TEST EXECUTION] Process completed with return code: {return_code}")
            print(f"[TEST EXECUTION] Total output lines: {line_count}")

            # Update status
            running_tests[test_id]["status"] = (
                "completed" if process.returncode == 0 else "failed"
            )
            running_tests[test_id]["return_code"] = process.returncode
            running_tests[test_id]["finished"] = datetime.now().isoformat()

            # Generate unique build ID
            build_id = str(uuid4())[
                :8
            ]  # Use first 8 characters of UUID for shorter display

            # Save results to file
            result_data = {
                "test_id": test_id,
                "test_path": str(test_path),
                "build_id": build_id,  # Unique build identifier
                "status": running_tests[test_id]["status"],
                "return_code": process.returncode,
                "started": running_tests[test_id]["started"],
                "finished": running_tests[test_id]["finished"],
                "output": running_tests[test_id]["output"],
                "command": running_tests[test_id]["command"],
            }

            # Save JSON result
            # Include test_path in result data for better matching
            result_data["test_path"] = str(test_path)

            # Include build_id in filename for easier identification
            result_filename = f"{test_id.replace('/', '_').replace('.yaml', '')}_{build_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            result_path = reports_directory / result_filename
            with open(result_path, "w") as f:
                json.dump(result_data, f, indent=2)

            running_tests[test_id]["result_file"] = str(result_filename)

            # Keep the execution record permanently (don't remove it)
            # This allows the frontend to poll for results even after completion
            running_tests[test_id]["result_file"] = str(result_filename)
            running_tests[test_id]["completed_at"] = datetime.now().isoformat()

            # Also save a reference in the result data for lookup
            result_data["execution_id"] = test_id

            await broadcast_message(
                {
                    "type": "test_completed",
                    "test_id": test_id,
                    "status": running_tests[test_id]["status"],
                    "result_file": result_filename,
                }
            )

            # Send Teams notification if enabled
            await send_teams_notification(test_id, running_tests[test_id], test_path)

            print(
                f"[BACKGROUND TASK] Test {test_id} completed. Status: {running_tests[test_id]['status']}"
            )
            print(f"[BACKGROUND TASK] Result file: {result_filename}")
            print("[BACKGROUND TASK] Execution record kept in running_tests")
            print(
                f"[BACKGROUND TASK] running_tests contains: {list(running_tests.keys())}"
            )

        except Exception as e:
            import traceback

            error_trace = traceback.format_exc()
            print(f"Error executing test {test_id}: {e}")
            print(f"Traceback: {error_trace}")

            running_tests[test_id]["status"] = "error"
            running_tests[test_id]["error"] = str(e)
            running_tests[test_id]["error_trace"] = error_trace

            await broadcast_message(
                {
                    "type": "test_error",
                    "test_id": test_id,
                    "error": str(e),
                    "error_trace": error_trace,
                }
            )

            # Send Teams notification for error
            running_tests[test_id]["status"] = "error"
            await send_teams_notification(test_id, running_tests[test_id], test_path)

    # Verify execution record exists before starting background task
    if test_id not in running_tests:
        print(
            "[API] ERROR: Execution record not found before starting background task!"
        )
        raise HTTPException(status_code=500, detail="Failed to create execution record")

    # Add background task and log
    print(f"[API] Adding background task for test execution: {test_id}")
    print(f"[API] Execution record status: {running_tests[test_id].get('status')}")
    background_tasks.add_task(run_test)
    print("[API] Background task added successfully")
    print(f"[API] running_tests now contains: {list(running_tests.keys())}")

    return {
        "test_id": test_id,
        "status": "queued",
        "message": "Test execution started",
        "test_path": str(test_path),
        "execution_record_exists": test_id in running_tests,
    }


@app.get("/api/tests/execution/{test_id}")
async def get_test_execution(
    test_id: str,
):
    """Get test execution status and output"""
    print(f"[API] Getting execution status for: {test_id}")
    print(f"[API] Current running_tests keys: {list(running_tests.keys())}")

    if test_id not in running_tests:
        # Check if it might be in results
        print(f"[API] Test execution {test_id} not found in running_tests")
        # Try to find it in results directory
        result_files = list(reports_directory.glob(f"*{test_id}*.json"))
        if result_files:
            print(f"[API] Found result file: {result_files[0]}")
            try:
                with open(result_files[0], "r") as f:
                    result_data = json.load(f)
                return result_data
            except Exception as e:
                print(f"[API] Error reading result file: {e}")

        raise HTTPException(
            status_code=404,
            detail=f"Test execution not found: {test_id}. Available executions: {list(running_tests.keys())[:5]}",
        )

    return running_tests[test_id]


@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    """Get dashboard statistics"""
    try:
        # Count tests
        test_count = 0
        if tests_directory.exists():
            test_count = len(list(tests_directory.rglob("*.yaml")))

        # Analyze results
        results = []
        if reports_directory.exists():
            for result_file in reports_directory.glob("*.json"):
                try:
                    with open(result_file, "r") as f:
                        result_data = json.load(f)

                    test_info = None
                    if (
                        "tests" in result_data
                        and isinstance(result_data["tests"], list)
                        and result_data["tests"]
                    ):
                        test_info = result_data["tests"][0]

                    status = (
                        test_info.get("status", result_data.get("status", "unknown"))
                        if test_info
                        else result_data.get("status", "unknown")
                    ).lower()
                    timestamp = (
                        result_data.get("timestamp")
                        or result_data.get("started")
                        or result_data.get("finished")
                    )

                    # Extract test name from multiple possible sources
                    test_name = "Unknown Test"

                    # Try test_info.name first
                    if test_info and test_info.get("name"):
                        test_name = test_info.get("name")
                    # Try test_info.file_path or test_path
                    elif test_info and test_info.get("file_path"):
                        test_path = test_info.get("file_path")
                        # Extract just the filename without extension
                        test_name = Path(test_path).stem.replace("_", " ").title()
                    elif test_info and test_info.get("test_path"):
                        test_path = test_info.get("test_path")
                        test_name = Path(test_path).stem.replace("_", " ").title()
                    # Try result_data.test_path
                    elif result_data.get("test_path"):
                        test_path = result_data.get("test_path")
                        test_name = Path(test_path).stem.replace("_", " ").title()
                    # Try result_data.test_file
                    elif result_data.get("test_file"):
                        test_file = result_data.get("test_file")
                        test_name = Path(test_file).stem.replace("_", " ").title()
                    # Try extracting from output logs
                    elif result_data.get("output") and isinstance(
                        result_data.get("output"), list
                    ):
                        for line in result_data.get("output", []):
                            if "Executing test" in str(line):
                                try:
                                    # Extract from "Executing test 1/1: TestName"
                                    parts = str(line).split("Executing test")
                                    if len(parts) > 1:
                                        test_part = parts[1].split(":")[-1].strip()
                                        if test_part:
                                            test_name = test_part
                                            break
                                except Exception:
                                    pass
                    # Fallback: use filename
                    if test_name == "Unknown Test":
                        test_name = result_file.stem.replace("_", " ").title()
                        # Remove execution ID if present (format: id_timestamp)
                        if "_" in test_name:
                            parts = test_name.split("_")
                            # If last part looks like a date/time, remove it
                            if len(parts) > 1 and any(
                                char.isdigit() for char in parts[-1]
                            ):
                                test_name = "_".join(parts[:-1])

                    results.append(
                        {
                            "status": status,
                            "timestamp": timestamp,
                            "execution_time": test_info.get("execution_time")
                            if test_info
                            else result_data.get("execution_time", 0),
                            "test_name": test_name,
                        }
                    )
                except Exception as e:
                    print(f"Error processing result file {result_file}: {e}")
                    continue

        # Calculate statistics
        total_runs = len(results)
        passed = sum(
            1 for r in results if r["status"] in ["passed", "completed", "success"]
        )
        failed = sum(1 for r in results if r["status"] in ["failed", "error"])
        pass_rate = (passed / total_runs * 100) if total_runs > 0 else 0

        # Get recent runs (last 7 days)
        from datetime import timedelta

        seven_days_ago = datetime.now() - timedelta(days=7)
        recent_runs = []
        for r in results:
            if r.get("timestamp"):
                try:
                    ts = r["timestamp"]
                    # Handle various timestamp formats
                    if isinstance(ts, str):
                        # Remove timezone info and milliseconds if present
                        ts_clean = ts.split(".")[0].split("+")[0].split("Z")[0]
                        try:
                            r_date = datetime.fromisoformat(ts_clean)
                        except Exception:
                            # Try parsing as standard format
                            r_date = datetime.strptime(ts_clean, "%Y-%m-%d %H:%M:%S")
                        if r_date >= seven_days_ago:
                            recent_runs.append(r)
                    elif isinstance(ts, (int, float)):
                        r_date = datetime.fromtimestamp(ts)
                        if r_date >= seven_days_ago:
                            recent_runs.append(r)
                except Exception:
                    continue

        # Get today's runs
        today = datetime.now().date()
        today_runs = []
        for r in results:
            if r.get("timestamp"):
                try:
                    ts = r["timestamp"]
                    if isinstance(ts, str):
                        ts_clean = ts.split(".")[0].split("+")[0].split("Z")[0]
                        try:
                            r_date = datetime.fromisoformat(ts_clean)
                        except Exception:
                            r_date = datetime.strptime(ts_clean, "%Y-%m-%d %H:%M:%S")
                        if r_date.date() == today:
                            today_runs.append(r)
                    elif isinstance(ts, (int, float)):
                        r_date = datetime.fromtimestamp(ts)
                        if r_date.date() == today:
                            today_runs.append(r)
                except Exception:
                    continue

        # Average execution time
        avg_time = (
            sum(r.get("execution_time", 0) for r in results) / len(results)
            if results
            else 0
        )

        # Get last run
        last_run = None
        if results:
            sorted_results = sorted(
                [r for r in results if r.get("timestamp")],
                key=lambda x: x["timestamp"],
                reverse=True,
            )
            if sorted_results:
                last_run = sorted_results[0]

        # Running tests count
        running_count = len(
            [t for t in running_tests.values() if t.get("status") == "running"]
        )

        # Get hardware stats
        hardware_stats = get_hardware_stats()

        return {
            "test_count": test_count,
            "total_runs": total_runs,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(pass_rate, 1),
            "today_runs": len(today_runs),
            "recent_runs": len(recent_runs),
            "avg_execution_time": round(avg_time, 2),
            "last_run": last_run,
            "running_tests": running_count,
            "recent_results": sorted(
                [r for r in results if r.get("timestamp")],
                key=lambda x: x["timestamp"],
                reverse=True,
            )[:10],
            "hardware": hardware_stats,
        }
    except Exception as e:
        print(f"Error calculating dashboard stats: {e}")
        # Get hardware stats even on error
        hardware_stats = get_hardware_stats()

        return {
            "test_count": 0,
            "total_runs": 0,
            "passed": 0,
            "failed": 0,
            "pass_rate": 0,
            "today_runs": 0,
            "recent_runs": 0,
            "avg_execution_time": 0,
            "last_run": None,
            "running_tests": 0,
            "recent_results": [],
            "hardware": hardware_stats,
        }


def get_hardware_stats() -> Dict[str, Any]:
    """Get hardware statistics (CPU, memory, disk)"""
    stats = {
        "cpu": {"usage_percent": 0, "cores": 0, "frequency": 0},
        "memory": {"total_gb": 0, "used_gb": 0, "available_gb": 0, "usage_percent": 0},
        "disk": {"total_gb": 0, "used_gb": 0, "free_gb": 0, "usage_percent": 0},
    }

    try:
        if PSUTIL_AVAILABLE:
            # CPU stats
            stats["cpu"]["usage_percent"] = round(psutil.cpu_percent(interval=0.1), 1)
            stats["cpu"]["cores"] = psutil.cpu_count(logical=True)
            try:
                freq = psutil.cpu_freq()
                if freq:
                    stats["cpu"]["frequency"] = round(
                        freq.current / 1000, 2
                    )  # Convert to GHz
            except Exception:
                pass

            # Memory stats
            mem = psutil.virtual_memory()
            stats["memory"]["total_gb"] = round(mem.total / (1024**3), 2)
            stats["memory"]["used_gb"] = round(mem.used / (1024**3), 2)
            stats["memory"]["available_gb"] = round(mem.available / (1024**3), 2)
            stats["memory"]["usage_percent"] = round(mem.percent, 1)

            # Disk stats (for the current working directory)
            disk = psutil.disk_usage("/")
            stats["disk"]["total_gb"] = round(disk.total / (1024**3), 2)
            stats["disk"]["used_gb"] = round(disk.used / (1024**3), 2)
            stats["disk"]["free_gb"] = round(disk.free / (1024**3), 2)
            stats["disk"]["usage_percent"] = round((disk.used / disk.total) * 100, 1)
        else:
            # Fallback to platform-specific methods
            # CPU cores
            stats["cpu"]["cores"] = os.cpu_count() or 1

            # Memory (platform-specific)
            if platform.system() == "Linux":
                try:
                    with open("/proc/meminfo", "r") as f:
                        meminfo = f.read()
                        for line in meminfo.split("\n"):
                            if line.startswith("MemTotal:"):
                                total_kb = int(line.split()[1])
                                stats["memory"]["total_gb"] = round(
                                    total_kb / (1024**2), 2
                                )
                            elif line.startswith("MemAvailable:"):
                                avail_kb = int(line.split()[1])
                                stats["memory"]["available_gb"] = round(
                                    avail_kb / (1024**2), 2
                                )
                                stats["memory"]["used_gb"] = round(
                                    (
                                        stats["memory"]["total_gb"]
                                        - stats["memory"]["available_gb"]
                                    ),
                                    2,
                                )
                                if stats["memory"]["total_gb"] > 0:
                                    stats["memory"]["usage_percent"] = round(
                                        (
                                            stats["memory"]["used_gb"]
                                            / stats["memory"]["total_gb"]
                                        )
                                        * 100,
                                        1,
                                    )
                except Exception:
                    pass
            elif platform.system() == "Darwin":  # macOS
                try:
                    # Use vm_stat command
                    result = subprocess.run(
                        ["vm_stat"], capture_output=True, text=True, timeout=2
                    )
                    if result.returncode == 0:
                        # Parse vm_stat output (simplified)
                        # This is a basic implementation
                        pass
                except Exception:
                    pass

            # Disk stats using shutil
            try:
                disk = shutil.disk_usage("/")
                stats["disk"]["total_gb"] = round(disk.total / (1024**3), 2)
                stats["disk"]["used_gb"] = round(disk.used / (1024**3), 2)
                stats["disk"]["free_gb"] = round(disk.free / (1024**3), 2)
                stats["disk"]["usage_percent"] = round(
                    (disk.used / disk.total) * 100, 1
                )
            except Exception:
                pass

            # CPU usage (platform-specific, less accurate)
            if platform.system() == "Linux":
                try:
                    result = subprocess.run(
                        ["top", "-bn1"], capture_output=True, text=True, timeout=2
                    )
                    # Parse top output (simplified)
                except Exception:
                    pass
    except Exception as e:
        print(f"Error getting hardware stats: {e}")

    return stats


@app.get("/api/dashboard/hardware")
async def get_hardware_stats_endpoint():
    """Get hardware statistics"""
    return get_hardware_stats()


@app.get("/api/metrics/comprehensive")
async def get_comprehensive_metrics():
    """Get comprehensive metrics for the metrics page"""
    try:
        from collections import defaultdict
        from datetime import timedelta

        # Load all test results
        results = []
        test_results_map = defaultdict(list)  # test_name -> list of results
        if reports_directory.exists():
            for result_file in reports_directory.glob("*.json"):
                try:
                    with open(result_file, "r") as f:
                        result_data = json.load(f)

                    test_info = None
                    if (
                        "tests" in result_data
                        and isinstance(result_data["tests"], list)
                        and result_data["tests"]
                    ):
                        test_info = result_data["tests"][0]

                    status = (
                        test_info.get("status", result_data.get("status", "unknown"))
                        if test_info
                        else result_data.get("status", "unknown")
                    ).lower()

                    timestamp = (
                        result_data.get("timestamp")
                        or result_data.get("started")
                        or result_data.get("finished")
                    )

                    # Extract test name
                    test_name = "Unknown Test"
                    if test_info and test_info.get("name"):
                        test_name = test_info.get("name")
                    elif test_info and test_info.get("file_path"):
                        test_path = test_info.get("file_path")
                        test_name = Path(test_path).stem.replace("_", " ").title()
                    elif test_info and test_info.get("test_path"):
                        test_path = test_info.get("test_path")
                        test_name = Path(test_path).stem.replace("_", " ").title()
                    elif result_data.get("test_path"):
                        test_path = result_data.get("test_path")
                        test_name = Path(test_path).stem.replace("_", " ").title()
                    elif result_data.get("file_path"):
                        test_path = result_data.get("file_path")
                        test_name = Path(test_path).stem.replace("_", " ").title()

                    result_item = {
                        "status": status,
                        "timestamp": timestamp,
                        "execution_time": test_info.get("execution_time")
                        if test_info
                        else result_data.get("execution_time", 0),
                        "test_name": test_name,
                        "test_path": test_info.get("test_path")
                        or test_info.get("file_path")
                        or result_data.get("test_path")
                        or result_data.get("file_path"),
                    }

                    results.append(result_item)
                    if timestamp:
                        test_results_map[test_name].append(result_item)
                except Exception as e:
                    print(f"Error processing result file {result_file}: {e}")
                    continue

        # Sort results by timestamp
        results_with_timestamp = [r for r in results if r.get("timestamp")]
        results_with_timestamp.sort(key=lambda x: x["timestamp"], reverse=True)

        # 1. Test Health & Maintenance
        # Most failing tests
        test_failure_counts = defaultdict(lambda: {"total": 0, "failed": 0})
        for result in results:
            test_name = result.get("test_name", "Unknown")
            test_failure_counts[test_name]["total"] += 1
            if result["status"] in ["failed", "error"]:
                test_failure_counts[test_name]["failed"] += 1

        most_failing_tests = []
        for test_name, counts in test_failure_counts.items():
            if counts["total"] > 0:
                failure_rate = (counts["failed"] / counts["total"]) * 100
                if counts["failed"] > 0:
                    most_failing_tests.append(
                        {
                            "test_name": test_name,
                            "total_runs": counts["total"],
                            "failed_runs": counts["failed"],
                            "failure_rate": round(failure_rate, 1),
                        }
                    )

        most_failing_tests.sort(
            key=lambda x: (x["failure_rate"], x["failed_runs"]), reverse=True
        )

        # Flaky tests (tests that have both passed and failed)
        flaky_tests = []
        for test_name, test_results in test_results_map.items():
            if len(test_results) < 2:
                continue
            statuses = [r["status"] for r in test_results]
            has_passed = any(s in ["passed", "completed", "success"] for s in statuses)
            has_failed = any(s in ["failed", "error"] for s in statuses)
            if has_passed and has_failed:
                passed_count = sum(
                    1 for s in statuses if s in ["passed", "completed", "success"]
                )
                failed_count = sum(1 for s in statuses if s in ["failed", "error"])
                flaky_tests.append(
                    {
                        "test_name": test_name,
                        "total_runs": len(test_results),
                        "passed": passed_count,
                        "failed": failed_count,
                        "pass_rate": round((passed_count / len(test_results)) * 100, 1),
                    }
                )

        flaky_tests.sort(key=lambda x: x["total_runs"], reverse=True)

        # Stale tests (tests not run in last 30 days)
        thirty_days_ago = datetime.now() - timedelta(days=30)
        stale_tests = []
        all_test_names = set()
        if tests_directory.exists():
            for test_file in tests_directory.rglob("*.yaml"):
                test_name = test_file.stem.replace("_", " ").title()
                all_test_names.add(test_name)

        for test_name in all_test_names:
            test_results = test_results_map.get(test_name, [])
            if not test_results:
                stale_tests.append(
                    {
                        "test_name": test_name,
                        "last_run": None,
                        "days_since_run": None,
                    }
                )
            else:
                latest_result = max(
                    test_results, key=lambda x: x.get("timestamp") or ""
                )
                if latest_result.get("timestamp"):
                    try:
                        last_run_date = datetime.fromisoformat(
                            latest_result["timestamp"].replace("Z", "+00:00")
                        )
                        if last_run_date < thirty_days_ago:
                            days_since = (datetime.now() - last_run_date).days
                            stale_tests.append(
                                {
                                    "test_name": test_name,
                                    "last_run": latest_result["timestamp"],
                                    "days_since_run": days_since,
                                }
                            )
                    except Exception:
                        pass

        stale_tests.sort(
            key=lambda x: x["days_since_run"] if x["days_since_run"] else 999,
            reverse=True,
        )

        # Tests without steps
        tests_without_steps = []
        if tests_directory.exists():
            for test_file in tests_directory.rglob("*.yaml"):
                try:
                    with open(test_file, "r") as f:
                        test_data = yaml.safe_load(f)
                        test_name = test_file.stem.replace("_", " ").title()
                        steps_count = (
                            len(test_data.get("steps", []))
                            + len(test_data.get("setup", []))
                            + len(test_data.get("cleanup", []))
                        )
                        if steps_count == 0:
                            tests_without_steps.append(
                                {
                                    "test_name": test_name,
                                    "test_path": str(
                                        test_file.relative_to(tests_directory)
                                    ),
                                }
                            )
                except Exception:
                    pass

        # 2. Test Suite Statistics
        suite_stats = {
            "total_suites": 0,
            "suites_with_tests": 0,
            "total_tests_in_suites": 0,
            "most_active_suites": [],
        }

        if test_suites_directory.exists():
            suites = []
            for suite_file in test_suites_directory.glob("*.json"):
                try:
                    with open(suite_file, "r") as f:
                        data = json.load(f)
                        suite = TestSuite(**data)
                        suites.append(suite)
                except Exception:
                    continue

            suite_stats["total_suites"] = len(suites)
            suite_stats["suites_with_tests"] = sum(
                1 for s in suites if len(s.tests) > 0
            )
            suite_stats["total_tests_in_suites"] = sum(len(s.tests) for s in suites)

            # Most active suites (by test count)
            suite_activity = [
                {"name": s.name, "test_count": len(s.tests), "id": s.id} for s in suites
            ]
            suite_activity.sort(key=lambda x: x["test_count"], reverse=True)
            suite_stats["most_active_suites"] = suite_activity[:10]

        # 3. Execution Trends
        # Execution time trends (last 30 days)
        thirty_days_ago = datetime.now() - timedelta(days=30)
        recent_results = [
            r
            for r in results_with_timestamp
            if r.get("timestamp")
            and datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
            > thirty_days_ago
        ]

        # Group by date
        execution_time_by_date = defaultdict(list)
        failure_rate_by_date = defaultdict(lambda: {"total": 0, "failed": 0})

        for result in recent_results:
            try:
                result_date = datetime.fromisoformat(
                    result["timestamp"].replace("Z", "+00:00")
                )
                date_key = result_date.strftime("%Y-%m-%d")
                if result.get("execution_time"):
                    execution_time_by_date[date_key].append(result["execution_time"])
                failure_rate_by_date[date_key]["total"] += 1
                if result["status"] in ["failed", "error"]:
                    failure_rate_by_date[date_key]["failed"] += 1
            except Exception:
                pass

        execution_trends = []
        for date_key in sorted(execution_time_by_date.keys()):
            times = execution_time_by_date[date_key]
            execution_trends.append(
                {
                    "date": date_key,
                    "avg_time": round(sum(times) / len(times), 2) if times else 0,
                    "min_time": round(min(times), 2) if times else 0,
                    "max_time": round(max(times), 2) if times else 0,
                }
            )

        failure_rate_trends = []
        for date_key in sorted(failure_rate_by_date.keys()):
            stats = failure_rate_by_date[date_key]
            rate = (stats["failed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            failure_rate_trends.append(
                {
                    "date": date_key,
                    "total": stats["total"],
                    "failed": stats["failed"],
                    "failure_rate": round(rate, 1),
                }
            )

        # Peak execution times (by hour)
        executions_by_hour = defaultdict(int)
        for result in results_with_timestamp:
            try:
                result_time = datetime.fromisoformat(
                    result["timestamp"].replace("Z", "+00:00")
                )
                hour = result_time.hour
                executions_by_hour[hour] += 1
            except Exception:
                pass

        peak_hours = [
            {"hour": h, "count": executions_by_hour[h]}
            for h in sorted(executions_by_hour.keys())
        ]

        # Slowest tests
        slowest_tests = []
        test_execution_times = defaultdict(list)
        for result in results:
            if result.get("execution_time"):
                test_name = result.get("test_name", "Unknown")
                test_execution_times[test_name].append(result["execution_time"])

        for test_name, times in test_execution_times.items():
            slowest_tests.append(
                {
                    "test_name": test_name,
                    "avg_time": round(sum(times) / len(times), 2),
                    "max_time": round(max(times), 2),
                    "min_time": round(min(times), 2),
                    "runs": len(times),
                }
            )

        slowest_tests.sort(key=lambda x: x["avg_time"], reverse=True)

        # 4. Test Coverage & Distribution
        # Tests by workspace
        tests_by_workspace = defaultdict(int)
        if tests_directory.exists():
            for test_file in tests_directory.rglob("*.yaml"):
                try:
                    with open(test_file, "r") as f:
                        test_data = yaml.safe_load(f)
                        workspace = test_data.get("workspace") or "No Workspace"
                        tests_by_workspace[workspace] += 1
                except Exception:
                    tests_by_workspace["Unknown"] += 1

        workspace_distribution = [
            {"workspace": ws, "count": count}
            for ws, count in sorted(
                tests_by_workspace.items(), key=lambda x: x[1], reverse=True
            )
        ]

        # Tests by action type
        action_type_counts = defaultdict(int)
        total_steps = 0
        if tests_directory.exists():
            for test_file in tests_directory.rglob("*.yaml"):
                try:
                    with open(test_file, "r") as f:
                        test_data = yaml.safe_load(f)
                        for step in (
                            test_data.get("steps", [])
                            + test_data.get("setup", [])
                            + test_data.get("cleanup", [])
                        ):
                            action = step.get("action", "unknown")
                            # Categorize action
                            if action.startswith("browser.") or action.startswith(
                                "browser "
                            ):
                                action_type_counts["Browser"] += 1
                            elif action.startswith("api.") or action.startswith("api "):
                                action_type_counts["API"] += 1
                            elif action.startswith("command.") or action.startswith(
                                "command "
                            ):
                                action_type_counts["Command"] += 1
                            elif action.startswith("test.") or action.startswith(
                                "test "
                            ):
                                action_type_counts["Test"] += 1
                            elif "ovrc" in action.lower():
                                action_type_counts["OvrC API"] += 1
                            elif (
                                "jsonrpc" in action.lower()
                                or "json-rpc" in action.lower()
                            ):
                                action_type_counts["JSON-RPC"] += 1
                            elif "aws" in action.lower():
                                action_type_counts["AWS"] += 1
                            else:
                                action_type_counts["Other"] += 1
                            total_steps += 1
                except Exception:
                    pass

        action_distribution = [
            {
                "type": action_type,
                "count": count,
                "percentage": round(
                    (count / total_steps * 100) if total_steps > 0 else 0, 1
                ),
            }
            for action_type, count in sorted(
                action_type_counts.items(), key=lambda x: x[1], reverse=True
            )
        ]

        # Test complexity (steps per test)
        test_complexity = []
        if tests_directory.exists():
            for test_file in tests_directory.rglob("*.yaml"):
                try:
                    with open(test_file, "r") as f:
                        test_data = yaml.safe_load(f)
                        test_name = test_file.stem.replace("_", " ").title()
                        steps_count = (
                            len(test_data.get("steps", []))
                            + len(test_data.get("setup", []))
                            + len(test_data.get("cleanup", []))
                        )
                        test_complexity.append(
                            {
                                "test_name": test_name,
                                "steps": steps_count,
                                "setup_steps": len(test_data.get("setup", [])),
                                "main_steps": len(test_data.get("steps", [])),
                                "cleanup_steps": len(test_data.get("cleanup", [])),
                            }
                        )
                except Exception:
                    pass

        test_complexity.sort(key=lambda x: x["steps"], reverse=True)
        avg_complexity = (
            sum(t["steps"] for t in test_complexity) / len(test_complexity)
            if test_complexity
            else 0
        )

        # Tag distribution
        tag_counts = defaultdict(int)
        if tests_directory.exists():
            for test_file in tests_directory.rglob("*.yaml"):
                try:
                    with open(test_file, "r") as f:
                        test_data = yaml.safe_load(f)
                        tags = test_data.get("tags", [])
                        for tag in tags:
                            tag_counts[tag] += 1
                except Exception:
                    pass

        tag_distribution = [
            {"tag": tag, "count": count}
            for tag, count in sorted(
                tag_counts.items(), key=lambda x: x[1], reverse=True
            )[:20]
        ]

        # 5. Quick Insights
        # Execution velocity (tests per day/week)
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        today_count = sum(
            1
            for r in results_with_timestamp
            if r.get("timestamp")
            and datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).date()
            == today
        )

        week_count = sum(
            1
            for r in results_with_timestamp
            if r.get("timestamp")
            and datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).date()
            >= week_ago
        )

        month_count = sum(
            1
            for r in results_with_timestamp
            if r.get("timestamp")
            and datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).date()
            >= month_ago
        )

        # Success streak
        success_streak = 0
        for result in results_with_timestamp[:10]:  # Check last 10 runs
            if result["status"] in ["passed", "completed", "success"]:
                success_streak += 1
            else:
                break

        # Recent failures
        recent_failures = [
            r for r in results_with_timestamp[:20] if r["status"] in ["failed", "error"]
        ][:5]

        # 6. Resource & Storage
        # Test result storage
        result_files_size = 0
        result_file_count = 0
        if reports_directory.exists():
            for result_file in reports_directory.glob("*.json"):
                try:
                    result_files_size += result_file.stat().st_size
                    result_file_count += 1
                except Exception:
                    pass

        # HTML reports
        html_reports_size = 0
        html_report_count = 0
        if reports_directory.exists():
            for html_file in reports_directory.glob("*.html"):
                try:
                    html_reports_size += html_file.stat().st_size
                    html_report_count += 1
                except Exception:
                    pass

        # Old results (older than 90 days)
        ninety_days_ago = datetime.now() - timedelta(days=90)
        old_results_count = sum(
            1
            for r in results_with_timestamp
            if r.get("timestamp")
            and datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
            < ninety_days_ago
        )

        return {
            "test_health": {
                "most_failing_tests": most_failing_tests[:10],
                "flaky_tests": flaky_tests[:10],
                "stale_tests": stale_tests[:20],
                "tests_without_steps": tests_without_steps[:20],
            },
            "suite_statistics": suite_stats,
            "execution_trends": {
                "time_trends": execution_trends[-30:],  # Last 30 days
                "failure_rate_trends": failure_rate_trends[-30:],
                "peak_hours": peak_hours,
                "slowest_tests": slowest_tests[:10],
            },
            "test_coverage": {
                "by_workspace": workspace_distribution,
                "by_action_type": action_distribution,
                "complexity": {
                    "average": round(avg_complexity, 1),
                    "most_complex": test_complexity[:10],
                    "least_complex": sorted(test_complexity, key=lambda x: x["steps"])[
                        :10
                    ],
                },
                "tag_distribution": tag_distribution,
            },
            "quick_insights": {
                "execution_velocity": {
                    "today": today_count,
                    "this_week": week_count,
                    "this_month": month_count,
                    "avg_per_day": round(week_count / 7, 1) if week_count > 0 else 0,
                },
                "success_streak": success_streak,
                "recent_failures": recent_failures,
            },
            "resource_storage": {
                "result_files": {
                    "count": result_file_count,
                    "size_mb": round(result_files_size / (1024 * 1024), 2),
                },
                "html_reports": {
                    "count": html_report_count,
                    "size_mb": round(html_reports_size / (1024 * 1024), 2),
                },
                "old_results_count": old_results_count,
            },
        }
    except Exception as e:
        print(f"Error calculating comprehensive metrics: {e}")
        import traceback

        traceback.print_exc()
        return {
            "test_health": {
                "most_failing_tests": [],
                "flaky_tests": [],
                "stale_tests": [],
                "tests_without_steps": [],
            },
            "suite_statistics": {
                "total_suites": 0,
                "suites_with_tests": 0,
                "total_tests_in_suites": 0,
                "most_active_suites": [],
            },
            "execution_trends": {
                "time_trends": [],
                "failure_rate_trends": [],
                "peak_hours": [],
                "slowest_tests": [],
            },
            "test_coverage": {
                "by_workspace": [],
                "by_action_type": [],
                "complexity": {"average": 0, "most_complex": [], "least_complex": []},
                "tag_distribution": [],
            },
            "quick_insights": {
                "execution_velocity": {
                    "today": 0,
                    "this_week": 0,
                    "this_month": 0,
                    "avg_per_day": 0,
                },
                "success_streak": 0,
                "recent_failures": [],
            },
            "resource_storage": {
                "result_files": {"count": 0, "size_mb": 0},
                "html_reports": {"count": 0, "size_mb": 0},
                "old_results_count": 0,
            },
        }


@app.get("/api/results")
async def list_test_results(
    page: int = 1,
    per_page: int = 10,
    workspace: Optional[str] = None,
):
    """List all test execution results with pagination and workspace filtering"""
    print(
        f"[DEBUG] list_test_results called: page={page}, per_page={per_page}, workspace={workspace}"
    )
    """List all test execution results with pagination and workspace filtering"""
    results = []

    for result_file in reports_directory.glob("*.json"):
        try:
            with open(result_file, "r") as f:
                result_data = json.load(f)

            # Support new result format
            test_info = None
            if (
                "tests" in result_data
                and isinstance(result_data["tests"], list)
                and result_data["tests"]
            ):
                test_info = result_data["tests"][0]

            # Get test_path for workspace extraction
            test_path = result_data.get("test_path", "") or (
                test_info.get("file_path", "") if test_info else ""
            )

            # Extract workspace from test_path (e.g., "tests/cases/ovrc/test.yaml" -> "ovrc")
            workspace_name = None
            if test_path:
                # Normalize path separators
                normalized_path = test_path.replace("\\", "/")
                path_parts = normalized_path.split("/")
                # Remove empty parts
                path_parts = [p for p in path_parts if p]

                # Look for workspace in path (usually after "tests/cases/")
                if (
                    len(path_parts) >= 3
                    and path_parts[0] == "tests"
                    and path_parts[1] == "cases"
                ):
                    workspace_name = path_parts[2] if len(path_parts) > 2 else None
                elif len(path_parts) >= 2:
                    # Fallback: use first directory after root
                    workspace_name = (
                        path_parts[0]
                        if path_parts[0] not in ["tests", "cases"]
                        else (path_parts[1] if len(path_parts) > 1 else None)
                    )

            # Get timestamp for sorting (prefer finished, then started, then timestamp)
            timestamp = (
                result_data.get("finished")
                or result_data.get("started")
                or result_data.get("timestamp", "")
            )

            results.append(
                {
                    "filename": result_file.name,
                    "build_id": result_data.get("build_id"),  # Include unique build ID
                    "test_id": test_info.get(
                        "name", result_data.get("test_file", "unknown")
                    )
                    if test_info
                    else result_data.get("test_file", "unknown"),
                    "test_path": test_path
                    or (
                        test_info.get("file_path", "unknown")
                        if test_info
                        else result_data.get("test_file", "unknown")
                    ),
                    "status": test_info.get(
                        "status", result_data.get("status", "unknown")
                    ).upper()
                    if test_info
                    else result_data.get("status", "unknown"),
                    "started": result_data.get("started")
                    or result_data.get("timestamp", "N/A"),
                    "finished": result_data.get("finished")
                    or result_data.get("timestamp", "N/A"),
                    "timestamp": timestamp,  # For sorting
                    "return_code": result_data.get("failed", 0),
                    "output_lines": len(test_info.get("execution_log", "").splitlines())
                    if test_info
                    else 0,
                    "workspace": workspace_name or "uncategorized",
                    "execution_time": test_info.get("execution_time", 0)
                    if test_info
                    else result_data.get("execution_time", 0),
                }
            )
        except Exception as e:
            print(f"Error reading result file {result_file}: {e}")

    # Sort by timestamp (newest first), handle None/empty values
    results.sort(key=lambda x: x.get("timestamp", "") or "", reverse=True)

    # Calculate workspace counts BEFORE filtering (for dropdown)
    all_workspaces = {}
    for result in results:
        ws = result.get("workspace", "uncategorized")
        all_workspaces[ws] = all_workspaces.get(ws, 0) + 1

    # Filter by workspace if specified
    if workspace:
        results = [r for r in results if r.get("workspace") == workspace]

    # Calculate pagination AFTER filtering
    total = len(results)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_results = results[start_idx:end_idx]

    return {
        "results": paginated_results,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
        "workspaces": sorted(list(all_workspaces.keys())),
        "workspace_counts": all_workspaces,
    }


@app.get("/api/results/{filename}")
async def get_test_result(
    filename: str,
):
    """Get detailed test execution result"""
    result_path = reports_directory / filename

    if not result_path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")

    try:
        with open(result_path, "r") as f:
            result_data = json.load(f)
        return result_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading result: {str(e)}")


@app.get("/api/results/{filename}/download")
async def download_test_result(
    filename: str,
):
    """Download test execution result as JSON"""
    result_path = reports_directory / filename

    if not result_path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")

    return FileResponse(
        path=result_path, filename=filename, media_type="application/json"
    )


@app.post("/api/results/{filename}/generate-report")
async def generate_report_from_json_file(
    filename: str,
):
    """Generate HTML report from a JSON test results file"""
    result_path = reports_directory / filename

    if not result_path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")

    try:
        # Read the JSON file
        with open(result_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Import HTMLReporter directly from file to avoid importing entire easy_bdd package
        import importlib.util
        import sys
        from pathlib import Path as PathLib

        # Add project root to path
        project_root = Path(__file__).parent.parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))

        try:
            # Import directly from the file to avoid __init__.py dependencies
            html_reporter_path = project_root / "easy_bdd" / "core" / "html_reporter.py"
            if not html_reporter_path.exists():
                raise HTTPException(
                    status_code=500, detail="HTMLReporter module not found"
                )

            spec = importlib.util.spec_from_file_location(
                "html_reporter", html_reporter_path
            )
            html_reporter_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(html_reporter_module)
            HTMLReporter = html_reporter_module.HTMLReporter
        except Exception as import_err:
            import traceback

            error_details = traceback.format_exc()
            print(f"Import error: {error_details}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to import HTMLReporter: {str(import_err)}",
            )

        from datetime import datetime

        # Parse the JSON data to extract test details
        test_details = []
        total_tests = 0
        passed = 0
        failed = 0
        execution_time = 0.0
        test_file_name = "test"

        # Handle different JSON formats
        if "tests" in data:
            # Standard format (has "tests" array)
            test_details = data["tests"]
            total_tests = data.get("total_tests", len(test_details))
            passed = data.get(
                "passed",
                sum(
                    1
                    for t in test_details
                    if t.get("status", "").upper() in ["PASSED", "COMPLETED"]
                ),
            )
            failed = data.get(
                "failed",
                sum(1 for t in test_details if t.get("status", "").upper() == "FAILED"),
            )
            execution_time = data.get(
                "execution_time", sum(t.get("execution_time", 0) for t in test_details)
            )
            test_file_name = data.get(
                "test_file",
                PathLib(result_path)
                .stem.replace("_results", "")
                .replace("_report", ""),
            )
        elif "test_path" in data and "output" in data:
            # Web app format (has test_path, status, output array)
            # Parse execution time from started/finished timestamps
            if "started" in data and "finished" in data:
                try:
                    started = datetime.fromisoformat(
                        data["started"].replace("Z", "+00:00")
                    )
                    finished = datetime.fromisoformat(
                        data["finished"].replace("Z", "+00:00")
                    )
                    execution_time = (finished - started).total_seconds()
                except Exception:
                    pass

            # Try to extract execution time from output
            if execution_time == 0:
                for line in data.get("output", []):
                    if "Execution time:" in line:
                        try:
                            execution_time = float(
                                line.split("Execution time:")[1]
                                .split("seconds")[0]
                                .strip()
                            )
                            break
                        except Exception:
                            pass

            # Try to extract test results from output
            for line in data.get("output", []):
                if "passed" in line.lower() and "failed" in line.lower():
                    try:
                        # Parse "Test Results: X passed, Y failed"
                        parts = line.split("Test Results:")[1].strip()
                        passed = int(parts.split("passed")[0].strip())
                        failed = int(parts.split("failed")[0].split(",")[1].strip())
                        break
                    except Exception:
                        pass

            # If not found, use status field
            if passed == 0 and failed == 0:
                if data.get("status", "").lower() in ["passed", "completed", "success"]:
                    passed = 1
                else:
                    failed = 1

            total_tests = passed + failed if (passed + failed) > 0 else 1

            # Extract test name from output or test_path
            test_name = "Test"
            for line in data.get("output", []):
                if "Executing test" in line:
                    try:
                        test_name = (
                            line.split("Executing test")[1].split(":")[1].strip()
                        )
                        break
                    except Exception:
                        pass

            if test_name == "Test":
                test_name = (
                    PathLib(data.get("test_path", "")).stem.replace("_", " ").title()
                )

            # Create test detail structure
            execution_log = "\n".join(data.get("output", []))
            test_details = [
                {
                    "name": test_name,
                    "description": "",
                    "tags": [],
                    "status": "PASSED"
                    if data.get("status", "").lower()
                    in ["passed", "completed", "success"]
                    else "FAILED",
                    "execution_time": execution_time,
                    "file_path": data.get("test_path", ""),
                    "execution_log": execution_log,
                    "error": None
                    if data.get("status", "").lower()
                    in ["passed", "completed", "success"]
                    else execution_log,
                }
            ]

            test_file_name = PathLib(
                data.get("test_path", PathLib(result_path).stem)
            ).stem
        elif isinstance(data, list):
            # Format is a list of test results
            test_details = data
            total_tests = len(test_details)
            passed = sum(
                1
                for t in test_details
                if t.get("status", "").upper() in ["PASSED", "COMPLETED"]
                or t.get("success", False)
            )
            failed = sum(
                1
                for t in test_details
                if t.get("status", "").upper() == "FAILED"
                or (
                    not t.get("success", True)
                    and t.get("status", "").upper() != "PASSED"
                )
            )
            execution_time = sum(t.get("execution_time", 0) for t in test_details)
            test_file_name = (
                PathLib(result_path).stem.replace("_results", "").replace("_report", "")
            )
        else:
            # Try to extract from other formats
            test_details = []
            if "test_details" in data:
                test_details = data["test_details"]
            elif "results" in data:
                test_details = data["results"]
            else:
                # Try to use the data itself as a single test result
                test_details = [data]

            total_tests = len(test_details) if test_details else 1
            passed = (
                sum(
                    1
                    for t in test_details
                    if t.get("status", "").upper() in ["PASSED", "COMPLETED"]
                    or t.get("success", False)
                )
                if test_details
                else 0
            )
            failed = total_tests - passed
            execution_time = (
                sum(t.get("execution_time", 0) for t in test_details)
                if test_details
                else data.get("execution_time", 0)
            )
            test_file_name = (
                PathLib(result_path).stem.replace("_results", "").replace("_report", "")
            )

        # Generate the report using HTMLReporter
        reporter = HTMLReporter(reports_directory)
        report_path = reporter.generate_report(
            test_details=test_details,
            total_tests=total_tests,
            passed=passed,
            failed=failed,
            execution_time=execution_time,
            test_file_name=test_file_name,
        )

        if report_path and Path(report_path).exists():
            # Return the report file
            return FileResponse(
                path=report_path,
                filename=Path(report_path).name,
                media_type="text/html",
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to generate report")
    except HTTPException:
        raise
    except Exception as e:
        import traceback

        error_details = traceback.format_exc()
        print(f"Error generating report: {error_details}")
        import logging

        logging.error(f"Error generating report: {error_details}")
        # Return more detailed error for debugging
        raise HTTPException(
            status_code=500,
            detail=f"Error generating report: {str(e)}\n\nTraceback:\n{error_details}",
        )


@app.delete("/api/results/{filename}")
async def delete_test_result(
    filename: str,
):
    """Delete a test execution result"""
    result_path = reports_directory / filename

    if not result_path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")

    try:
        result_path.unlink()
        return {"success": True, "message": "Result deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting result: {str(e)}")


# ==================== TEST SUITE ENDPOINTS ====================


def _get_suite_file_path(suite_id: str) -> Path:
    """Get file path for a test suite"""
    return test_suites_directory / f"{suite_id}.json"


def _load_suite(suite_id: str) -> Optional[TestSuite]:
    """Load a test suite from disk"""
    suite_file = _get_suite_file_path(suite_id)
    if not suite_file.exists():
        return None

    try:
        with open(suite_file, "r") as f:
            data = json.load(f)
            return TestSuite(**data)
    except Exception as e:
        print(f"Error loading suite {suite_id}: {e}")
        return None


def _save_suite(suite: TestSuite) -> bool:
    """Save a test suite to disk"""
    try:
        suite_file = _get_suite_file_path(suite.id)
        suite_dict = suite.model_dump()
        suite_dict["modified"] = datetime.now().isoformat()
        if not suite_dict.get("created"):
            suite_dict["created"] = datetime.now().isoformat()

        with open(suite_file, "w") as f:
            json.dump(suite_dict, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving suite {suite.id}: {e}")
        return False


@app.get("/api/test-suites")
async def list_test_suites(
    workspace: Optional[str] = None,
):
    """List all test suites, optionally filtered by workspace"""
    suites = []

    if not test_suites_directory.exists():
        return {"suites": [], "total": 0}

    for suite_file in test_suites_directory.glob("*.json"):
        try:
            with open(suite_file, "r") as f:
                data = json.load(f)
                suite = TestSuite(**data)

                # Filter by workspace if specified
                if workspace and suite.workspace != workspace:
                    continue

                suites.append(suite)
        except Exception as e:
            print(f"Error loading suite file {suite_file}: {e}")
            continue

    # Sort by modified date (newest first)
    suites.sort(key=lambda s: s.modified or s.created or "", reverse=True)

    return {"suites": [suite.model_dump() for suite in suites], "total": len(suites)}


@app.get("/api/test-suites/{suite_id}")
async def get_test_suite(
    suite_id: str,
):
    """Get a specific test suite"""
    suite = _load_suite(suite_id)
    if not suite:
        raise HTTPException(status_code=404, detail=f"Test suite not found: {suite_id}")
    return suite.model_dump()


@app.post("/api/test-suites")
async def create_test_suite(
    suite: TestSuite,
):
    """Create a new test suite"""
    # Generate ID if not provided
    if not suite.id:
        suite.id = str(uuid4())

    # Set timestamps
    now = datetime.now().isoformat()
    suite.created = now
    suite.modified = now

    if _save_suite(suite):
        return suite.model_dump()
    else:
        raise HTTPException(status_code=500, detail="Failed to create test suite")


@app.put("/api/test-suites/{suite_id}")
async def update_test_suite(
    suite_id: str,
    suite: TestSuite,
):
    """Update an existing test suite"""
    existing = _load_suite(suite_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Test suite not found: {suite_id}")

    # Preserve ID and created date
    suite.id = suite_id
    suite.created = existing.created

    if _save_suite(suite):
        return suite.model_dump()
    else:
        raise HTTPException(status_code=500, detail="Failed to update test suite")


@app.delete("/api/test-suites/{suite_id}")
async def delete_test_suite(
    suite_id: str,
):
    """Delete a test suite"""
    suite_file = _get_suite_file_path(suite_id)

    if not suite_file.exists():
        raise HTTPException(status_code=404, detail=f"Test suite not found: {suite_id}")

    try:
        suite_file.unlink()
        return {"success": True, "message": "Test suite deleted successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error deleting test suite: {str(e)}"
        )


@app.post("/api/test-suites/{suite_id}/execute")
async def execute_test_suite(
    suite_id: str,
    request: TestSuiteExecutionRequest,
    background_tasks: BackgroundTasks,
):
    """Execute a test suite with optional test selection"""
    suite = _load_suite(suite_id)
    if not suite:
        raise HTTPException(status_code=404, detail=f"Test suite not found: {suite_id}")

    # Determine which tests to run
    tests_to_run = []

    if request.test_ids:
        # Run specific tests
        for test_id in request.test_ids:
            suite_item = next(
                (item for item in suite.tests if item.test_id == test_id), None
            )
            if suite_item:
                tests_to_run.append(suite_item)
    else:
        # Run enabled tests, optionally limited by max_tests
        enabled_tests = [item for item in suite.tests if item.enabled]
        enabled_tests.sort(key=lambda x: x.order)  # Sort by order

        if request.max_tests:
            tests_to_run = enabled_tests[: request.max_tests]
        else:
            tests_to_run = enabled_tests

    if not tests_to_run:
        raise HTTPException(status_code=400, detail="No tests to run in suite")

    # Create execution ID
    execution_id = f"suite_{suite_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # Store execution info
    running_tests[execution_id] = {
        "status": "running",
        "started": datetime.now().isoformat(),
        "suite_id": suite_id,
        "suite_name": suite.name,
        "test_count": len(tests_to_run),
        "tests": [item.test_id for item in tests_to_run],
        "progress": 0,
    }

    # Execute tests in background
    background_tasks.add_task(
        execute_test_suite_background, execution_id, suite, tests_to_run, request
    )

    return {
        "execution_id": execution_id,
        "suite_id": suite_id,
        "suite_name": suite.name,
        "test_count": len(tests_to_run),
        "tests": [item.test_id for item in tests_to_run],
        "message": f"Test suite execution started with {len(tests_to_run)} test(s)",
    }


async def execute_test_suite_background(
    execution_id: str,
    suite: TestSuite,
    tests_to_run: List[TestSuiteItem],
    request: TestSuiteExecutionRequest,
):
    """Execute test suite in background"""
    try:
        total_tests = len(tests_to_run)
        passed = 0
        failed = 0
        results = []

        for idx, suite_item in enumerate(tests_to_run):
            test_id = suite_item.test_id
            test_path = tests_directory / test_id

            if not test_path.exists():
                print(f"      ⚠️  Test file not found: {test_path}")
                failed += 1
                results.append(
                    {
                        "test_id": test_id,
                        "status": "failed",
                        "error": f"Test file not found: {test_path}",
                    }
                )
                continue

            # Update progress
            progress = int((idx / total_tests) * 100)
            running_tests[execution_id]["progress"] = progress

            # Broadcast progress
            await broadcast_message(
                {
                    "type": "suite_progress",
                    "execution_id": execution_id,
                    "current_test": idx + 1,
                    "total_tests": total_tests,
                    "test_id": test_id,
                    "progress": progress,
                }
            )

            # Execute the test
            try:
                # Try to use venv Python if available, otherwise use sys.executable
                venv_python = Path(__file__).parent.parent / ".venv" / "bin" / "python"
                python_executable = (
                    str(venv_python) if venv_python.exists() else sys.executable
                )

                # Build command
                cmd = [python_executable, "-m", "easy_bdd", "run", str(test_path)]

                if request.headless:
                    cmd.append("--headless")

                if request.tags:
                    cmd.extend(["--tags", ",".join(request.tags)])

                # Execute test
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(Path(__file__).parent.parent),
                )

                output_lines = []
                for line in process.stdout:
                    output_lines.append(line.rstrip())
                    # Broadcast output
                    await broadcast_message(
                        {
                            "type": "suite_output",
                            "execution_id": execution_id,
                            "test_id": test_id,
                            "line": line.rstrip(),
                        }
                    )

                process.wait()
                return_code = process.returncode

                # Determine status
                output_text = "\n".join(output_lines)
                test_passed = return_code == 0 and (
                    "PASSED" in output_text or "passed" in output_text.lower()
                )

                if test_passed:
                    passed += 1
                    status = "passed"
                else:
                    failed += 1
                    status = "failed"

                results.append(
                    {
                        "test_id": test_id,
                        "status": status,
                        "return_code": return_code,
                        "output": output_lines,
                    }
                )

            except Exception as e:
                failed += 1
                error_msg = str(e)
                results.append(
                    {"test_id": test_id, "status": "failed", "error": error_msg}
                )
                print(f"      ❌ Error executing test {test_id}: {error_msg}")

        # Final status
        final_status = "completed" if failed == 0 else "failed"
        running_tests[execution_id]["status"] = final_status
        running_tests[execution_id]["progress"] = 100
        running_tests[execution_id]["finished"] = datetime.now().isoformat()
        running_tests[execution_id]["passed"] = passed
        running_tests[execution_id]["failed"] = failed
        running_tests[execution_id]["results"] = results

        # Broadcast completion
        await broadcast_message(
            {
                "type": "suite_completed",
                "execution_id": execution_id,
                "status": final_status,
                "passed": passed,
                "failed": failed,
                "total": total_tests,
            }
        )

    except Exception as e:
        running_tests[execution_id]["status"] = "failed"
        running_tests[execution_id]["error"] = str(e)
        running_tests[execution_id]["finished"] = datetime.now().isoformat()
        print(f"      ❌ Error executing test suite: {e}")


# ==================== VARIABLE MANAGEMENT ====================


def _get_environment_file_path(env_id: str) -> Path:
    """Get file path for an environment"""
    return environments_directory / f"{env_id}.json"


def _load_environment(env_id: str) -> Optional[Environment]:
    """Load environment from file"""
    env_file = _get_environment_file_path(env_id)
    if not env_file.exists():
        return None

    try:
        with open(env_file, "r") as f:
            data = json.load(f)
            return Environment(**data)
    except Exception as e:
        print(f"Error loading environment {env_id}: {e}")
        return None


def _save_environment(env: Environment) -> bool:
    """Save environment to file"""
    try:
        env_file = _get_environment_file_path(env.id)
        with open(env_file, "w") as f:
            json.dump(env.model_dump(), f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving environment {env.id}: {e}")
        return False


def _get_collection_file_path(collection_id: str) -> Path:
    """Get file path for a collection"""
    return collections_directory / f"{collection_id}.json"


def _load_collection(collection_id: str) -> Optional[Collection]:
    """Load collection from file"""
    collection_file = _get_collection_file_path(collection_id)
    if not collection_file.exists():
        return None

    try:
        with open(collection_file, "r") as f:
            data = json.load(f)
            return Collection(**data)
    except Exception as e:
        print(f"Error loading collection {collection_id}: {e}")
        return None


def _save_collection(collection: Collection) -> bool:
    """Save collection to file"""
    try:
        collection_file = _get_collection_file_path(collection.id)
        with open(collection_file, "w") as f:
            json.dump(collection.model_dump(), f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving collection {collection.id}: {e}")
        return False


def _get_active_environment() -> Optional[Environment]:
    """Get the currently active environment"""
    if not environments_directory.exists():
        return None

    for env_file in environments_directory.glob("*.json"):
        try:
            with open(env_file, "r") as f:
                data = json.load(f)
                env = Environment(**data)
                if env.is_active:
                    return env
        except Exception:
            continue
    return None


def _get_collection_by_name(name: str) -> Optional[Collection]:
    """Get collection by workspace/collection name"""
    if not collections_directory.exists():
        return None

    for collection_file in collections_directory.glob("*.json"):
        try:
            with open(collection_file, "r") as f:
                data = json.load(f)
                collection = Collection(**data)
                if collection.name == name:
                    return collection
        except Exception:
            continue
    return None


def _deactivate_all_environments():
    """Deactivate all environments"""
    if not environments_directory.exists():
        return

    for env_file in environments_directory.glob("*.json"):
        try:
            with open(env_file, "r") as f:
                data = json.load(f)
                env = Environment(**data)
                if env.is_active:
                    env.is_active = False
                    env.modified = datetime.now().isoformat()
                    _save_environment(env)
        except Exception:
            continue


# ==================== ENVIRONMENT ENDPOINTS ====================


@app.get("/api/environments")
async def list_environments():
    """List all environments"""
    environments = []

    if not environments_directory.exists():
        return {"environments": [], "total": 0, "active": None}

    active_env = None
    for env_file in environments_directory.glob("*.json"):
        try:
            with open(env_file, "r") as f:
                data = json.load(f)
                env = Environment(**data)
                environments.append(env)
                if env.is_active:
                    active_env = env.id
        except Exception as e:
            print(f"Error loading environment file {env_file}: {e}")
            continue

    # Sort by name
    environments.sort(key=lambda e: e.name.lower())

    return {
        "environments": [env.model_dump() for env in environments],
        "total": len(environments),
        "active": active_env,
    }


@app.get("/api/environments/{env_id}")
async def get_environment(
    env_id: str,
):
    """Get a specific environment"""
    env = _load_environment(env_id)
    if not env:
        raise HTTPException(status_code=404, detail=f"Environment not found: {env_id}")
    return env.model_dump()


@app.post("/api/environments")
async def create_environment(
    env: Environment,
):
    """Create a new environment"""
    # Generate ID if not provided
    if not env.id:
        env.id = str(uuid4())

    # Set timestamps
    now = datetime.now().isoformat()
    env.created = now
    env.modified = now

    # If this environment is being set as active, deactivate others
    if env.is_active:
        _deactivate_all_environments()

    if _save_environment(env):
        return env.model_dump()
    else:
        raise HTTPException(status_code=500, detail="Failed to create environment")


@app.put("/api/environments/{env_id}")
async def update_environment(
    env_id: str,
    env: Environment,
):
    """Update an existing environment"""
    existing = _load_environment(env_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Environment not found: {env_id}")

    # Preserve ID and created date
    env.id = env_id
    env.created = existing.created
    env.modified = datetime.now().isoformat()

    # If this environment is being set as active, deactivate others
    if env.is_active and not existing.is_active:
        _deactivate_all_environments()

    if _save_environment(env):
        return env.model_dump()
    else:
        raise HTTPException(status_code=500, detail="Failed to update environment")


@app.delete("/api/environments/{env_id}")
async def delete_environment(
    env_id: str,
):
    """Delete an environment"""
    env_file = _get_environment_file_path(env_id)

    if not env_file.exists():
        raise HTTPException(status_code=404, detail=f"Environment not found: {env_id}")

    try:
        env_file.unlink()
        return {"success": True, "message": "Environment deleted successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error deleting environment: {str(e)}"
        )


@app.post("/api/environments/{env_id}/activate")
async def activate_environment(
    env_id: str,
):
    """Activate an environment (deactivates all others)"""
    env = _load_environment(env_id)
    if not env:
        raise HTTPException(status_code=404, detail=f"Environment not found: {env_id}")

    # Deactivate all environments
    _deactivate_all_environments()

    # Activate this one
    env.is_active = True
    env.modified = datetime.now().isoformat()

    if _save_environment(env):
        return {
            "success": True,
            "message": f"Environment '{env.name}' activated",
            "environment": env.model_dump(),
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to activate environment")


# ==================== COLLECTION ENDPOINTS ====================


@app.get("/api/collections")
async def list_collections():
    """List all collections"""
    collections = []

    if not collections_directory.exists():
        return {"collections": [], "total": 0}

    for collection_file in collections_directory.glob("*.json"):
        try:
            with open(collection_file, "r") as f:
                data = json.load(f)
                collection = Collection(**data)
                collections.append(collection)
        except Exception as e:
            print(f"Error loading collection file {collection_file}: {e}")
            continue

    # Sort by name
    collections.sort(key=lambda c: c.name.lower())

    return {
        "collections": [collection.model_dump() for collection in collections],
        "total": len(collections),
    }


@app.get("/api/collections/{collection_id}")
async def get_collection(
    collection_id: str,
):
    """Get a specific collection"""
    collection = _load_collection(collection_id)
    if not collection:
        raise HTTPException(
            status_code=404, detail=f"Collection not found: {collection_id}"
        )
    return collection.model_dump()


@app.get("/api/collections/by-name/{name}")
async def get_collection_by_name(
    name: str,
):
    """Get a collection by workspace/collection name"""
    collection = _get_collection_by_name(name)
    if not collection:
        raise HTTPException(status_code=404, detail=f"Collection not found: {name}")
    return collection.model_dump()


@app.post("/api/collections")
async def create_collection(
    collection: Collection,
):
    """Create a new collection"""
    # Generate ID if not provided
    if not collection.id:
        collection.id = str(uuid4())

    # Set timestamps
    now = datetime.now().isoformat()
    collection.created = now
    collection.modified = now

    if _save_collection(collection):
        return collection.model_dump()
    else:
        raise HTTPException(status_code=500, detail="Failed to create collection")


@app.put("/api/collections/{collection_id}")
async def update_collection(
    collection_id: str,
    collection: Collection,
):
    """Update an existing collection"""
    existing = _load_collection(collection_id)
    if not existing:
        raise HTTPException(
            status_code=404, detail=f"Collection not found: {collection_id}"
        )

    # Preserve ID and created date
    collection.id = collection_id
    collection.created = existing.created
    collection.modified = datetime.now().isoformat()

    if _save_collection(collection):
        return collection.model_dump()
    else:
        raise HTTPException(status_code=500, detail="Failed to update collection")


@app.delete("/api/collections/{collection_id}")
async def delete_collection(
    collection_id: str,
):
    """Delete a collection"""
    collection_file = _get_collection_file_path(collection_id)

    if not collection_file.exists():
        raise HTTPException(
            status_code=404, detail=f"Collection not found: {collection_id}"
        )

    try:
        collection_file.unlink()
        return {"success": True, "message": "Collection deleted successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error deleting collection: {str(e)}"
        )


# ==================== SUITE VARIABLES ENDPOINTS ====================


@app.get("/api/test-suites/{suite_id}/variables")
async def get_suite_variables(
    suite_id: str,
):
    """Get variables for a test suite"""
    suite = _load_suite(suite_id)
    if not suite:
        raise HTTPException(status_code=404, detail=f"Test suite not found: {suite_id}")

    # Check if suite has variables stored separately
    variables_file = test_suites_directory / f"{suite_id}_variables.json"
    if variables_file.exists():
        try:
            with open(variables_file, "r") as f:
                data = json.load(f)
                return {"suite_id": suite_id, "variables": data.get("variables", {})}
        except Exception:
            pass

    return {"suite_id": suite_id, "variables": {}}


@app.put("/api/test-suites/{suite_id}/variables")
async def update_suite_variables(
    suite_id: str,
    suite_vars: SuiteVariables,
):
    """Update variables for a test suite"""
    suite = _load_suite(suite_id)
    if not suite:
        raise HTTPException(status_code=404, detail=f"Test suite not found: {suite_id}")

    # Ensure suite_id matches
    suite_vars.suite_id = suite_id

    # Save variables to separate file
    variables_file = test_suites_directory / f"{suite_id}_variables.json"
    try:
        with open(variables_file, "w") as f:
            json.dump(suite_vars.model_dump(), f, indent=2)
        return {
            "success": True,
            "message": "Suite variables updated",
            "variables": suite_vars.variables,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error saving suite variables: {str(e)}"
        )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates"""
    await websocket.accept()
    websocket_connections.append(websocket)

    try:
        while True:
            # Keep connection alive with timeout
            try:
                # Wait for message with timeout to keep connection alive
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Echo back for ping/pong
                await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in websocket_connections:
            websocket_connections.remove(websocket)


@app.get("/api/categories")
async def get_categories():
    """Get list of action categories"""
    categories = set()
    for action_def in ACTION_DEFINITIONS.values():
        categories.add(action_def.get("category", "Other"))

    return {"categories": sorted(list(categories))}


@app.get("/api/templates")
async def get_test_templates():
    """Get predefined test templates"""
    templates = [
        {
            "id": "browser_login",
            "name": "Browser Login Test",
            "description": "Basic login flow test template",
            "category": "Browser",
            "template": TestDefinition(
                name="Login Test",
                description="Test user login functionality",
                tags=["browser", "authentication"],
                steps=[
                    TestStep(
                        action="browser.open",
                        parameters={"url": "https://example.com/login"},
                    ),
                    TestStep(
                        action="browser.fill",
                        parameters={"field": "#username", "value": "${username}"},
                    ),
                    TestStep(
                        action="browser.fill",
                        parameters={"field": "#password", "value": "${password}"},
                    ),
                    TestStep(action="browser.click", parameters={"button": "Sign In"}),
                    TestStep(
                        action="test.assert",
                        parameters={
                            "expression": "'Welcome' in page_content",
                            "message": "Should see welcome message",
                        },
                    ),
                ],
            ),
        },
        {
            "id": "api_crud",
            "name": "API CRUD Operations",
            "description": "Create, Read, Update, Delete API test",
            "category": "API",
            "template": TestDefinition(
                name="API CRUD Test",
                description="Test REST API CRUD operations",
                tags=["api", "crud"],
                variables={"api_url": "https://api.example.com"},
                steps=[
                    TestStep(
                        action="api.post",
                        parameters={
                            "url": "${api_url}/users",
                            "body": {"name": "Test User"},
                            "store_as": "created_user",
                        },
                    ),
                    TestStep(
                        action="api.get",
                        parameters={
                            "url": "${api_url}/users/${created_user.id}",
                            "store_as": "user",
                        },
                    ),
                    TestStep(
                        action="api.put",
                        parameters={
                            "url": "${api_url}/users/${user.id}",
                            "body": {"name": "Updated User"},
                        },
                    ),
                    TestStep(
                        action="api.delete",
                        parameters={"url": "${api_url}/users/${user.id}"},
                    ),
                ],
            ),
        },
        {
            "id": "aws_firmware",
            "name": "AWS Firmware Test",
            "description": "Download and verify firmware from S3",
            "category": "AWS",
            "template": TestDefinition(
                name="Firmware Update Test",
                description="Test firmware download and update",
                tags=["aws", "firmware"],
                variables={"bucket": "firmware-bucket"},
                steps=[
                    TestStep(
                        action="aws.get_latest",
                        parameters={
                            "bucket_name": "${bucket}",
                            "folder_prefix": "firmware/",
                            "store_as": "latest_fw",
                        },
                    ),
                    TestStep(
                        action="aws.download",
                        parameters={
                            "bucket_name": "${bucket}",
                            "key": "${latest_fw_basename}",
                            "local_path": "/tmp/firmware.bin",
                        },
                    ),
                    TestStep(
                        action="test.assert",
                        parameters={
                            "expression": "os.path.exists('/tmp/firmware.bin')",
                            "message": "Firmware file should be downloaded",
                        },
                    ),
                ],
            ),
        },
    ]

    return {"templates": templates}


@app.get("/api/action-templates")
async def get_action_templates():
    """Generate templates for every action with preset parameters"""
    action_templates = []

    for action_id, action_def in ACTION_DEFINITIONS.items():
        # Build parameters with defaults/placeholders
        template_params = {}

        for param_name, param_def in action_def.get("parameters", {}).items():
            param_type = param_def.get("type", "text")
            is_required = param_def.get("required", False)

            # Set default value based on type and definition
            if "default" in param_def:
                template_params[param_name] = param_def["default"]
            elif param_type == "text":
                # Use placeholder if available, otherwise use a generic placeholder
                placeholder = param_def.get("placeholder", "")
                if placeholder:
                    template_params[param_name] = placeholder
                elif is_required:
                    template_params[param_name] = f"<{param_name}>"
            elif param_type == "number":
                template_params[param_name] = (
                    param_def.get("default", 0) if is_required else None
                )
            elif param_type == "boolean":
                template_params[param_name] = param_def.get("default", False)
            elif param_type == "select":
                options = param_def.get("options", [])
                if options:
                    # Use first option if it's a simple list, or first value if it's a list of dicts
                    if isinstance(options[0], dict):
                        template_params[param_name] = options[0].get(
                            "value", options[0].get("label", "")
                        )
                    else:
                        template_params[param_name] = options[0]
            elif param_type == "keyvalue":
                # For keyvalue, provide an empty object structure
                template_params[param_name] = {}
            elif param_type == "json":
                # For JSON, provide an empty object
                template_params[param_name] = {}
            elif param_type == "textarea":
                template_params[param_name] = (
                    param_def.get("placeholder", "") if is_required else ""
                )
            # Only include required parameters or those with defaults
            elif is_required:
                template_params[param_name] = f"<{param_name}>"

        # Create template step
        template_step = {
            "action": action_id,
            "parameters": template_params,
            "description": f"Template for {action_def.get('label', action_id)}",
        }

        action_templates.append(
            {
                "id": f"action_template_{action_id}",
                "action_id": action_id,
                "name": action_def.get("label", action_id),
                "description": action_def.get("description", ""),
                "category": action_def.get("category", "Other"),
                "icon": action_def.get("icon", "📝"),
                "step": template_step,
                "required_params": [
                    name
                    for name, defn in action_def.get("parameters", {}).items()
                    if defn.get("required", False)
                ],
                "optional_params": [
                    name
                    for name, defn in action_def.get("parameters", {}).items()
                    if not defn.get("required", False)
                ],
            }
        )

    # Sort by category, then by name
    action_templates.sort(key=lambda x: (x["category"], x["name"]))

    return {
        "templates": action_templates,
        "total": len(action_templates),
        "by_category": {},
    }


@app.get("/api/folders")
async def list_folders():
    """List all available folders/workspaces in the tests directory"""
    folders = []

    if not tests_directory.exists():
        tests_directory.mkdir(parents=True, exist_ok=True)
        return {"folders": folders, "total": 0}

    # Get all directories (excluding hidden ones)
    for item in tests_directory.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            # Count tests in this folder
            test_count = len(list(item.rglob("*.yaml")))

            folders.append(
                FolderInfo(
                    name=item.name,
                    path=str(item.relative_to(tests_directory)),
                    test_count=test_count,
                    description=None,
                )
            )

    # Sort by name
    folders.sort(key=lambda x: x.name)

    return {"folders": folders, "total": len(folders)}


@app.post("/api/folders")
async def create_folder(
    name: str,
    description: Optional[str] = None,
):
    """Create a new folder/workspace"""
    # Sanitize folder name
    folder_name = name.lower().replace(" ", "_").replace("/", "_")
    folder_name = "".join(c for c in folder_name if c.isalnum() or c == "_")

    if not folder_name:
        raise HTTPException(status_code=400, detail="Invalid folder name")

    folder_path = tests_directory / folder_name

    # Check if folder already exists
    if folder_path.exists():
        raise HTTPException(status_code=409, detail="Folder already exists")

    try:
        folder_path.mkdir(parents=True, exist_ok=False)

        # Create a README file with description if provided
        if description:
            readme_path = folder_path / "README.md"
            with open(readme_path, "w") as f:
                f.write(f"# {name}\n\n{description}\n")

        return {
            "success": True,
            "folder": FolderInfo(
                name=folder_name,
                path=folder_name,
                test_count=0,
                description=description,
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating folder: {str(e)}")


@app.get("/api/folders/{folder_name:path}")
async def get_folder_info(
    folder_name: str,
):
    """Get information about a specific folder"""
    folder_path = tests_directory / folder_name

    if not folder_path.exists() or not folder_path.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    # Count tests
    test_count = len(list(folder_path.rglob("*.yaml")))

    # Check for README
    description = None
    readme_path = folder_path / "README.md"
    if readme_path.exists():
        try:
            with open(readme_path, "r") as f:
                content = f.read()
                # Extract first paragraph as description
                lines = content.split("\n")
                for line in lines[1:]:  # Skip title
                    if line.strip():
                        description = line.strip()
                        break
        except Exception:
            pass

    return FolderInfo(
        name=folder_path.name,
        path=str(folder_path.relative_to(tests_directory)),
        test_count=test_count,
        description=description,
    )


# ==================== RECORDER ENDPOINTS ====================


@app.post("/api/recorder/start")
async def start_recording(session: RecordingSession):
    """Start a new Playwright recording session"""
    try:
        # Check if playwright is installed
        from playwright.async_api import async_playwright  # noqa: F401

        session_id = session.session_id
        recording_sessions[session_id] = {
            "url": session.url,
            "headless": session.headless,
            "actions": [],
            "browser": None,
            "page": None,
            "context": None,
        }

        # Start recording task in background
        asyncio.create_task(run_recorder(session_id, session.url, session.headless))

        return {
            "success": True,
            "session_id": session_id,
            "message": "Recording session started. Browser window will open shortly.",
        }
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Playwright not installed. Run: pip install playwright && playwright install",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error starting recorder: {str(e)}"
        )


@app.get("/api/recorder/status/{session_id}")
async def get_recording_status(session_id: str):
    """Get status of a recording session"""
    if session_id not in recording_sessions:
        raise HTTPException(status_code=404, detail="Recording session not found")

    session = recording_sessions[session_id]
    return {
        "session_id": session_id,
        "url": session["url"],
        "action_count": len(session["actions"]),
        "is_active": session.get("browser") is not None,
    }


@app.get("/api/recorder/actions/{session_id}")
async def get_recorded_actions(session_id: str):
    """Get all recorded actions for a session"""
    if session_id not in recording_sessions:
        raise HTTPException(status_code=404, detail="Recording session not found")

    return {
        "session_id": session_id,
        "actions": recording_sessions[session_id]["actions"],
    }


@app.post("/api/recorder/stop/{session_id}")
async def stop_recording(session_id: str):
    """Stop a recording session"""
    if session_id not in recording_sessions:
        raise HTTPException(status_code=404, detail="Recording session not found")

    session = recording_sessions[session_id]
    actions = session["actions"]

    # Close browser if still open
    try:
        if session.get("browser"):
            await session["browser"].close()
    except Exception:
        pass

    # Keep actions but mark as stopped
    session["browser"] = None
    session["page"] = None
    session["context"] = None

    return {
        "success": True,
        "session_id": session_id,
        "actions": actions,
        "action_count": len(actions),
    }


async def run_recorder(session_id: str, url: str, headless: bool):
    """Run Playwright recorder and capture actions"""
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()

            # Store in session
            recording_sessions[session_id]["browser"] = browser
            recording_sessions[session_id]["page"] = page
            recording_sessions[session_id]["context"] = context

            # Navigate to URL
            await page.goto(url, wait_until="domcontentloaded")

            # Set up action recording function first
            async def record_action_wrapper(action_type: str, params: Dict[str, Any]):
                """Wrapper to make record_action async for Playwright"""
                try:
                    print(
                        f"[EasyBDD Recorder] recordAction called: {action_type} with params: {params}"
                    )
                    record_action(session_id, action_type, params)
                    print("[EasyBDD Recorder] Action recorded successfully")
                except Exception as e:
                    print(f"[EasyBDD Recorder] Error in recordAction wrapper: {e}")
                    import traceback

                    traceback.print_exc()

            await page.expose_function("recordAction", record_action_wrapper)
            print("[EasyBDD Recorder] recordAction function exposed to page")

            # Test that the function is accessible
            test_result = await page.evaluate(
                """
                () => {
                    if (typeof window.recordAction === 'function') {
                        return 'recordAction is available';
                    } else {
                        return 'recordAction is NOT available';
                    }
                }
            """
            )
            print(f"[EasyBDD Recorder] Function availability test: {test_result}")

            print(
                "[EasyBDD Recorder] Injecting highlight/locator script into page:",
                page.url,
            )

            # Define the recorder script
            recorder_script = """
                (function() {
                    'use strict';

                    // Check if script has already been injected - MUST be first!
                    if (window.__easybdd_recorder_injected__) {
                        console.log('[EasyBDD Recorder] Script already injected, skipping...');
                        return;
                    }

                    // Mark as injected immediately
                    window.__easybdd_recorder_injected__ = true;

                    console.log('[EasyBDD Recorder] Highlight/locator script starting...');

                    // Check if recordAction is available
                    if (typeof window.recordAction === 'undefined') {
                        console.error('[EasyBDD Recorder] ERROR: window.recordAction is not defined!');
                        window.__easybdd_recorder_injected__ = false; // Reset flag on error
                        return;
                    }
                    console.log('[EasyBDD Recorder] window.recordAction is available');

                    // Use a namespace to avoid variable conflicts
                    // Always reset/recreate the namespace to avoid conflicts
                    window.__easybdd_recorder__ = window.__easybdd_recorder__ || {};

                    // Clean up any existing elements from previous injection
                    if (window.__easybdd_recorder__.highlightEl) {
                        try { window.__easybdd_recorder__.highlightEl.remove(); } catch(e) {}
                    }
                    if (window.__easybdd_recorder__.locatorTooltip) {
                        try { window.__easybdd_recorder__.locatorTooltip.remove(); } catch(e) {}
                    }
                    if (window.__easybdd_recorder__.recordingBadge) {
                        try { window.__easybdd_recorder__.recordingBadge.remove(); } catch(e) {}
                    }
                    if (window.__easybdd_recorder__.contextMenu) {
                        try { window.__easybdd_recorder__.contextMenu.remove(); } catch(e) {}
                    }

                    // --- Highlight and locator overlay ---
                    // Use window.__easybdd_recorder__ directly to avoid const redeclaration
                    if (!window.__easybdd_recorder__.highlightEl) window.__easybdd_recorder__.highlightEl = null;
                    if (!window.__easybdd_recorder__.locatorTooltip) window.__easybdd_recorder__.locatorTooltip = null;
                    if (!window.__easybdd_recorder__.recordingBadge) window.__easybdd_recorder__.recordingBadge = null;
                    if (!window.__easybdd_recorder__.contextMenu) window.__easybdd_recorder__.contextMenu = null;
                    if (!window.__easybdd_recorder__.contextTarget) window.__easybdd_recorder__.contextTarget = null;

                    function showHighlight(element) {
                        if (!element) return;
                        removeHighlight();
                        window.__easybdd_recorder__.highlightEl = document.createElement('div');
                        window.__easybdd_recorder__.highlightEl.className = '__recorder_highlight__';
                        const rect = element.getBoundingClientRect();
                        window.__easybdd_recorder__.highlightEl.style.cssText = `
                            position: fixed;
                            left: ${rect.left + window.scrollX}px;
                            top: ${rect.top + window.scrollY}px;
                            width: ${rect.width}px;
                            height: ${rect.height}px;
                            background: rgba(59,130,246,0.08);
                            border: 2px solid #3b82f6;
                            border-radius: 4px;
                            z-index: 999998;
                            pointer-events: none;
                            box-shadow: 0 0 0 2px #3b82f644;
                        `;
                        document.body.appendChild(window.__easybdd_recorder__.highlightEl);
                    }
                    function removeHighlight() {
                        if (window.__easybdd_recorder__.highlightEl) window.__easybdd_recorder__.highlightEl.remove();
                        window.__easybdd_recorder__.highlightEl = null;
                    }
                    function showLocatorTooltip(element) {
                        removeLocatorTooltip();
                        const info = getSelectorInfo(element);
                        window.__easybdd_recorder__.locatorTooltip = document.createElement('div');
                        window.__easybdd_recorder__.locatorTooltip.className = '__recorder_locator__';
                        const rect = element.getBoundingClientRect();
                        // Position tooltip above the element with more space to avoid blocking
                        // Try to position it 100px above, or to the right if not enough space above
                        const viewportHeight = window.innerHeight;
                        const spaceAbove = rect.top;
                        const spaceBelow = viewportHeight - rect.bottom;
                        const spaceRight = window.innerWidth - rect.right;

                        let tooltipTop, tooltipLeft;
                        if (spaceAbove > 120) {
                            // Position above with good clearance
                            tooltipTop = rect.top + window.scrollY - 110;
                            tooltipLeft = rect.left + window.scrollX + (rect.width / 2) - 200; // Center it relative to element
                        } else if (spaceRight > 450) {
                            // Position to the right
                            tooltipTop = rect.top + window.scrollY;
                            tooltipLeft = rect.right + window.scrollX + 20;
                        } else {
                            // Position below if no space above or right
                            tooltipTop = rect.bottom + window.scrollY + 10;
                            tooltipLeft = rect.left + window.scrollX + (rect.width / 2) - 200;
                        }

                        window.__easybdd_recorder__.locatorTooltip.style.cssText = `
                            position: fixed;
                            left: ${tooltipLeft}px;
                            top: ${tooltipTop}px;
                            background: #1e293b;
                            color: #fff;
                            padding: 8px 12px;
                            border-radius: 6px;
                            font-size: 12px;
                            font-family: 'Monaco', 'Courier New', monospace;
                            z-index: 999999;
                            pointer-events: none;
                            opacity: 0.95;
                            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                            max-width: 400px;
                            line-height: 1.6;
                            border: 1px solid #3b82f6;
                        `;

                        window.__easybdd_recorder__.locatorTooltip.innerHTML = `
                            <div style="color: #3b82f6; font-weight: bold; margin-bottom: 4px;">Selector:</div>
                            <div style="color: #60a5fa; word-break: break-all;">${info.selector}</div>
                            <div style="margin-top: 6px; padding-top: 6px; border-top: 1px solid #334155; color: #94a3b8; font-size: 11px;">
                                ${info.details}
                            </div>
                        `;
                        document.body.appendChild(window.__easybdd_recorder__.locatorTooltip);
                    }
                    function removeLocatorTooltip() {
                        if (window.__easybdd_recorder__.locatorTooltip) window.__easybdd_recorder__.locatorTooltip.remove();
                        window.__easybdd_recorder__.locatorTooltip = null;
                    }
                    function showRecordingBadge() {
                        if (window.__easybdd_recorder__.recordingBadge) return;
                        window.__easybdd_recorder__.recordingBadge = document.createElement('div');
                        window.__easybdd_recorder__.recordingBadge.className = '__recorder_badge__';
                        window.__easybdd_recorder__.recordingBadge.style.cssText = `
                            position: fixed;
                            right: 24px;
                            bottom: 24px;
                            background: #3b82f6;
                            color: #fff;
                            font-weight: bold;
                            font-size: 15px;
                            padding: 8px 18px;
                            border-radius: 24px;
                            z-index: 999999;
                            box-shadow: 0 2px 12px rgba(59,130,246,0.18);
                            pointer-events: none;
                            opacity: 0.92;
                        `;
                        window.__easybdd_recorder__.recordingBadge.textContent = '● Recording';
                        document.body.appendChild(window.__easybdd_recorder__.recordingBadge);
                    }
                    function removeRecordingBadge() {
                        if (window.__easybdd_recorder__.recordingBadge) window.__easybdd_recorder__.recordingBadge.remove();
                        window.__easybdd_recorder__.recordingBadge = null;
                    }

                    function getSelector(element) {
                        if (!element || !element.tagName) return '';

                        // Priority 1: ID selector (most reliable)
                        if (element.id) {
                            return '#' + element.id;
                        }

                        // Priority 2: Name attribute (for form elements)
                        if (element.name) {
                            return element.tagName.toLowerCase() + '[name="' + element.name + '"]';
                        }

                        // Priority 3: Data-testid or data-cy (common test attributes)
                        if (element.getAttribute('data-testid')) {
                            return '[data-testid="' + element.getAttribute('data-testid') + '"]';
                        }
                        if (element.getAttribute('data-cy')) {
                            return '[data-cy="' + element.getAttribute('data-cy') + '"]';
                        }

                        // Priority 4: Class name (first meaningful class)
                        if (element.className && typeof element.className === 'string') {
                            const classes = element.className.trim().split(/\\s+/).filter(c =>
                                c && !c.startsWith('__recorder') && c.length > 0
                            );
                            if (classes.length > 0) {
                                return element.tagName.toLowerCase() + '.' + classes[0];
                            }
                        }

                        // Priority 5: Role attribute
                        if (element.getAttribute('role')) {
                            return element.tagName.toLowerCase() + '[role="' + element.getAttribute('role') + '"]';
                        }

                        // Priority 6: Text content (for buttons, links)
                        const text = element.textContent?.trim();
                        if (text && text.length < 50 && (element.tagName === 'BUTTON' || element.tagName === 'A')) {
                            return element.tagName.toLowerCase() + ':has-text("' + text.substring(0, 30) + '")';
                        }

                        // Priority 7: Tag with parent context
                        if (element.parentElement) {
                            const parentTag = element.parentElement.tagName.toLowerCase();
                            const siblings = Array.from(element.parentElement.children);
                            const index = siblings.indexOf(element);
                            if (index >= 0) {
                                return parentTag + ' > ' + element.tagName.toLowerCase() + ':nth-child(' + (index + 1) + ')';
                            }
                        }

                        // Fallback: Just tag name
                        return element.tagName.toLowerCase();
                    }

                    function getSelectorInfo(element) {
                        const selector = getSelector(element);
                        const info = [];

                        if (element.id) info.push('ID: ' + element.id);
                        if (element.name) info.push('Name: ' + element.name);
                        if (element.className && typeof element.className === 'string') {
                            const classes = element.className.trim().split(/\\s+/).filter(c => c && !c.startsWith('__recorder'));
                            if (classes.length > 0) info.push('Classes: ' + classes.join(', '));
                        }
                        if (element.tagName) info.push('Tag: ' + element.tagName.toLowerCase());
                        const text = element.textContent?.trim();
                        if (text && text.length < 100) info.push('Text: ' + text.substring(0, 50));

                        return {
                            selector: selector,
                            details: info.join(' | ')
                        };
                    }

                    // Show recording badge to confirm script is running
                    showRecordingBadge();
                    console.log('[EasyBDD Recorder] Recording badge shown, script fully loaded');

                    // Test recordAction function (wrapped in async IIFE to allow await)
                    (async function() {
                        if (typeof window.recordAction === 'function') {
                            console.log('[EasyBDD Recorder] ✅ window.recordAction is a function');
                            // Test call
                            try {
                                await window.recordAction('test.action', {test: 'initialization'});
                                console.log('[EasyBDD Recorder] ✅ Test recordAction call succeeded');
                            } catch (error) {
                                console.error('[EasyBDD Recorder] ❌ Test recordAction call failed:', error);
                            }
                        } else {
                            console.error('[EasyBDD Recorder] ❌ window.recordAction is NOT a function! Type:', typeof window.recordAction);
                        }
                    })();

                    // Mouse over highlighting
                    document.addEventListener('mouseover', (e) => {
                        if (e.target.classList.contains('__recorder_highlight__') ||
                            e.target.classList.contains('__recorder_locator__') ||
                            e.target.classList.contains('__recorder_badge__') ||
                            e.target.closest('#__recorder_context_menu__')) {
                            return;
                        }
                        showHighlight(e.target);
                        showLocatorTooltip(e.target);
                    }, true);

                    document.addEventListener('mouseout', (e) => {
                        if (e.target.classList.contains('__recorder_highlight__') ||
                            e.target.classList.contains('__recorder_locator__') ||
                            e.target.classList.contains('__recorder_badge__')) {
                            return;
                        }
                        // Only remove if not moving to a child element
                        if (!e.relatedTarget || !e.target.contains(e.relatedTarget)) {
                            removeHighlight();
                            removeLocatorTooltip();
                        }
                    }, true);

                    // Context menu for right-click assertions (using namespace)
                    function createContextMenu() {
                        const menu = document.createElement('div');
                        menu.id = '__recorder_context_menu__';
                        menu.style.cssText = `
                            position: fixed;
                            background: white;
                            border: 1px solid #ddd;
                            border-radius: 6px;
                            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                            z-index: 1000000;
                            min-width: 220px;
                            padding: 4px 0;
                            font-size: 14px;
                        `;

                        const options = [
                        { label: '🎬 Assert Element Visible', action: 'assert_visible' },
                        { label: '🚫 Assert Element Not Visible', action: 'assert_not_visible' },
                        { label: '✅ Assert Element Enabled', action: 'assert_enabled' },
                        { label: '❌ Assert Element Disabled', action: 'assert_disabled' },
                        { label: '📝 Assert Text Contains...', action: 'assert_text_contains' },
                        { label: '📋 Assert Text Equals...', action: 'assert_text_equals' },
                        { label: '🔢 Assert Count...', action: 'assert_count' },
                    ];

                    options.forEach(opt => {
                        const item = document.createElement('div');
                        item.textContent = opt.label;
                        item.style.cssText = `
                            padding: 8px 16px;
                            cursor: pointer;
                            color: #333;
                        `;
                        item.onmouseover = () => item.style.background = '#f0f0f0';
                        item.onmouseout = () => item.style.background = 'white';
                        item.onclick = () => handleAssertAction(opt.action);
                        menu.appendChild(item);
                    });

                    return menu;
                }

                // Handle assertion action
                async function handleAssertAction(action) {
                    const selector = getSelector(window.__easybdd_recorder__.contextTarget);
                    let params = { selector: selector };

                    if (action === 'assert_text_contains' || action === 'assert_text_equals') {
                        const text = prompt('Enter expected text:', window.__easybdd_recorder__.contextTarget.textContent.trim());
                        if (!text) {
                            hideContextMenu();
                            return;
                        }
                        params.text = text;
                    } else if (action === 'assert_count') {
                        const count = prompt('Enter expected count:', '1');
                        if (!count) {
                            hideContextMenu();
                            return;
                        }
                        params.count = parseInt(count);
                    }

                    // Map action to Easy BDD action name
                    const actionMap = {
                        'assert_visible': 'test.assert_element_visible',
                        'assert_not_visible': 'test.assert_element_not_visible',
                        'assert_enabled': 'test.assert_element_enabled',
                        'assert_disabled': 'test.assert_element_disabled',
                        'assert_text_contains': 'test.assert_text_contains',
                        'assert_text_equals': 'test.assert_text_equals',
                        'assert_count': 'test.assert_element_count'
                    };

                    if (window.recordAction) {
                        await window.recordAction(actionMap[action], params);
                    }

                    hideContextMenu();
                }

                function hideContextMenu() {
                    if (window.__easybdd_recorder__.contextMenu) {
                        window.__easybdd_recorder__.contextMenu.remove();
                        window.__easybdd_recorder__.contextMenu = null;
                        window.__easybdd_recorder__.contextTarget = null;
                    }
                }

                // Show context menu on right-click
                document.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    window.__easybdd_recorder__.contextTarget = e.target;

                    hideContextMenu();
                    window.__easybdd_recorder__.contextMenu = createContextMenu();
                    window.__easybdd_recorder__.contextMenu.style.left = e.pageX + 'px';
                    window.__easybdd_recorder__.contextMenu.style.top = e.pageY + 'px';
                    document.body.appendChild(window.__easybdd_recorder__.contextMenu);
                }, true);

                // Hide context menu on click outside
                document.addEventListener('click', (e) => {
                    if (window.__easybdd_recorder__.contextMenu && !window.__easybdd_recorder__.contextMenu.contains(e.target)) {
                        hideContextMenu();
                    }
                });

                // Track clicks (but not on context menu or recorder UI)
                document.addEventListener('click', async (e) => {
                    if (e.target.closest('#__recorder_context_menu__') ||
                        e.target.classList.contains('__recorder_highlight__') ||
                        e.target.classList.contains('__recorder_locator__') ||
                        e.target.classList.contains('__recorder_badge__')) {
                        return;
                    }

                    const selector = getSelector(e.target);
                    console.log('[EasyBDD Recorder] Click detected, selector:', selector);

                    if (!window.recordAction) {
                        console.error('[EasyBDD Recorder] ERROR: window.recordAction is not available!');
                        return;
                    }

                    if (!selector) {
                        console.warn('[EasyBDD Recorder] No selector generated for element');
                        return;
                    }

                    try {
                        await window.recordAction('browser.click', {selector: selector});
                        console.log('[EasyBDD Recorder] Click action recorded:', selector);
                    } catch (error) {
                        console.error('[EasyBDD Recorder] Error recording click:', error);
                    }
                }, true);

                // Track input/typing with improved debouncing to avoid splitting words
                let typingTimeout = null;
                let lastRecordedValue = null;
                let lastRecordedSelector = null;
                document.addEventListener('input', async (e) => {
                    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
                        const selector = getSelector(e.target);
                        const currentValue = e.target.value || e.target.textContent || '';

                        // Clear existing timeout
                        clearTimeout(typingTimeout);

                        // Only record if the value actually changed from what we last recorded
                        // This prevents recording partial words
                        if (currentValue === lastRecordedValue && selector === lastRecordedSelector) {
                            return; // No change, skip
                        }

                        // Wait for user to stop typing (1.5 seconds) before recording
                        // This ensures we capture the complete word/phrase, not partial input
                        typingTimeout = setTimeout(async () => {
                            const finalValue = e.target.value || e.target.textContent || '';

                            // Double-check the value hasn't changed since we set the timeout
                            // and that it's different from what we last recorded
                            if (finalValue === lastRecordedValue && selector === lastRecordedSelector) {
                                return; // Already recorded this value
                            }

                            console.log('[EasyBDD Recorder] Input detected, selector:', selector, 'text length:', finalValue.length);

                            if (!window.recordAction) {
                                console.error('[EasyBDD Recorder] ERROR: window.recordAction is not available!');
                                return;
                            }

                            if (!selector) {
                                console.warn('[EasyBDD Recorder] No selector generated for input element');
                                return;
                            }

                            if (!finalValue) {
                                console.warn('[EasyBDD Recorder] Input detected but no text value');
                                lastRecordedValue = '';
                                lastRecordedSelector = selector;
                                return;
                            }

                            try {
                                await window.recordAction('browser.type', {
                                    selector: selector,
                                    text: finalValue
                                });
                                console.log('[EasyBDD Recorder] Type action recorded:', selector, 'text:', finalValue);

                                // Update last recorded values
                                lastRecordedValue = finalValue;
                                lastRecordedSelector = selector;
                            } catch (error) {
                                console.error('[EasyBDD Recorder] Error recording type:', error);
                            }
                        }, 1500); // Increased from 300ms to 1500ms to wait for complete input
                    }
                }, true);

                // Track form submissions
                document.addEventListener('submit', async (e) => {
                    const selector = getSelector(e.target);
                    if (window.recordAction && selector) {
                        await window.recordAction('browser.submit', {selector: selector});
                    }
                }, true);

                // Track select changes
                document.addEventListener('change', async (e) => {
                    if (e.target.tagName === 'SELECT') {
                        const selector = getSelector(e.target);
                        const value = e.target.value;
                        if (window.recordAction && selector) {
                            await window.recordAction('browser.select', {
                                selector: selector,
                                value: value
                            });
                        }
                    }
                }, true);

                // Track checkbox/radio changes
                document.addEventListener('change', async (e) => {
                    if (e.target.type === 'checkbox' || e.target.type === 'radio') {
                        const selector = getSelector(e.target);
                        const checked = e.target.checked;
                        if (window.recordAction && selector) {
                            await window.recordAction('browser.check', {
                                selector: selector,
                                checked: checked
                            });
                        }
                    }
                }, true);
                })();
            """

            # Wait a bit for page to fully load
            await page.wait_for_load_state("networkidle", timeout=5000)

            # Inject script immediately after page loads
            try:
                result = await page.evaluate(recorder_script)
                print(f"[EasyBDD Recorder] Script injected successfully: {result}")
            except Exception as e:
                print(f"[EasyBDD Recorder] Error injecting script: {e}")
                import traceback

                traceback.print_exc()

            # Attach event listeners for recording navigation
            async def on_navigation(frame):
                if frame == page.main_frame:
                    # Wait for page to load
                    try:
                        await frame.wait_for_load_state("networkidle", timeout=5000)
                        # Clear the injection flag and namespace to allow re-injection
                        await page.evaluate(
                            """
                            window.__easybdd_recorder_injected__ = false;
                            if (window.__easybdd_recorder__) {
                                // Clean up old elements
                                if (window.__easybdd_recorder__.highlightEl) {
                                    window.__easybdd_recorder__.highlightEl.remove();
                                }
                                if (window.__easybdd_recorder__.locatorTooltip) {
                                    window.__easybdd_recorder__.locatorTooltip.remove();
                                }
                                if (window.__easybdd_recorder__.recordingBadge) {
                                    window.__easybdd_recorder__.recordingBadge.remove();
                                }
                                if (window.__easybdd_recorder__.contextMenu) {
                                    window.__easybdd_recorder__.contextMenu.remove();
                                }
                                // Reset namespace
                                window.__easybdd_recorder__ = {};
                            }
                        """
                        )
                        # Re-inject script after navigation
                        await page.evaluate(recorder_script)
                        record_action(session_id, "browser.open", {"url": frame.url})
                        print(
                            f"[EasyBDD Recorder] Script re-injected after navigation to {frame.url}"
                        )
                    except Exception as e:
                        print(
                            f"[EasyBDD Recorder] Error re-injecting script after navigation: {e}"
                        )
                        import traceback

                        traceback.print_exc()

            page.on("framenavigated", on_navigation)

            # Verify script is working by checking console
            page.on("console", lambda msg: print(f"[Browser Console] {msg.text}"))

            # Keep browser open until stopped
            while recording_sessions.get(session_id, {}).get("browser"):
                await asyncio.sleep(1)

    except Exception as e:
        print(f"Recorder error: {e}")
        if session_id in recording_sessions:
            recording_sessions[session_id]["browser"] = None


def record_action(session_id: str, action: str, parameters: Dict[str, Any]):
    """Record an action to the session"""
    print(
        f"[RECORDER] record_action called: session_id={session_id}, action={action}, params={parameters}"
    )

    if session_id not in recording_sessions:
        print(
            f"[RECORDER] ERROR: Session {session_id} not found in recording_sessions!"
        )
        print(f"[RECORDER] Available sessions: {list(recording_sessions.keys())}")
        return

    recorded_action = {
        "action": action,
        "parameters": parameters,
        "timestamp": datetime.now().isoformat(),
    }
    recording_sessions[session_id]["actions"].append(recorded_action)

    # Log for debugging
    print(f"[RECORDER] ✅ Session {session_id}: {action} with params {parameters}")
    print(
        f"[RECORDER] Total actions in session: {len(recording_sessions[session_id]['actions'])}"
    )

    # Broadcast to connected websockets
    try:
        asyncio.create_task(
            broadcast_message(
                {
                    "type": "recorded_action",
                    "session_id": session_id,
                    "action": recorded_action,
                }
            )
        )
    except Exception as e:
        print(f"[RECORDER] Error broadcasting message: {e}")


# ==================== SETTINGS API ====================

SETTINGS_FILE = Path(__file__).parent / "test_builder_settings.json"


class TeamsConfig(BaseModel):
    """Teams notification configuration"""

    enabled: bool = False
    webhook_url: str = ""
    notify_on_success: bool = False
    include_screenshots: bool = False
    include_html_report: bool = False


class TeamsTestRequest(BaseModel):
    """Request model for testing Teams connection"""

    webhook_url: str


def load_settings() -> Dict[str, Any]:
    """Load settings from JSON file"""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading settings: {e}")
            return {}
    return {}


def save_settings(settings: Dict[str, Any]) -> None:
    """Save settings to JSON file"""
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"Error saving settings: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {e}")


@app.get("/api/settings/teams")
async def get_teams_config():
    """Get Teams notification configuration"""
    settings = load_settings()
    teams_config = settings.get("teams", {})

    # Also check environment variable for webhook URL (for backward compatibility)
    if not teams_config.get("webhook_url") and os.environ.get("TEAMS_WEBHOOK_URL"):
        teams_config["webhook_url"] = os.environ.get("TEAMS_WEBHOOK_URL")

    return teams_config


@app.put("/api/settings/teams")
async def update_teams_config(config: TeamsConfig):
    """Update Teams notification configuration"""
    settings = load_settings()
    settings["teams"] = config.model_dump()
    save_settings(settings)

    # Also set environment variable for backward compatibility
    if config.webhook_url:
        os.environ["TEAMS_WEBHOOK_URL"] = config.webhook_url

    return {"success": True, "message": "Teams configuration updated"}


async def send_teams_notification(
    test_id: str, test_result: Dict[str, Any], test_path: Path
):
    """Send Teams notification for test completion"""
    try:
        settings = load_settings()
        teams_config = settings.get("teams", {})

        # Check if Teams notifications are enabled
        if not teams_config.get("enabled", False):
            return

        webhook_url = teams_config.get("webhook_url", "")
        if not webhook_url:
            # Fallback to environment variable
            webhook_url = os.environ.get("TEAMS_WEBHOOK_URL", "")

        if not webhook_url:
            print("[TEAMS] Webhook URL not configured, skipping notification")
            return

        # Check if we should notify (only failures or all)
        status = test_result.get("status", "unknown")
        notify_on_success = teams_config.get("notify_on_success", False)

        if status == "completed" and not notify_on_success:
            print(
                "[TEAMS] Test passed and notify_on_success is disabled, skipping notification"
            )
            return

        # Prepare message
        test_name = test_path.stem if test_path else "Unknown Test"
        status_emoji = "✅" if status == "completed" else "❌"
        status_text = "PASSED" if status == "completed" else "FAILED"

        # Calculate duration
        started = test_result.get("started")
        finished = test_result.get("finished")
        duration = "N/A"
        if started and finished:
            try:
                start_time = datetime.fromisoformat(started.replace("Z", "+00:00"))
                end_time = datetime.fromisoformat(finished.replace("Z", "+00:00"))
                duration_seconds = (end_time - start_time).total_seconds()
                if duration_seconds < 60:
                    duration = f"{duration_seconds:.1f}s"
                else:
                    duration = f"{duration_seconds / 60:.1f}m"
            except Exception:
                pass

        # Get output summary (last few lines)
        output = test_result.get("output", [])
        output_summary = "\n".join(output[-10:]) if output else "No output available"

        message_body = [
            {
                "type": "TextBlock",
                "text": f"{status_emoji} Test Execution: {status_text}",
                "wrap": True,
                "weight": "Bolder",
                "size": "Large",
                "color": "Good" if status == "completed" else "Attention",
            },
            {
                "type": "TextBlock",
                "text": f"**Test:** {test_name}",
                "wrap": True,
                "spacing": "Medium",
            },
            {
                "type": "TextBlock",
                "text": f"**Duration:** {duration}",
                "wrap": True,
                "spacing": "Small",
            },
        ]

        # Add error details if failed
        if status != "completed":
            error = test_result.get("error", "")
            if error:
                message_body.append(
                    {
                        "type": "TextBlock",
                        "text": f"**Error:** {error[:200]}",
                        "wrap": True,
                        "spacing": "Medium",
                        "color": "Attention",
                    }
                )

        # Add output summary
        if output_summary and len(output_summary) > 0:
            message_body.append(
                {
                    "type": "TextBlock",
                    "text": f"**Output:**\n```\n{output_summary[-500:]}\n```",
                    "wrap": True,
                    "spacing": "Medium",
                    "fontType": "Monospace",
                    "size": "Small",
                }
            )

        # Add timestamp
        message_body.append(
            {
                "type": "TextBlock",
                "text": f"*Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
                "wrap": True,
                "isSubtle": True,
                "size": "Small",
                "spacing": "Large",
            }
        )

        # Prepare card actions (for HTML report link)
        card_actions = []
        include_html_report = teams_config.get("include_html_report", False)
        if include_html_report:
            result_file = test_result.get("result_file")
            if result_file:
                # Get base URL (try to get from environment or use default)
                base_url = os.environ.get("BASE_URL", "http://localhost:8000")
                report_url = f"{base_url}/api/results/{result_file}/generate-report"

                card_actions.append(
                    {
                        "type": "Action.OpenUrl",
                        "title": "📊 Download HTML Report",
                        "url": report_url,
                    }
                )

        teams_message = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "type": "AdaptiveCard",
                        "body": message_body,
                        "actions": card_actions if card_actions else None,
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "version": "1.2",
                    },
                }
            ],
        }

        # Remove actions if empty (some Teams clients don't like empty arrays)
        if not card_actions:
            teams_message["attachments"][0]["content"].pop("actions", None)

        # Send notification
        try:
            import requests

            response = requests.post(
                webhook_url,
                headers={"Content-Type": "application/json"},
                json=teams_message,
                timeout=10,
            )
            if response.status_code in [200, 202]:
                print(f"[TEAMS] Notification sent successfully for test {test_id}")
            else:
                print(
                    f"[TEAMS] Failed to send notification. Status: {response.status_code}"
                )
        except ImportError:
            print("[TEAMS] requests library not available, cannot send notification")
        except Exception as e:
            print(f"[TEAMS] Error sending notification: {e}")
    except Exception as e:
        print(f"[TEAMS] Error preparing notification: {e}")


@app.post("/api/settings/teams/test")
async def test_teams_connection(request: TeamsTestRequest):
    """Test Teams webhook connection by sending a test message"""
    print(
        f"[TEAMS TEST] Received test request with webhook_url: {request.webhook_url[:50]}..."
    )
    webhook_url = request.webhook_url

    if not webhook_url:
        raise HTTPException(status_code=400, detail="Webhook URL is required")

    try:
        import requests

        test_message = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "type": "AdaptiveCard",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": "✅ Test notification from Easy BDD Test Builder",
                                "wrap": True,
                                "weight": "Bolder",
                                "size": "Large",
                            },
                            {
                                "type": "TextBlock",
                                "text": "If you received this message, your Teams webhook is configured correctly!",
                                "wrap": True,
                                "spacing": "Medium",
                            },
                            {
                                "type": "TextBlock",
                                "text": f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                                "wrap": True,
                                "isSubtle": True,
                                "size": "Small",
                            },
                        ],
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "version": "1.2",
                    },
                }
            ],
        }

        response = requests.post(
            webhook_url,
            headers={"Content-Type": "application/json"},
            json=test_message,
            timeout=10,
        )

        if response.status_code == 200 or response.status_code == 202:
            return {
                "success": True,
                "message": "Test notification sent successfully! Check your Teams channel.",
            }
        else:
            return {
                "success": False,
                "message": f"Failed to send notification. Status: {response.status_code}, Response: {response.text[:200]}",
            }
    except ImportError:
        raise HTTPException(status_code=500, detail="requests library not available")
    except Exception as e:
        return {
            "success": False,
            "message": f"Error sending test notification: {str(e)}",
        }


# Catch-all route for client-side routing (must be last)
@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """
    Serve the frontend HTML file for any route that doesn't match API endpoints.
    This allows client-side routing to work when refreshing the page.
    """
    # Don't serve HTML for API routes or static files
    if (
        full_path.startswith("api/")
        or full_path.startswith("static/")
        or full_path.startswith("favicon.ico")
    ):
        raise HTTPException(status_code=404, detail="Not Found")

    html_path = Path(__file__).parent / "static" / "test_builder.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse("<h1>Test Builder</h1><p>Frontend not found</p>")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
