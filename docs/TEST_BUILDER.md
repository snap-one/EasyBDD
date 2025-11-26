# Test Builder Web Application

Modern, professional web interface for visual test creation and management with the Easy BDD Framework.

## 🌟 Features

### Visual Test Creation
- **Drag & Drop Interface** - Intuitive step management with automatic numbering
- **Action Library** - Browse 50+ available actions categorized by type
- **Form-Based Configuration** - Dynamic forms with validation for each action
- **Real-Time Validation** - Instant feedback on test structure and parameters
- **Template System** - Start from pre-built test templates or action templates
- **Required Field Validation** - Prevents adding steps until all required fields are valid

### Test Management
- **CRUD Operations** - Create, Read, Update, Delete tests from web UI
- **Test Library** - Browse all tests with search and filtering
- **Copy/Duplicate Tests** - Quickly duplicate existing tests
- **Copy/Duplicate Steps** - Duplicate steps within or across tests
- **Version Control Ready** - Tests saved as YAML files in your repository
- **Tag Organization** - Organize tests with custom tags
- **Workspace Organization** - Organize tests by workspace/folder with filtering

### Test Suites
- **Create Test Suites** - Group multiple tests together
- **Add/Remove Tests** - Manage tests in suites
- **Enable/Disable Tests** - Control which tests run in a suite
- **Reorder Execution** - Drag and drop to change execution order
- **Execution History** - View past suite executions
- **One-Click Execution** - Run entire suite with one click

### Execution & Monitoring
- **One-Click Execution** - Run tests directly from the web interface
- **Real-Time Output** - Stream test execution logs via WebSocket
- **CLI Integration** - Seamlessly integrates with existing CLI framework
- **Enhanced Result Tracking** - Split-view results interface with compact cards, test name/build number extraction, and interactive preview panel
- **Test Report Pagination** - Paginated test reports (10 per page) for better navigation
- **Report Generation** - Generate beautiful HTML reports with simple and debug logs

### Developer Experience
- **Zero Programming Required** - Build tests without writing code
- **Professional UI** - Modern, responsive design with dark mode support
- **Auto-Complete** - Smart suggestions for parameters and values
- **Help Text** - Built-in documentation for every action and parameter
- **Action Templates** - Pre-filled templates for all actions with required/optional parameters
- **Improved Variable Management** - Enhanced variable creation with no duplicate empty variables, no prefilled placeholders
- **Enhanced Navigation** - Reorganized navigation panel with Resources section above Workspaces

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd frontend
pip install -r requirements_builder.txt
```

### 2. Start the Test Builder

```bash
# From frontend directory
python start_builder.py

