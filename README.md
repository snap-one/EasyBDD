# Easy BDD Testing Framework

A powerful, user-friendly YAML-based BDD testing framework that supports multiple protocols including browser automation, REST APIs, WebSocket, AWS S3, Serial, and Android. **No programming knowledge required.**

## ✨ What's New

### 🎨 **Test Builder Web Application** (Latest!)
**Zero-code visual test creation with modern web UI!**

- **🎯 Visual Test Builder** - Drag & drop interface, no programming needed
- **📚 50+ Actions Library** - Browse all available actions in categorized library
- **📝 Form-Based Configuration** - Dynamic forms with validation for each action
- **⚡ Real-Time Execution** - Run tests from web UI with live output streaming
- **📋 Template System** - Start from pre-built test templates or action templates
- **📦 Test Suites** - Group and execute multiple tests with specific configurations
- **🔍 Test Management** - Create, edit, delete, copy tests in beautiful UI
- **📊 Report Generation** - Generate beautiful HTML reports with simple and debug logs
- **🔌 OvrC API Integration** - Full support for OvrC WebSocket and HTTP API
- **✅ Required Field Validation** - Prevents adding steps until all required fields are valid
- **🔑 Variable Management** - Postman-like environments, collections, and suite variables with scoped variable resolution
- **📱 Workspace Organization** - Organize tests by workspace/folder with filtering
- **🔄 Step Copy/Duplicate** - Quickly duplicate test steps
- **📈 Test Results Dashboard** - Split-view results interface with compact cards, test name/build number extraction, and interactive preview panel
- **📄 Test Report Pagination** - Paginated test reports (10 per page) for better navigation
- **♻️ Reusable Test Steps** - Use any test as a step in other tests with `test.run` action for modular test composition
- **🗑️ Safe Deletions** - Confirmation dialogs for deleting variables and steps
- **📊 Metrics & Analytics Dashboard** - Comprehensive metrics page with test health, execution trends, coverage analysis, and resource insights
- **📅 Time Period Filtering** - Filter metrics by 7 days, 2 weeks, 3 weeks, 1 month, or 1 quarter
- **🤖 AI Assistant** - Persistent AI chat assistant with workspace/directory context awareness and **automatic test creation**
- **♻️ Test Rerun** - Rerun tests directly from results pages
- **✏️ In-Suite Test Editing** - Edit tests during suite creation/editing with context preservation
- **🗺️ Routing Support** - Proper URL routing with page refresh support and deep linking (all pages have unique routes)
- **🎯 Test Queue Management UI** - Comprehensive web interface for managing test queues, continuous execution, retries, and health monitoring
- **🚨 Error Pages** - Custom error pages for 404, 500, 503, and other HTTP errors
- **📈 System Resource Auto-Detection** - Automatic CPU, memory, disk, and network monitoring
- **🎬 Demo Test Suite** - Ready-to-run demo tests for UI and API testing

**[📖 Full Test Builder Guide](docs/TEST_BUILDER.md)** | **[🆕 New Features Guide](docs/NEW_FEATURES.md)** | **[🚀 Server Deployment Guide](docs/SERVER_DEPLOYMENT.md)** | **Quick Start**: `python frontend/start_builder.py` → http://localhost:8000

### 🆕 Recent Features

