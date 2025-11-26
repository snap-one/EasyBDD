# Test Builder API Reference

Complete API reference for the Easy BDD Test Builder web application.

**Base URL**: `http://localhost:8000` (default)

**API Documentation**: Interactive Swagger UI available at `/docs` when server is running.

---

## Table of Contents

1. [Test Management](#test-management)
2. [Test Execution](#test-execution)
3. [Test Suites](#test-suites)
4. [Variables](#variables)
5. [Actions](#actions)
6. [Results & Reports](#results--reports)
7. [Dashboard & Metrics](#dashboard--metrics)
8. [Workspaces](#workspaces)
9. [Documentation](#documentation)
10. [Settings](#settings)

---

## Test Management

### List All Tests

**GET** `/api/tests`

Get a list of all test files.

**Query Parameters:**
- `workspace` (optional): Filter by workspace name
- `folder` (optional): Filter by folder path

**Response:**
```json
{
  "tests": [
    {
      "id": "tests/cases/example_test.yaml",
      "name": "Example Test",
      "description": "Test description",
      "tags": ["smoke", "critical"],
      "workspace": "My Workspace",
      "folder": "tests/cases",
      "step_count": 5,
      "has_setup": true,
      "has_cleanup": false
    }
  ],
  "total": 1
}
```

### Get Test Details

**GET** `/api/tests/{test_id}`

Get detailed information about a specific test.

**Path Parameters:**
- `test_id`: Test file path (e.g., `tests/cases/example_test.yaml`)

**Response:**
```json
{
  "id": "tests/cases/example_test.yaml",
  "name": "Example Test",
  "description": "Test description",
  "tags": ["smoke"],
  "workspace": "My Workspace",
  "variables": {
    "base_url": "https://example.com"
  },
  "browser_config": {
    "headless": true
  },
  "setup": [...],
  "steps": [...],
  "cleanup": [...]
}
```

### Create Test

**POST** `/api/tests`

Create a new test file.

**Request Body:**
```json
{
  "name": "New Test",
  "description": "Test description",
  "tags": ["smoke"],
  "workspace": "My Workspace",
  "folder": "tests/cases",
  "variables": {},
  "browser_config": {},
  "setup": [],
  "steps": [],
  "cleanup": []
}
```

**Response:**
```json
{
  "id": "tests/cases/new_test.yaml",
  "message": "Test created successfully"
}
```

### Update Test

**PUT** `/api/tests/{test_id}`

Update an existing test file.

**Path Parameters:**
- `test_id`: Test file path

**Request Body:** Same as Create Test

**Response:**
```json
{
  "message": "Test updated successfully"
}
```

### Delete Test

**DELETE** `/api/tests/{test_id}`

Delete a test file.

**Path Parameters:**
- `test_id`: Test file path

**Response:**
```json
{
  "message": "Test deleted successfully"
}
```

### Duplicate Test

**POST** `/api/tests/{test_id}/duplicate`

Create a copy of an existing test.

**Path Parameters:**
- `test_id`: Test file path

**Query Parameters:**
- `new_name` (optional): Name for the duplicate test

**Response:**
```json
{
  "id": "tests/cases/new_test_copy.yaml",
  "message": "Test duplicated successfully"
}
```

### Validate Test

**POST** `/api/tests/validate`

Validate a test definition without saving.

**Request Body:**
```json
{
  "name": "Test Name",
  "steps": [...],
  "variables": {},
  "browser_config": {}
}
```

**Response:**
```json
{
  "valid": true,
  "errors": [],
  "warnings": []
}
```

---

## Test Execution

### Execute Test

**POST** `/api/tests/execute`

Execute a test and stream results via WebSocket.

**Request Body:**
```json
{
  "test_path": "tests/cases/example_test.yaml",
  "headless": true,
  "variables": {}
}
```

**Response:**
```json
{
  "test_id": "unique-test-id",
  "status": "running",
  "message": "Test execution started"
}
```

**WebSocket Connection:**
- Connect to: `ws://localhost:8000/ws/{test_id}`
- Messages: `test_output`, `test_completed`, `test_failed`, `ping`

### Get Execution Status

**GET** `/api/tests/execution/{test_id}`

Get current status of a running test.

**Path Parameters:**
- `test_id`: Unique test execution ID

**Response:**
```json
{
  "test_id": "unique-test-id",
  "status": "running",
  "current_step": 3,
  "total_steps": 10,
  "percentage": 30,
  "output": ["Step 1 completed", "Step 2 completed"],
  "started": "2025-01-15T10:30:00Z"
}
```

---

## Test Suites

### List Test Suites

**GET** `/api/test-suites`

Get all test suites.

**Query Parameters:**
- `workspace` (optional): Filter by workspace

**Response:**
```json
{
  "suites": [
    {
      "id": "suite-uuid",
      "name": "My Test Suite",
      "description": "Suite description",
      "workspace": "My Workspace",
      "tests": [
        {
          "test_id": "tests/cases/test1.yaml",
          "order": 0
        }
      ],
      "created": "2025-01-15T10:00:00Z",
      "modified": "2025-01-15T10:00:00Z"
    }
  ],
  "total": 1
}
```

### Get Test Suite

**GET** `/api/test-suites/{suite_id}`

Get details of a specific test suite.

**Path Parameters:**
- `suite_id`: Suite UUID

**Response:** Same structure as suite object in List Test Suites

### Create Test Suite

**POST** `/api/test-suites`

Create a new test suite.

**Request Body:**
```json
{
  "name": "New Test Suite",
  "description": "Suite description",
  "workspace": "My Workspace",
  "tests": []
}
```

**Response:**
```json
{
  "id": "suite-uuid",
  "message": "Test suite created successfully"
}
```

### Update Test Suite

**PUT** `/api/test-suites/{suite_id}`

Update an existing test suite.

**Path Parameters:**
- `suite_id`: Suite UUID

**Request Body:** Same as Create Test Suite

**Response:**
```json
{
  "message": "Test suite updated successfully"
}
```

### Delete Test Suite

**DELETE** `/api/test-suites/{suite_id}`

Delete a test suite.

**Path Parameters:**
- `suite_id`: Suite UUID

**Response:**
```json
{
  "message": "Test suite deleted successfully"
}
```

### Execute Test Suite

**POST** `/api/test-suites/{suite_id}/execute`

Execute all tests in a suite.

**Path Parameters:**
- `suite_id`: Suite UUID

**Request Body:**
```json
{
  "test_ids": ["tests/cases/test1.yaml"],
  "max_tests": null,
  "headless": true
}
```

**Response:**
```json
{
  "suite_id": "suite-uuid",
  "status": "running",
  "message": "Test suite execution started"
}
```

---

## Variables

### List Environments

**GET** `/api/environments`

Get all environment variable sets.

**Response:**
```json
{
  "environments": [
    {
      "id": "env-uuid",
      "name": "Production",
      "description": "Production environment",
      "variables": {
        "api_url": "https://api.prod.com"
      },
      "is_active": true
    }
  ],
  "total": 1
}
```

### Get Environment

**GET** `/api/environments/{env_id}`

Get details of a specific environment.

**Path Parameters:**
- `env_id`: Environment UUID

**Response:** Environment object

### Create Environment

**POST** `/api/environments`

Create a new environment.

**Request Body:**
```json
{
  "name": "Staging",
  "description": "Staging environment",
  "variables": {
    "api_url": "https://api.staging.com"
  },
  "is_active": false
}
```

**Response:**
```json
{
  "id": "env-uuid",
  "message": "Environment created successfully"
}
```

### Update Environment

**PUT** `/api/environments/{env_id}`

Update an environment.

**Path Parameters:**
- `env_id`: Environment UUID

**Request Body:** Same as Create Environment

**Response:**
```json
{
  "message": "Environment updated successfully"
}
```

### Delete Environment

**DELETE** `/api/environments/{env_id}`

Delete an environment.

**Path Parameters:**
- `env_id`: Environment UUID

**Response:**
```json
{
  "message": "Environment deleted successfully"
}
```

### List Collections

**GET** `/api/collections`

Get all collection/workspace variable sets.

**Response:**
```json
{
  "collections": [
    {
      "id": "collection-uuid",
      "name": "My Workspace",
      "description": "Collection description",
      "variables": {
        "base_url": "https://example.com"
      }
    }
  ],
  "total": 1
}
```

### Get Collection

**GET** `/api/collections/{collection_id}`

Get details of a specific collection.

**Path Parameters:**
- `collection_id`: Collection UUID

**Response:** Collection object

### Create Collection

**POST** `/api/collections`

Create a new collection.

**Request Body:**
```json
{
  "name": "New Collection",
  "description": "Collection description",
  "variables": {
    "base_url": "https://example.com"
  }
}
```

**Response:**
```json
{
  "id": "collection-uuid",
  "message": "Collection created successfully"
}
```

### Update Collection

**PUT** `/api/collections/{collection_id}`

Update a collection.

**Path Parameters:**
- `collection_id`: Collection UUID

**Request Body:** Same as Create Collection

**Response:**
```json
{
  "message": "Collection updated successfully"
}
```

### Delete Collection

**DELETE** `/api/collections/{collection_id}`

Delete a collection.

**Path Parameters:**
- `collection_id`: Collection UUID

**Response:**
```json
{
  "message": "Collection deleted successfully"
}
```

---

## Actions

### List Actions

**GET** `/api/actions`

Get all available actions.

**Query Parameters:**
- `category` (optional): Filter by category (Browser, API, AWS, etc.)

**Response:**
```json
{
  "actions": [
    {
      "id": "browser.open",
      "category": "Browser",
      "label": "Open URL",
      "description": "Navigate to a URL",
      "icon": "🌐",
      "parameters": {
        "url": {
          "type": "string",
          "required": true,
          "description": "The URL to navigate to"
        }
      }
    }
  ],
  "total": 50
}
```

### Get Action Definition

**GET** `/api/actions/{action_id}`

Get detailed definition of a specific action.

**Path Parameters:**
- `action_id`: Action ID (e.g., `browser.open`)

**Response:** Action object with full parameter definitions

### Get Actions by Category

**GET** `/api/actions/category/{category}`

Get all actions in a specific category.

**Path Parameters:**
- `category`: Category name (Browser, API, AWS, etc.)

**Response:** Array of action objects

---

## Results & Reports

### List Test Results

**GET** `/api/results`

Get all test execution results.

**Query Parameters:**
- `page` (optional, default: 1): Page number
- `per_page` (optional, default: 10): Results per page
- `workspace` (optional): Filter by workspace

**Response:**
```json
{
  "results": [
    {
      "filename": "result_20250115_103000.json",
      "test_name": "Example Test",
      "status": "passed",
      "timestamp": "2025-01-15T10:30:00Z",
      "execution_time": 12.5,
      "build_id": "abc12345"
    }
  ],
  "total": 100,
  "page": 1,
  "per_page": 10,
  "total_pages": 10
}
```

### Get Test Result

**GET** `/api/results/{filename}`

Get detailed information about a specific test result.

**Path Parameters:**
- `filename`: Result JSON filename

**Response:**
```json
{
  "test_name": "Example Test",
  "test_path": "tests/cases/example_test.yaml",
  "status": "passed",
  "timestamp": "2025-01-15T10:30:00Z",
  "execution_time": 12.5,
  "build_id": "abc12345",
  "return_code": 0,
  "output": ["Step 1 completed", "Step 2 completed"],
  "tests": [...]
}
```

### Download Result

**GET** `/api/results/{filename}/download`

Download a result JSON file.

**Path Parameters:**
- `filename`: Result JSON filename

**Response:** File download

### Generate HTML Report

**POST** `/api/results/{filename}/report`

Generate an HTML report from a result JSON file.

**Path Parameters:**
- `filename`: Result JSON filename

**Response:**
```json
{
  "report_filename": "result_20250115_103000.html",
  "message": "Report generated successfully"
}
```

### Download HTML Report

**GET** `/api/results/{filename}/report/download`

Download a generated HTML report.

**Path Parameters:**
- `filename`: Result JSON filename (without .html extension)

**Response:** File download

---

## Dashboard & Metrics

### Get Dashboard Stats

**GET** `/api/dashboard/stats`

Get dashboard statistics summary.

**Response:**
```json
{
  "test_count": 50,
  "total_runs": 200,
  "passed": 180,
  "failed": 20,
  "pass_rate": 90.0,
  "today_runs": 10,
  "recent_runs": 50,
  "avg_execution_time": 12.5,
  "last_run": {
    "test_name": "Example Test",
    "status": "passed",
    "timestamp": "2025-01-15T10:30:00Z"
  },
  "running_tests": 2,
  "recent_results": [...],
  "hardware": {
    "cpu": {...},
    "memory": {...},
    "disk": {...}
  }
}
```

### Get Hardware Stats

**GET** `/api/dashboard/hardware`

Get system hardware statistics.

**Response:**
```json
{
  "cpu": {
    "usage_percent": 45.2,
    "cores": 8,
    "frequency": "2.4 GHz"
  },
  "memory": {
    "usage_percent": 62.5,
    "total_gb": 16,
    "used_gb": 10,
    "free_gb": 6
  },
  "disk": {
    "usage_percent": 35.8,
    "total_gb": 500,
    "used_gb": 179,
    "free_gb": 321
  }
}
```

### Get Comprehensive Metrics

**GET** `/api/metrics/comprehensive`

Get detailed metrics for the metrics dashboard page.

**Response:**
```json
{
  "test_health": {
    "most_failing_tests": [...],
    "flaky_tests": [...],
    "stale_tests": [...],
    "tests_without_steps": [...]
  },
  "suite_statistics": {
    "total_suites": 5,
    "suites_with_tests": 4,
    "total_tests_in_suites": 20,
    "most_active_suites": [...]
  },
  "execution_trends": {
    "time_trends": [...],
    "failure_rate_trends": [...],
    "peak_hours": [...],
    "slowest_tests": [...]
  },
  "test_coverage": {
    "by_workspace": [...],
    "by_action_type": [...],
    "complexity": {...},
    "tag_distribution": [...]
  },
  "quick_insights": {
    "execution_velocity": {...},
    "success_streak": 5,
    "recent_failures": [...]
  },
  "resource_storage": {
    "result_files": {...},
    "html_reports": {...},
    "old_results_count": 10
  }
}
```

---

## Workspaces

### List Workspaces

**GET** `/api/workspaces`

Get all workspaces/folders.

**Response:**
```json
{
  "workspaces": [
    {
      "path": "tests/cases/MyWorkspace",
      "name": "MyWorkspace",
      "test_count": 10
    }
  ],
  "total": 1
}
```

### Create Workspace

**POST** `/api/workspaces`

Create a new workspace/folder.

**Request Body:**
```json
{
  "name": "NewWorkspace"
}
```

**Response:**
```json
{
  "path": "tests/cases/NewWorkspace",
  "message": "Workspace created successfully"
}
```

---

## Documentation

### Get Documentation

**GET** `/api/docs/{doc_name}`

Get rendered documentation file.

**Path Parameters:**
- `doc_name`: Documentation file name (e.g., `README`, `TEST_BUILDER`)

**Response:** HTML rendered markdown

**Available Documents:**
- `README` - Main README
- `TEST_BUILDER` - Test Builder guide
- `actions` - Actions reference
- `syntax` - Syntax guide
- `SYNTAX_CHEATSHEET` - Quick syntax reference
- And all other files in `docs/` folder

---

## Settings

### Get Settings

**GET** `/api/settings`

Get application settings.

**Response:**
```json
{
  "teams": {
    "enabled": true,
    "webhook_url": "https://...",
    "notify_on_success": true,
    "notify_on_failure": true,
    "attach_report": false
  }
}
```

### Update Settings

**PUT** `/api/settings`

Update application settings.

**Request Body:**
```json
{
  "teams": {
    "enabled": true,
    "webhook_url": "https://...",
    "notify_on_success": true,
    "notify_on_failure": true,
    "attach_report": true
  }
}
```

**Response:**
```json
{
  "message": "Settings updated successfully"
}
```

### Test Teams Connection

**POST** `/api/settings/teams/test`

Test Microsoft Teams webhook connection.

**Request Body:**
```json
{
  "webhook_url": "https://..."
}
```

**Response:**
```json
{
  "success": true,
  "message": "Connection successful"
}
```

---

## WebSocket API

### Test Execution WebSocket

**WebSocket** `/ws/{test_id}`

Real-time updates for test execution.

**Path Parameters:**
- `test_id`: Unique test execution ID

**Message Types:**

1. **test_output**
```json
{
  "type": "test_output",
  "line": "Step 1: Opening browser..."
}
```

2. **test_completed**
```json
{
  "type": "test_completed",
  "test_id": "unique-test-id",
  "status": "passed",
  "execution_time": 12.5
}
```

3. **test_failed**
```json
{
  "type": "test_failed",
  "test_id": "unique-test-id",
  "error": "Error message",
  "execution_time": 5.2
}
```

4. **ping**
```json
{
  "type": "ping"
}
```

**Client should respond with `pong` to keep connection alive.**

---

## Error Responses

All endpoints may return error responses in the following format:

```json
{
  "detail": "Error message description"
}
```

**Common HTTP Status Codes:**
- `200` - Success
- `201` - Created
- `400` - Bad Request
- `404` - Not Found
- `422` - Validation Error
- `500` - Internal Server Error

---

## Authentication

Currently, the Test Builder API does not require authentication. This is suitable for local development and internal use.

**Future:** Authentication may be added for production deployments.

---

## Rate Limiting

No rate limiting is currently implemented. Use responsibly.

---

## CORS

CORS is enabled for all origins by default. For production, restrict to specific origins.

---

## Examples

### Create and Execute a Test

```bash
# Create test
curl -X POST http://localhost:8000/api/tests \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Test",
    "steps": [
      {
        "action": "browser.open",
        "parameters": {
          "url": "https://example.com"
        }
      }
    ]
  }'

# Execute test
curl -X POST http://localhost:8000/api/tests/execute \
  -H "Content-Type: application/json" \
  -d '{
    "test_path": "tests/cases/my_test.yaml",
    "headless": true
  }'
```

### Get Metrics

```bash
curl http://localhost:8000/api/metrics/comprehensive
```

### Create Test Suite

```bash
curl -X POST http://localhost:8000/api/test-suites \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Smoke Tests",
    "tests": [
      {
        "test_id": "tests/cases/test1.yaml",
        "order": 0
      }
    ]
  }'
```

---

## Interactive Documentation

When the Test Builder server is running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

These provide interactive API documentation with the ability to test endpoints directly from the browser.

---

## Support

For issues, questions, or contributions:

- **GitHub Issues**: Report bugs and request features
- **Documentation**: See `/docs` folder for detailed guides
- **API Docs**: Use interactive Swagger UI at `/docs`