# Or from project root
python frontend/start_builder.py
```

### 3. Open in Browser

Navigate to: **http://localhost:8000**

## 📖 User Guide

### Creating Your First Test

1. **Click "New Test"** in the sidebar
2. **Fill in Test Information**
   - Name: Give your test a descriptive name
   - Description: Explain what the test does
   - Tags: Add tags for organization (e.g., "browser", "smoke", "critical")
   - Workspace: Select or create a workspace (optional)

3. **Add Test Variables** (Optional)
   - Click "Add Variable" to add key-value pairs
   - Variables can be used in steps with `${variable_name}` syntax
   - Variables are automatically synced to JSON format

4. **Add Test Steps**
   - Click "Add Step" button
   - Select an action from the action library
   - Fill in the parameters using the form
   - **Required fields** are marked with red asterisk (*)
   - The "Add Step" button is disabled until all required fields are valid
   - Click "Add Step" to add it to your test

5. **Edit Steps**
   - Click the edit icon on any step
   - Modify parameters in the form
   - Click "Update Step" to save changes
   - Confirmation dialog appears when deleting steps

6. **Copy/Duplicate Steps**
   - Click the copy icon on any step
   - The step is duplicated immediately after the original

7. **Use Tests as Reusable Steps**
   - When adding a step, select "Test" category
   - Choose "Run Test" action
   - Select an existing test file from the dropdown
   - Configure parameters to pass to the test
   - Specify variables to extract from the test execution
   - The selected test will run as a step in your current test
   - This enables modular test composition and code reuse

7. **Reorder Steps** (if needed)
   - Use arrow buttons to move steps up/down
   - Steps are automatically renumbered

8. **Save Test**
   - Click "Save" button
   - Test is saved as YAML file in `tests/cases/`

9. **Run Test**
   - Click "Run Test" button
   - Monitor execution in the console output panel
   - View results in the "Test Results" tab

### Using Action Templates

Action templates provide pre-filled parameters for all actions:

1. **Go to "Actions Library"** in the sidebar
2. **Browse Actions** by category
3. **Click an Action** to see:
   - Action description
   - Required parameters (marked with *)
   - Optional parameters
   - Parameter help text
4. **Click "Add Step"** button
5. **Select Tests** - Choose which tests to add this step to (multiple selection)
6. **Fill in Parameters** - Templates pre-fill with placeholders
7. **Add Step** - Step is added to all selected tests

### Adding Steps to Multiple Tests

1. **Go to "Actions Library"**
2. **Click an Action**
3. **Click "Add Step"**
4. **Select Tests** - Use the test selection modal:
   - Search for tests by name
   - Filter by workspace
   - Select multiple tests with checkboxes
   - Counter shows number of selected tests
5. **Click "Continue"** - Opens step editor
6. **Fill in Parameters**
7. **Click "Add Step"** - Step is added to all selected tests

### Test Suites

Test suites allow you to group and execute multiple tests together.

#### Creating a Test Suite

1. **Click "Test Suites"** in the sidebar
2. **Click "Create Suite"** button
3. **Fill in Suite Information**:
   - Name: Descriptive name for the suite
   - Description: What this suite tests
   - Workspace: Select workspace (optional)
4. **Add Tests**:
   - Click "Add Tests" button
   - Select tests from the list
   - Tests are added to the suite
5. **Configure Tests**:
   - Enable/Disable: Toggle which tests run
   - Reorder: Drag and drop to change execution order
6. **Save Suite**

#### Executing a Test Suite

1. **Go to "Test Suites"**
2. **Click on a Suite** to view details
3. **Click "Execute Suite"** button
4. **Monitor Execution**:
   - View progress in real-time
   - See which tests are running
   - View results as they complete

#### Managing Test Suites

- **Edit Suite**: Click edit icon to modify suite configuration
- **Delete Suite**: Click delete icon (with confirmation)
- **View Execution History**: See past suite executions in the suite detail view

### Variable Management

Variables can be used throughout your test with `${variable_name}` syntax.

#### Adding Variables

1. **In Test Builder**, scroll to "Variables" section
2. **Click "Add Variable"** button
3. **Enter Key and Value**:
   - Key: Variable name (e.g., `base_url`)
   - Value: Variable value (e.g., `https://api.example.com`)
4. **Variables are automatically synced** to JSON format

#### Using Variables in Steps

Variables can be used in any parameter field:

```yaml
# In variables section:
base_url: "https://api.example.com"
username: "testuser"

# In step parameters:
url: "${base_url}/login"
value: "${username}"
```

#### Nested Variables

Variables can contain other variables:

```yaml
variables:
  device_ip: "192.168.1.100"
  api_base_url: "http://${device_ip}:8080"

steps:
  - api.get:
      url: "${api_base_url}/api/v1/status"
```

### OvrC API Integration

The Test Builder includes full support for OvrC WebSocket and HTTP API.

#### OvrC WebSocket Actions

**Connect to OvrC:**
```yaml
- ovrc.connect:
    server_url: "ws://192.168.1.100:8080"
    device_id: "4B:00:00:00:00:15"
    auth_type: "bearer"  # or "basic", "api_key", "custom"
    auth_token: "${ovrc_token}"  # for bearer auth
```

**Send JSON-RPC Command:**
```yaml
- ovrc.send:
    method: "dxGetAbout"
    params:
      deviceId: "${device_id}"
    store_as: "device_info"
    timeout: 10
```

**Common OvrC Methods:**
- `dxGetAbout` - Get device information
- `dsStartDeviceUpdates` - Start receiving device updates
- `dsStopDeviceUpdates` - Stop device updates
- `dxGetNetworkSettings` - Get network configuration
- `dxSetNetworkSettings` - Set network configuration
- And many more (see autocomplete suggestions)

**Automatic Connection Management:**
- OvrC actions automatically connect if not already connected
- Connection is automatically closed after test execution
- No need to manually manage connections

#### OvrC HTTP API Actions