- **Metrics & Analytics Dashboard** - Comprehensive metrics page with test health monitoring (failing tests, flaky tests, stale tests), execution trends (time trends, failure rates, peak hours), test coverage analysis (by workspace, action type, complexity), quick insights (velocity, streaks, recent failures), and resource storage tracking
- **Time Period Filtering** - Filter metrics by 7 days, 2 weeks, 3 weeks, 1 month, or 1 quarter for trend analysis
- **AI Assistant** - Persistent AI chat assistant that maintains context across pages, including workspace, directory, current test, and view information. **Can automatically create tests from natural language requests!**
- **Test Rerun** - Rerun tests directly from results pages with one click
- **In-Suite Test Editing** - Edit tests while creating/editing suites without losing context
- **Routing & Page Refresh** - Proper URL routing with state persistence, allowing page refreshes without errors. All pages have unique routes (e.g., `/queue`, `/metrics`, `/settings`)
- **Test Queue Management UI** - Full-featured web interface for managing test execution queues with real-time status updates, continuous execution toggle, retry configuration, and health monitoring
- **Error Pages** - Custom error pages for common HTTP errors (404, 500, 503, etc.) with user-friendly messages
- **System Resource Auto-Detection** - Automatic extraction and monitoring of CPU, memory, disk, and network resources from device updates
- **Demo Test Suite** - Pre-built demo tests for UI and API testing using public endpoints (no setup required)
- **Enhanced Test Results View** - Split-view interface with compact result cards showing test name and build number (instead of full paths), interactive preview panel for detailed execution logs
- **Test Report Pagination** - Paginated test reports showing 10 reports per page with navigation controls
- **Reusable Test Steps** - Use any test as a reusable step in other tests with `test.run` action, enabling modular test composition and maintainability
- **Improved Variable Management** - Enhanced variable creation with no duplicate empty variables, no prefilled placeholders, and confirmation dialogs for deletions
- **Confirmation Dialogs** - Added confirmation prompts when deleting variables and test steps to prevent accidental deletions
- **Navigation Improvements** - Reorganized navigation panel with Resources section above Workspaces for better accessibility
- **Environment & Collection Variables** - Postman-like variable management with environments, collections/workspaces, and suite variables. Use `${env.variable_name}`, `${collection.variable_name}`, or `${suite.variable_name}` in your tests
- **Test Suites** - Create test suites, add/remove tests, enable/disable tests, reorder execution, view execution history
- **OvrC API Actions** - Full support for OvrC WebSocket (JSON-RPC) and HTTP API with automatic authentication
- **Action Templates** - Pre-filled action templates with all required and optional parameters
- **HTML Report Generation** - Professional HTML reports with simple and debug log tabs
- **Variable Key-Value Editor** - Easy-to-use interface for managing test variables
- **Automatic OvrC Connection Management** - Auto-connect/disconnect for OvrC actions
- **Test Result Management** - View, download, and generate HTML reports for test results
- **Workspace Filtering** - Filter tests and results by workspace/folder
- **Step Validation** - Real-time validation of required fields before adding steps

### Framework Enhancements

- 🔁 **Retry Logic** - Configurable retry with exponential backoff for flaky tests
- 📊 **Enhanced Data-Driven** - CSV, JSON, Excel file support for test data
- 🎯 **Code Quality Tools** - Pre-commit hooks, Makefile commands, contributor guide
- ⚡ **Performance Boost** - 30-100% faster AWS S3 operations with connection pooling
- 🚀 **Optimized Regex** - 20% faster version extraction with pattern caching
- 🔒 **Security Enhancements** - Safe eval, password masking, test validation
- ✅ **Test Validation** - Validate tests before running with `validate` command
- 🔐 **Environment Variables** - Secure credential management with `.env` support
- ✨ **Dot Notation Actions** - New `service.action` syntax (e.g., `browser.click`, `aws.get_latest`)
- ✅ **Conditional Steps** - If/then/else logic for dynamic test flows
- ✅ **AWS S3 Integration** - Firmware management, version extraction, CloudFront URLs
- ✅ **Iframe Support** - File uploads and clicks inside iframes (`iframe >> selector` syntax)
- ✅ **File Chooser API** - Handle hidden file inputs automatically
- ✅ **Soft Assertions** - Continue tests on failures, collect all issues
- ✅ **Custom Assertions** - Powerful expression evaluation with Python
- ✅ **Automatic Time Tracking** - Calculate time savings automatically
- ✅ **Datalake Integration** - Advanced logging, metrics, Teams notifications
- ✅ **Playwright Recorder Support** - Convert Chrome Recorder output to tests

## 🚀 Quick Start

> **New to Easy BDD?** Check out the [Quick Start Guide](QUICK_START.md) for a 5-minute setup!

### First-Time Setup

1. **Clone and Install**
```bash
git clone <repository-url>
cd easy_bdd
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install --upgrade pip  # Required for pyproject.toml editable installs
pip install -e .
playwright install chromium  # Or: firefox, webkit
```