**Generic HTTP Request:**
```yaml
- ovrc.http.request:
    method: "GET"  # or POST, PUT, PATCH, DELETE
    endpoint: "/api/v1/devices/${device_id}"
    query_params:
      status: "online"
    store_as: "device_data"
```

**Automatic Authentication:**
- Authentication is handled automatically based on connection settings
- Supports Bearer tokens, Basic auth, API keys, and custom headers
- Re-authenticates automatically on 401 errors

**Using OvrC Actions in Test Builder:**

1. **Add Step** → Select "OvrC API" category
2. **Choose Action**:
   - `ovrc.connect` - Connect to OvrC
   - `ovrc.send` - Send JSON-RPC command (with autocomplete suggestions)
   - `ovrc.http.request` - Make HTTP request
   - `ovrc.http.get` - GET request
   - `ovrc.http.post` - POST request
   - And more...
3. **Fill Parameters**:
   - Required fields marked with *
   - Use autocomplete for method names
   - Use key-value editor for params/query_params
4. **Add Step**

### Report Generation

Generate beautiful HTML reports from test results.

#### Viewing Test Results

The Test Results view features a modern split-view interface for efficient result browsing:

1. **Go to "Test Results"** tab (or click "View Results" after test execution)
2. **Browse Results** (Left Panel):
   - Filter by workspace using the dropdown
   - Results are displayed in compact cards showing:
     - Test name (extracted from path, not full path)
     - Build number (extracted from filename)
     - Status badge (PASSED, FAILED, etc.)
     - Short date format (e.g., "2h ago", "3d ago")
   - Results are grouped by workspace
   - Click any result card to view details in the preview panel
3. **View Details** (Right Panel):
   - Interactive preview panel shows full execution details
   - Execution information (started, finished, return code, output lines)
   - Command used for execution
   - Full execution output with syntax highlighting
   - Action buttons: Generate Report, Download, Delete
4. **Pagination**:
   - Navigate through multiple pages of results
   - Shows current page and total pages

#### Test Reports Pagination

When viewing test reports for a specific test:
- Reports are paginated (10 per page)
- Navigate using Previous/Next buttons
- Shows "Showing X to Y of Z reports" information
- Only displays pagination controls when there are more than 10 reports

#### Generating HTML Reports

1. **In Test Results**, click on a result
2. **Click "Generate Report"** button (next to Download)
3. **Report is Generated**:
   - Beautiful HTML format
   - Simple log tab (minimal output)
   - Debug log tab (full API request/response bodies, telnet feedback)
   - Step-by-step execution view
   - Professional styling matching dark theme

#### Report Features

- **Simple Log**: Shows only step names and minimal information
- **Debug Log**: Shows everything including:
  - Full API request/response bodies
  - Headers
  - Telnet feedback
  - Detailed error messages
- **Step View**: Visual representation of test execution
- **Download**: Download HTML report file

### Action Categories

#### 🌐 Browser Actions (30+)
- **Navigation**: Open URL, navigate, back, forward, refresh
- **Interaction**: Click, fill, upload, select, check, hover, drag
- **Keyboard**: Press keys, type text
- **Waiting**: Wait for time, wait for elements
- **Capture**: Screenshots, get text, get attributes
- **Advanced**: Execute JavaScript, manage cookies, set viewport

#### 🔍 API Actions
- **HTTP Methods**: GET, POST, PUT, PATCH, DELETE
- **Authentication**: Bearer tokens, basic auth, API keys
- **Validation**: Status codes, response body, headers
- **Storage**: Store responses in variables

#### ☁️ AWS S3 Actions
- **File Operations**: List, download, upload, delete
- **Version Management**: Get latest firmware with regex
- **CloudFront**: Generate CDN URLs automatically

#### 📡 OvrC API Actions
- **WebSocket**: Connect, disconnect, send JSON-RPC commands
- **HTTP API**: GET, POST, PUT, PATCH, DELETE with auto-auth
- **Device Control**: Get device info, network settings, time settings
- **Flexible Commands**: Support for any OvrC command

#### ✅ Test & Assertions
- **Assertions**: Expression evaluation, schema validation
- **Response Checks**: API response validation
- **Soft Assertions**: Continue on failure, check all at end

### Parameter Types

The form builder supports multiple input types:

| Type | Description | Example |
|------|-------------|---------|
| **Text** | Single line text input | `#username` |
| **Number** | Numeric input | `30000` |
| **Boolean** | Checkbox | `true/false` |
| **Select** | Dropdown menu | `chromium`, `firefox`, `webkit` |
| **Textarea** | Multi-line text | JavaScript code |
| **JSON** | JSON object/array | `{"key": "value"}` |
| **Key-Value** | Key-value pairs editor | `{"key": "value"}` |
| **File** | File path | `/path/to/file.txt` |

### Key-Value Editor

The key-value editor makes it easy to manage dictionary-like parameters:

1. **Click "Add Key-Value"** button
2. **Enter Key and Value**
3. **Add More Pairs** as needed
4. **Remove Pairs** with the X button
5. **JSON is Auto-Synced** - Changes are automatically reflected in the JSON field

Used for:
- API request bodies
- Query parameters
- Headers
- OvrC command parameters
- Test variables

### Templates

Pre-built templates for common scenarios:

1. **Test Templates** - Full test scenarios:
   - Browser Login Test
   - API CRUD Operations
   - AWS Firmware Test
   - OvrC Device Test

2. **Action Templates** - Pre-filled action templates:
   - All 50+ actions with required/optional parameters
   - Pre-filled with placeholders or defaults
   - Organized by category

To use a template:
1. Go to "Templates" in sidebar
2. Browse test templates or action templates
3. Click on a template
4. Customize as needed
5. Save with new name

## 🏗️ Architecture

### Backend (FastAPI)

**File**: `frontend/test_builder_app.py`

#### Key Endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tests` | GET | List all tests |
| `/api/tests/{id}` | GET | Get specific test |
| `/api/tests` | POST | Create new test |
| `/api/tests/{id}` | PUT | Update test |
| `/api/tests/{id}` | DELETE | Delete test |
| `/api/tests/{id}/copy` | POST | Copy/duplicate test |
| `/api/actions` | GET | Get all actions |
| `/api/actions/{id}` | GET | Get action details |
| `/api/action-templates` | GET | Get action templates |
| `/api/tests/validate` | POST | Validate test |
| `/api/tests/execute` | POST | Execute test |
| `/api/templates` | GET | Get test templates |
| `/api/test-suites` | GET | List all test suites |
| `/api/test-suites` | POST | Create test suite |
| `/api/test-suites/{id}` | GET | Get suite details |
| `/api/test-suites/{id}` | PUT | Update suite |
| `/api/test-suites/{id}` | DELETE | Delete suite |
| `/api/test-suites/{id}/execute` | POST | Execute suite |
| `/api/results` | GET | List test results |
| `/api/results/{id}` | GET | Get result details |
| `/api/results/{id}/report` | GET | Generate HTML report |
| `/api/folders` | GET | List workspaces/folders |
| `/ws` | WebSocket | Real-time updates |

#### Action Definitions:

**File**: `frontend/action_definitions.py`

Comprehensive catalog of all 50+ actions with:
- Parameter types and validation
- Required vs optional fields
- Help text and placeholders
- Form field configuration
- Autocomplete suggestions

### Frontend (Vue.js 3)

**File**: `frontend/static/test_builder.html`

Single-page application with:
- **Vue 3 Composition API** - Reactive state management
- **Axios** - HTTP client for API calls
- **WebSocket** - Real-time execution monitoring
- **Font Awesome** - Professional icons
- **Custom CSS** - Modern, responsive design with dark mode

#### Views:

1. **Dashboard** - Overview with key metrics and quick actions
2. **Test List** - Browse and manage all tests
3. **Test Builder** - Visual test creation interface
4. **Actions Library** - Browse all available actions
5. **Templates** - Pre-built test templates and action templates
6. **Test Suites** - Create and manage test suites
7. **Test Results** - View test execution results

#### Components:

- **Test Step Card** - Display step with parameters
- **Action Picker** - Select action from library
- **Step Editor Modal** - Form-based parameter input with validation
- **Test Info Form** - Name, description, tags, workspace
- **Variable Editor** - Key-value editor for variables
- **Test Suite Card** - Display suite information
- **Result Card** - Display test result summary

## 🎨 Customization

### Adding Custom Actions

1. **Add to Action Definitions** (`action_definitions.py`):