2. **Install Test Builder Dependencies** (Optional but Recommended)
```bash
cd frontend
pip install -r requirements_builder.txt
cd ..
```

3. **Configure AWS (Optional)**
```bash
# If using AWS features, configure AWS CLI
aws configure
# Or set environment variables:
export AWS_ACCESS_KEY_ID="your-key"  # pragma: allowlist secret
export AWS_SECRET_ACCESS_KEY="your-secret"  # pragma: allowlist secret
export AWS_DEFAULT_REGION="us-east-1"
```

4. **Verify Installation**
```bash
python -m easy_bdd --help
```

### Start the Test Builder (Recommended)

```bash
# Start the web application
python frontend/start_builder.py

# Open in browser: http://localhost:8000
```

The Test Builder provides a visual interface for creating and managing tests without writing YAML manually.

### Your First Test

#### Option 1: Using Test Builder (Easiest)

1. Start the Test Builder: `python frontend/start_builder.py`
2. Open http://localhost:8000 in your browser
3. Click "New Test" in the sidebar
4. Fill in test information (name, description, tags)
5. Click "Add Step" and select an action from the library
6. Fill in the parameters using the form
7. Click "Save" to save your test
8. Click "Run Test" to execute it

**[📖 Complete Test Builder Guide](docs/TEST_BUILDER.md)**

#### Option 2: Manual YAML Creation

Create `tests/cases/hello_world.yaml`:
```yaml
name: "My First Test"
description: "Login to application"
variables:
  username: "testuser"
  password: "testpass"  # pragma: allowlist secret
steps:
  - browser.open:
      url: "https://example.com"

  - browser.fill:
      field: "#username"
      value: "${username}"

  - browser.fill:
      field: "#password"
      value: "${password}"

  - browser.click:
      button: "Sign In"

  - test.assert:
      expression: "'Welcome' in page_content"
      message: "Expected welcome message not found"
```

Run it:
```bash
# Run with visible browser
python -m easy_bdd run tests/cases/hello_world.yaml --headed

# Run all tests
python -m easy_bdd run tests/cases/

# Run with specific tags
python -m easy_bdd run --tags demo
```

## 📚 Documentation

Comprehensive guides available in the `/docs` folder:

### 🚀 Quick Reference
- **[📋 Complete Syntax Cheat Sheet](docs/SYNTAX_CHEATSHEET.md)** - ⭐ ALL actions, options, and examples in one place!
- **[🎨 Test Builder Guide](docs/TEST_BUILDER.md)** - Complete guide to the web application
- **[YAML Syntax Reference](docs/syntax.md)** - Test file structure and variable syntax
- **[Action Reference](docs/actions.md)** - Detailed action documentation
- **[Dot Notation Actions](docs/dot-notation-actions.md)** - New `service.action` syntax

### 📖 Guides & Tutorials
- **[Getting Started Guide](docs/setup.md)** - Installation and configuration
- **[Examples](docs/examples.md)** - Real-world test examples
- **[Conditional Steps](docs/conditional-steps.md)** - If/then/else logic for dynamic flows
- **[Data-Driven Testing](docs/data-driven.md)** - CSV, JSON, Excel data sources
- **[Soft Assertions](docs/soft-assertions.md)** - Continue tests on failures
- **[Test Suites](docs/TEST_BUILDER.md#test-suites)** - Group and execute multiple tests

### 🔧 Integration Guides
- **[AWS S3 Integration](docs/aws-s3-integration.md)** - Firmware management and version extraction
- **[OvrC API Integration](docs/TEST_BUILDER.md#ovrc-api-integration)** - WebSocket and HTTP API
- **[JSON-RPC WebSocket](docs/jsonrpc-websocket.md)** - Device communication protocol
- **[API Authentication](docs/api-authentication.md)** - OAuth, JWT, API keys
- **[Chrome Recorder Conversion](docs/CHROME_RECORDER_CONVERSION.md)** - Import Playwright recordings

### ⚙️ Configuration
- **[Browser Configuration](docs/BROWSER_CONFIG.md)** - Browser settings and options
- **[Security Implementation](SECURITY_IMPLEMENTATION.md)** - Security features and best practices 🔒
- **[Datalake Integration](docs/datalake-logger.md)** - Advanced logging and metrics
- **[Workspace Management](docs/WORKSPACE_MANAGEMENT.md)** - Organizing tests by workspace

### 🛠️ Development
- **[Contributing Guide](CONTRIBUTING.md)** - How to contribute, code standards 🎯
- **[Code Quality Tools](WEEK3_QUALITY.md)** - Pre-commit hooks, Makefile commands
- **[Performance Optimizations](WEEK2_PERFORMANCE.md)** - AWS S3 pooling, regex caching ⚡
- **[Troubleshooting](docs/troubleshooting.md)** - Common issues and solutions

## 🎯 Key Features

### Core Framework
- ✅ **No Programming Required** - Write tests in simple YAML or use visual Test Builder
- ✅ **Multi-Protocol Support** - Browser (Playwright), REST API, WebSocket, AWS S3, Serial, Android
- ✅ **Conditional Logic** - If/then/else steps for dynamic test flows
- ✅ **Variable Substitution** - Use `${variable}` syntax throughout tests
- ✅ **Setup/Cleanup Phases** - Proper test phase organization

### Browser Automation
- ✅ **Playwright Integration** - Chrome, Firefox, Safari, Edge support
- ✅ **Iframe Support** - File uploads and clicks inside iframes (`iframe >> selector`)
- ✅ **File Chooser API** - Handle hidden file inputs automatically
- ✅ **Role-Based Selectors** - Click by role (button, link, etc.) and name
- ✅ **Chrome Recorder** - Convert Playwright recordings to YAML

### Testing Capabilities
- ✅ **Soft Assertions** - Continue on failures, collect all issues
- ✅ **Custom Assertions** - Python expression evaluation, JSON schema validation
- ✅ **Data-Driven Testing** - Run same test with multiple data sets
- ✅ **Async Execution** - 3x faster with concurrent test execution
- ✅ **Test Suites** - Group and execute multiple tests together

### AWS Integration
- ✅ **S3 Operations** - List, download, upload firmware files
- ✅ **Version Management** - Auto-extract firmware versions, intelligent sorting
- ✅ **CloudFront URLs** - Generate CDN URLs from S3 paths

### OvrC API Integration
- ✅ **WebSocket Support** - JSON-RPC over WebSocket for device communication
- ✅ **HTTP API Support** - RESTful API with automatic authentication
- ✅ **Auto-Connection Management** - Automatic connect/disconnect handling
- ✅ **Flexible Commands** - Support for any OvrC command via `ovrc.send` or `ovrc.http.request`

### Reporting & Logging
- ✅ **Automatic Time Tracking** - Calculate time savings automatically
- ✅ **Datalake Integration** - Advanced logging with error hints
- ✅ **Rich Reporting** - HTML reports with simple and debug log tabs
- ✅ **Report Generation** - Generate beautiful HTML reports from test results
- ✅ **Teams Notifications** - Auto-post results to Microsoft Teams

## 🎥 UI Recorder Integration

Convert browser recordings from popular tools into Easy BDD tests:

### Convert Recordings
```bash
# Convert Playwright, Selenium, Cypress recordings
python -m easy_bdd convert recorded_test.json

# Specify output file
python -m easy_bdd convert recorded_test.json --output my_test.yaml

# Auto-detect format (or specify: playwright, selenium, cypress, puppeteer)
python -m easy_bdd convert recorded_test.json --format-type auto
```

### Supported Formats
- **Playwright Test Generator** - JSON with actions array
- **Selenium IDE** - JSON with tests and commands
- **Cypress Test Runner** - JSON with commands array  
- **Puppeteer recordings** - JSON with page interactions

See [RECORDER_INTEGRATION.md](RECORDER_INTEGRATION.md) for detailed documentation.

## 📖 Test Definition Format

### Basic Structure
```yaml
name: "Test Name"
description: "What this test does"
tags: ["tag1", "tag2"]  # Optional

variables:
  var_name: "value"
  api_url: "https://api.example.com"

setup:  # Optional - runs before test
  - action: "Setup action"

steps:
  - action: "Action name"
    parameter: "value"

cleanup:  # Optional - runs after test
  - action: "Cleanup action"
```

### Variable Usage

Easy BDD supports multiple variable scopes with Postman-like functionality:

#### Variable Scopes (Priority Order)
1. **Test Variables** - `${variable_name}` - Variables defined in the test YAML file
2. **Suite Variables** - `${suite.variable_name}` - Variables specific to a test suite
3. **Collection/Workspace Variables** - `${collection.variable_name}` or `${workspace.variable_name}` - Variables for a workspace/collection
4. **Environment Variables** - `${env.variable_name}` - Global environment variables (from active environment)
5. **Global Variables** - Framework defaults and config file variables

#### Basic Variable Usage
Use `${variable_name}` to reference test-level variables:

```yaml
variables:
  base_url: "https://staging.example.com"
  username: "testuser"

steps:
  - browser.open:
    url: "${base_url}/login"
  - browser.fill:
    field: "username"
    value: "${username}"
```

### 🔒 Security Best Practices

**Use Environment Variables for Sensitive Data:**
```yaml
# .env file (never commit this!)
DEVICE_PASSWORD=secret123  # pragma: allowlist secret
API_KEY=sk_live_abc123xyz  # pragma: allowlist secret

# test.yaml - reference environment variables
variables:
  password: "${DEVICE_PASSWORD}"
  api_key: "${API_KEY}"
```

**Validate Tests Before Running:**
```bash
# Check for security issues and syntax errors
python -m easy_bdd validate tests/cases/

# Strict mode (warnings = errors)
python -m easy_bdd validate tests/cases/ --strict
```

**What Gets Validated:**
- ✅ Hardcoded passwords or tokens in test files
- ✅ Proper YAML syntax and structure
- ✅ Correct action format (dot notation)
- ✅ Valid conditional step syntax

See [SECURITY_IMPLEMENTATION.md](SECURITY_IMPLEMENTATION.md) for complete security documentation.

## 🎯 Common Use Cases & Examples

### Browser Testing with Login

```yaml
name: Login Test
variables:
  base_url: "https://example.com"
  username: "testuser"
  password: "TestPass123"  # pragma: allowlist secret

steps:
  - browser.open:
    url: "${base_url}/login"

  - browser.fill:
    field: "#username"
    value: "${username}"

  - browser.fill:
    field: "#password"
    value: "${password}"

  - browser.click:
    role: button
    name: "Log In"

  - browser.wait:
    timeout: 2000

  - browser.screenshot:
    name: "after-login"

  - test.assert:
    expression: "'Dashboard' in page_content"
```

### OvrC API Testing

```yaml
name: OvrC Device Info Test
variables:
  server_url: "ws://192.168.1.100:8080"
  device_id: "4B:00:00:00:00:15"

steps:
  # Connect to OvrC WebSocket
  - ovrc.connect:
      server_url: "${server_url}"
      device_id: "${device_id}"

  # Get device information
  - ovrc.send:
      method: "dxGetAbout"
      store_as: "device_info"

  # Make HTTP API request
  - ovrc.http.request:
      method: "GET"
      endpoint: "/api/v1/devices/${device_id}"
      store_as: "device_data"

  # Assert device info
  - test.assert:
      expression: "'firmware' in device_info"
      message: "Device info should contain firmware"
```

### Test Suites

Create a test suite to run multiple tests:

1. **In Test Builder**: Click "Test Suites" → "Create Suite"
2. **Add Tests**: Select tests to include in the suite
3. **Configure**: Set execution order, enable/disable tests
4. **Execute**: Run the entire suite with one click

See [Test Builder Guide](docs/TEST_BUILDER.md#test-suites) for detailed instructions.

### File Upload in Iframe

```yaml
- browser.upload:
  selector: 'iframe >> #file-input'
  file_path: 'path/to/file.bin'

- browser.click:
  selector: 'iframe >> #upload-button'
```

### Conditional Firmware Upgrade

```yaml
variables:
  current_version: "2.1.0.0"
  target_version: "2.2.0.0"

steps:
  - condition: "current_version < target_version"
    then:
      - browser.upload:
        selector: 'iframe >> #firmware'
        file_path: 'Firmware/${firmware_file}'

      - browser.click:
        selector: 'iframe >> #upgrade-button'
    else:
      - browser.screenshot:
        name: "already-updated"
```

### AWS S3 Firmware Management

```yaml
setup:
  # Get list of all firmware files
  - aws.s3.list:
    bucket_name: "my-bucket"
    folder_prefix: "firmware/"
    file_extension: ".bin"
    download_dir: "Firmware"
    store_as: "firmware_list"

  # Get latest firmware
  - aws.s3.get_latest:
    bucket_name: "my-bucket"
    folder_prefix: "firmware/"
    file_extension: ".bin"
    download_dir: "Firmware"
    store_filename_as: "latest_fw"
    store_version_as: "latest_version"

steps:
  # Use downloaded firmware
  - browser.upload:
    selector: "#firmware-input"
    file_path: "Firmware/${latest_fw_basename}"
```

### API Testing with Assertions

```yaml
- api.get:
  url: "https://api.example.com/users/123"
  headers:
    Authorization: "Bearer ${api_token}"

- test.assert:
  expression: "last_status == 200"
  message: "API should return 200"

- test.assert:
  expression: "last_json['id'] == 123"
  message: "Should return correct user ID"

- test.assert:
  expression: "'email' in last_json"
  message: "Response should contain email field"
```

## ⚙️ Configuration

Create `config/framework.yaml`:

```yaml
config:
  browser:
    default: "chrome"
    headless: false
    window_size: [1920, 1080]
    timeout: 30

  api:
    timeout: 30
    verify_ssl: true
    max_retries: 3

  reporting:
    output_dir: "reports"
    screenshots: true
    html_report: true

  parallel:
    workers: 2

environments:
  staging:
    base_url: "https://staging.example.com"
    api_url: "https://api-staging.example.com"

  production:
    base_url: "https://example.com"
    api_url: "https://api.example.com"
```

## 🏗️ Project Structure

```
Automation-Framework/
├── easy_bdd/                # Framework core
│   ├── core/               # Core functionality
│   │   ├── config.py       # Configuration management
│   │   ├── parser.py       # YAML parser
│   │   ├── generator.py    # Gherkin generator
│   │   └── runner.py       # Test runner
│   └── services/           # Protocol implementations
│       ├── browser_service.py
│       ├── api_service.py
│       ├── aws_service.py
│       ├── jsonrpc_service.py
│       └── ovrc_api_service.py
├── frontend/                # Test Builder Web Application
│   ├── test_builder_app.py # FastAPI backend
│   ├── action_definitions.py # Action catalog
│   ├── static/
│   │   └── test_builder.html # Vue.js frontend
│   └── start_builder.py    # Server launcher
├── tests/
│   ├── cases/              # Your YAML test definitions
│   ├── data/               # Test data (CSV, JSON)
│   ├── templates/          # Test templates
│   └── features/           # Generated Gherkin files
├── config/
│   └── framework.yaml      # Framework configuration
├── reports/                # Test reports and artifacts
├── test_suites/            # Test suite definitions
├── docs/                   # Complete documentation
└── README.md
```

## 🚀 Advanced Usage

### Running with Different Environments
```bash
python -m easy_bdd run --env staging
python -m easy_bdd run --env production
```

### Tag-Based Test Organization
```yaml
# Organize tests with tags
tags: ["smoke", "browser", "critical"]

# Run specific test types
python -m easy_bdd run --tags smoke
python -m easy_bdd run --tags browser,api
```

### Test Data Management
```yaml
# Reference external data
data_source: "test_data.csv"
steps:
  - browser.fill:
    field: "username"
    value: "${data.username}"  # From CSV column
```

## 🐛 Common Issues & Debugging

### Browser Issues

**Issue: Browser doesn't open**
```bash
# Install browser again
playwright install chromium

# Run with --headed to see what's happening
python -m easy_bdd run tests/cases/my_test.yaml --headed
```

**Issue: Element not found**
```yaml
# Add wait before clicking
- browser.wait:
  timeout: 2000

# Use role-based selectors (more reliable)
- browser.click:
  role: button
  name: "Submit"
```

**Issue: File upload fails**
```yaml
# For hidden inputs in iframes, use iframe syntax
- browser.upload:
  selector: 'iframe >> #file-input'
  file_path: 'full/path/to/file.bin'
```

### AWS Issues

**Issue: AWS credentials not found**
```bash
# Configure AWS CLI
aws configure

# Or set environment variables
export AWS_ACCESS_KEY_ID="your-key"  # pragma: allowlist secret
export AWS_SECRET_ACCESS_KEY="your-secret"  # pragma: allowlist secret
export AWS_DEFAULT_REGION="us-east-1"
```

### Test Execution Issues

**Issue: Test hangs or times out**
```yaml
# Increase timeout
- browser.wait_for_element:
  selector: "#slow-element"
  timeout: 30000  # 30 seconds

# Add explicit waits
- browser.wait:
  timeout: 5000
```

**Issue: Variables not substituting**
```yaml
# Correct syntax with curly braces
url: "${base_url}/api"  # ✅ Correct

# Wrong syntax
url: "$base_url/api"    # ❌ Won't work
```

### Installation Issues

**Issue: SyntaxError with gherkin package during installation**
```bash
# Error: SyntaxError: invalid syntax (ur'...')
# This happens with old pytest-bdd versions on Python 3.9+

# Solution: Upgrade pip first, then install
pip install --upgrade pip
pip install -e .

# If still having issues, skip bytecode compilation:
PYTHONDONTWRITEBYTECODE=1 pip install -e .
```

**Issue: pip install -e . fails with "setuptools-based build required"**
```bash
# Upgrade pip to support pyproject.toml editable installs
pip install --upgrade pip
pip install -e .
```

### Getting Help

1. **Check Documentation**: See `/docs` folder for detailed guides
2. **Enable Debug Output**: Run with `-v` or `--verbose`
3. **Check Reports**: Review HTML reports in `/reports` folder
4. **View Screenshots**: Check screenshots for visual debugging
5. **Check Logs**: Console output shows detailed step execution

**Useful Commands:**
```bash
# Run with visible browser
python -m easy_bdd run test.yaml --headed

# Generate features without running
python -m easy_bdd generate tests/cases/

# View framework version
python -m easy_bdd --version

# Get help
python -m easy_bdd --help
```

## 🏆 Why Choose Easy BDD Framework?

✅ **User-Friendly**: No programming knowledge required - write YAML or use visual Test Builder  
✅ **Powerful**: Conditional logic, AWS integration, iframe support, soft assertions, test suites  
✅ **Flexible**: Supports all protocols - browser, API, WebSocket, AWS, Serial, Android, OvrC  
✅ **Maintainable**: Standard YAML format everyone can read  
✅ **Independent**: No external dependencies like TestRail  
✅ **Extensible**: Easy to add new protocols and actions  
✅ **Modern**: Built with Playwright, FastAPI, Vue.js, and current best practices  
✅ **Fast**: Async execution for 3x faster test runs  
✅ **Visual**: Beautiful web interface for test creation and management  

## 📚 Additional Resources

- **[User Guide](docs/USER_GUIDE.md)** - Complete user guide for the framework
- **[New Features Guide](docs/NEW_FEATURES.md)** - Latest features and improvements
- **[Test Builder Guide](docs/TEST_BUILDER.md)** - Complete guide to the web application
- **[API Reference](docs/API_REFERENCE.md)** - Complete REST API documentation
- **[Syntax Cheat Sheet](docs/SYNTAX_CHEATSHEET.md)** - Quick reference for all actions
- **[Metrics & Analytics](docs/metrics-analytics.md)** - Metrics dashboard and analytics guide
- **[Examples](docs/examples.md)** - Real-world test examples
- **[Troubleshooting](docs/troubleshooting.md)** - Common issues and solutions
- **[Contributing](CONTRIBUTING.md)** - How to contribute to the project

---

**Ready to get started?**

1. **Quick Start**: `python frontend/start_builder.py` → http://localhost:8000
2. **Read the Docs**: Check out `/docs` folder for comprehensive guides
3. **Try Examples**: See `/tests/cases/` for example test files

For detailed guides, see the `/docs` folder. For examples, check `/tests/cases/` directory.