```python
ACTION_DEFINITIONS["custom.my_action"] = {
    "category": "Custom",
    "label": "My Custom Action",
    "description": "Does something custom",
    "icon": "🎯",
    "parameters": {
        "param1": {
            "type": "text",
            "required": True,
            "label": "Parameter 1",
            "placeholder": "Enter value",
            "help": "What this parameter does"
        }
    }
}
```

2. **Implement Handler** in your service

3. **Restart Server** - Changes auto-reload with `--reload` flag

### Styling

Modify CSS variables in `test_builder.html`:

```css
:root {
    --primary: #2563eb;        /* Primary color */
    --success: #10b981;        /* Success color */
    --danger: #ef4444;         /* Danger color */
    --bg-main: #f8fafc;        /* Main background */
    --bg-card: #ffffff;        /* Card background */
    /* ... */
}
```

## 🔧 Configuration

### Port Configuration

Default port is **8000**. To change:

```bash
uvicorn test_builder_app:app --host 0.0.0.0 --port 8080
```

### Test Directory

Default: `../tests/cases`

Modify in `test_builder_app.py`:

```python
tests_directory = Path("../tests/cases")
```

### CORS Configuration

Allow specific origins by modifying:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 📊 API Documentation

Interactive API documentation available at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🐛 Troubleshooting

### Port Already in Use

```bash
# Kill process using port 8000
lsof -ti:8000 | xargs kill -9

# Or use different port
uvicorn test_builder_app:app --port 8001
```

### Tests Not Loading

1. Check test directory exists: `tests/cases/`
2. Verify YAML files are valid
3. Check console for errors: Browser DevTools → Console

### Action Not Showing

1. Verify action is in `action_definitions.py`
2. Check category is defined
3. Restart server with `--reload`

### Step Editor Not Opening

1. Check browser console for errors
2. Verify action ID exists in definitions
3. Check network tab for failed API calls

### Required Fields Not Validating

1. Ensure all required fields are filled
2. Check field types match expected format
3. For key-value fields, ensure valid JSON object
4. For select fields, ensure value is in options list

### Variables Not Substituting

1. Check variable syntax: `${variable_name}` (with curly braces)
2. Ensure variable is defined in test variables section
3. Check for typos in variable names
4. For nested variables, ensure parent variable is defined first

## 🚀 Advanced Usage

### WebSocket Real-Time Updates

Connect to `/ws` endpoint for live updates:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === 'test_output') {
        console.log(data.line);
    } else if (data.type === 'test_completed') {
        console.log('Test finished:', data.status);
    }
};
```

### Batch Operations

Create multiple tests programmatically:

```python
import requests

tests = [
    {"name": "Test 1", "steps": [...]},
    {"name": "Test 2", "steps": [...]},
]

for test in tests:
    requests.post("http://localhost:8000/api/tests", json=test)
```

### CI/CD Integration

Run test builder in CI pipeline:

```yaml
# .github/workflows/tests.yml
- name: Start Test Builder
  run: |
    cd frontend
    python start_builder.py &
    sleep 5

- name: Create Test via API
  run: |
    curl -X POST http://localhost:8000/api/tests \
      -H "Content-Type: application/json" \
      -d @test_definition.json
```

## 🎯 Best Practices

1. **Use Descriptive Names** - Make test names clear and searchable
2. **Add Tags** - Organize tests with consistent tagging
3. **Include Descriptions** - Document what each test does
4. **Step Descriptions** - Add notes to complex steps
5. **Use Variables** - Don't hardcode URLs and credentials
6. **Validate First** - Always validate before running
7. **Template Starting Points** - Use templates for consistency
8. **Version Control** - Commit test files to git
9. **Workspace Organization** - Use workspaces to group related tests
10. **Test Suites** - Group related tests into suites for easier execution

## 🤝 Contributing

To add new features to Test Builder:

1. **Backend Changes**: Edit `test_builder_app.py`
2. **Action Definitions**: Edit `action_definitions.py`
3. **Frontend Changes**: Edit `static/test_builder.html`
4. **Test Changes**: Add test files to `tests/cases/`
5. **Documentation**: Update this file

## 📄 License

Same as main Easy BDD Framework project.

## 🆘 Support

- **Issues**: GitHub Issues
- **Documentation**: `/docs` folder
- **API Docs**: http://localhost:8000/docs
- **Syntax Reference**: [SYNTAX_CHEATSHEET.md](SYNTAX_CHEATSHEET.md)
- **Main README**: [../README.md](../README.md)
