# Easy BDD Testing Framework

A powerful, user-friendly YAML-based BDD testing framework that supports multiple protocols including browser automation, REST APIs, WebSocket, AWS S3, Serial, and Android. No programming knowledge required.

## ✨ What's New

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

### First-Time Setup

1. **Clone and Install**
```bash
git clone <repository-url>
cd Automation-Framework
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .
playwright install chromium  # Or: firefox, webkit
```

2. **Configure AWS (Optional)**
```bash
# If using AWS features, configure AWS CLI
aws configure
# Or set environment variables:
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_DEFAULT_REGION="us-east-1"
```

3. **Verify Installation**
```bash
python -m easy_bdd --help
```

### Your First Test

Create `tests/cases/hello_world.yaml`:
```yaml
name: Hello World Test
description: My first Easy BDD test
tags: [demo]

variables:
  website: "https://example.com"

steps:
  - action: browser.open
    url: ${website}
  
  - action: browser.screenshot
    name: "homepage"
  
  - action: test.assert
    expression: "'Example Domain' in page_content"
    message: "Should show Example Domain"
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

- **[Getting Started Guide](docs/setup.md)** - Installation and configuration
- **[Contributing Guide](CONTRIBUTING.md)** - How to contribute, code standards 🎯
- **[Code Quality Tools](WEEK3_QUALITY.md)** - Pre-commit hooks, Makefile, development setup
- **[Performance Optimizations](WEEK2_PERFORMANCE.md)** - AWS S3 pooling, regex caching ⚡
- **[Security Implementation](SECURITY_IMPLEMENTATION.md)** - Security features and best practices 🔒
- **[Recommendations](RECOMMENDATIONS.md)** - Security, performance, and feature recommendations
- **[Dot Notation Actions](docs/dot-notation-actions.md)** - New unified action syntax ✨
- **[YAML Syntax Reference](docs/syntax.md)** - Test file structure
- **[Action Reference](docs/actions.md)** - All available actions
- **[Examples](docs/examples.md)** - Real-world test examples
- **[Conditional Steps](docs/conditional-steps.md)** - If/then/else logic
- **[AWS S3 Integration](docs/aws-s3-integration.md)** - Firmware management
- **[Chrome Recorder Conversion](docs/CHROME_RECORDER_CONVERSION.md)** - Import Chrome recordings
- **[Browser Configuration](docs/BROWSER_CONFIG.md)** - Browser settings
- **[Troubleshooting](docs/troubleshooting.md)** - Common issues

### 🎯 Key Features

**Core Framework:**
- ✅ **No Programming Required** - Write tests in simple YAML
- ✅ **Multi-Protocol Support** - Browser (Playwright), REST API, WebSocket, AWS S3, Serial, Android
- ✅ **Conditional Logic** - If/then/else steps for dynamic test flows
- ✅ **Variable Substitution** - Use `${variable}` syntax throughout tests
- ✅ **Setup/Cleanup Phases** - Proper test phase organization

**Browser Automation:**
- ✅ **Playwright Integration** - Chrome, Firefox, Safari, Edge support
- ✅ **Iframe Support** - File uploads and clicks inside iframes (`iframe >> selector`)
- ✅ **File Chooser API** - Handle hidden file inputs automatically
- ✅ **Role-Based Selectors** - Click by role (button, link, etc.) and name
- ✅ **Chrome Recorder** - Convert Playwright recordings to YAML

**Testing Capabilities:**
- ✅ **Soft Assertions** - Continue on failures, collect all issues
- ✅ **Custom Assertions** - Python expression evaluation, JSON schema validation
- ✅ **Data-Driven Testing** - Run same test with multiple data sets
- ✅ **Async Execution** - 3x faster with concurrent test execution

**AWS Integration:**
- ✅ **S3 Operations** - List, download, upload firmware files
- ✅ **Version Management** - Auto-extract firmware versions, intelligent sorting
- ✅ **CloudFront URLs** - Generate CDN URLs from S3 paths

**Reporting & Logging:**
- ✅ **Automatic Time Tracking** - Calculate time savings automatically
- ✅ **Datalake Integration** - Advanced logging with error hints
- ✅ **Rich Reporting** - HTML reports, screenshots, video recordings
- ✅ **Teams Notifications** - Auto-post results to Microsoft Teams
    value: "${password}"
    
  - action: "Click button"
    button: "Sign In"
    
  - action: "Verify page contains"
    text: "Welcome"
```

### 3. Run Your Tests
```bash
# Validate tests first (recommended)
python -m easy_bdd validate tests/cases/

# Run all tests
python -m easy_bdd run

# Run specific test file
python -m easy_bdd run tests/cases/my_first_test.yaml

# Run tests with specific tags
python -m easy_bdd run --tags browser,login

# Generate Gherkin features only
python -m easy_bdd generate tests/cases/
```

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
Use `${variable_name}` to reference variables:

```yaml
variables:
  base_url: "https://staging.example.com"
  username: "testuser"

steps:
  - action: "Open browser"
    url: "${base_url}/login"
  - action: "Fill form field"
    field: "username"
    value: "${username}"
```

### 🔒 Security Best Practices

**Use Environment Variables for Sensitive Data:**
```yaml
# .env file (never commit this!)
DEVICE_PASSWORD=secret123
API_KEY=sk_live_abc123xyz

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
  password: "TestPass123"

steps:
  - action: Open browser
    url: "${base_url}/login"
  
  - action: Fill form field
    field: "#username"
    value: "${username}"
  
  - action: Fill form field
    field: "#password"
    value: "${password}"
  
  - action: Click element
    role: button
    name: "Log In"
  
  - action: Wait
    timeout: 2000
  
  - action: Take screenshot
    name: "after-login"
  
  - action: Assert
    expression: "'Dashboard' in page_content"
```

### File Upload in Iframe

```yaml
- action: Upload file
  selector: 'iframe >> #file-input'
  file_path: 'path/to/file.bin'

- action: Click element
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
      - action: Upload file
        selector: 'iframe >> #firmware'
        file_path: 'Firmware/${firmware_file}'
      
      - action: Click element
        selector: 'iframe >> #upgrade-button'
    else:
      - action: Take screenshot
        name: "already-updated"
```

### AWS S3 Firmware Management

```yaml
setup:
  # Get list of all firmware files
  - action: "AWS list firmware files"
    bucket_name: "my-bucket"
    folder_prefix: "firmware/"
    file_extension: ".bin"
    download_dir: "Firmware"
    store_as: "firmware_list"
  
  # Get latest firmware
  - action: "AWS get latest firmware"
    bucket_name: "my-bucket"
    folder_prefix: "firmware/"
    file_extension: ".bin"
    download_dir: "Firmware"
    store_filename_as: "latest_fw"
    store_version_as: "latest_version"

steps:
  # Use downloaded firmware
  - action: Upload file
    selector: "#firmware-input"
    file_path: "Firmware/${latest_fw_basename}"
```

### API Testing with Assertions

```yaml
- action: Send API request
  method: GET
  url: "https://api.example.com/users/123"
  headers:
    Authorization: "Bearer ${api_token}"

- action: Assert
  expression: "last_status == 200"
  message: "API should return 200"

- action: Assert
  expression: "last_json['id'] == 123"
  message: "Should return correct user ID"

- action: Assert
  expression: "'email' in last_json"
  message: "Response should contain email field"
```

### 🔌 API Actions
```yaml
# Send HTTP requests
- action: "Send API request"
  method: "POST"
  url: "https://api.example.com/users"
  headers:
    Content-Type: "application/json"
    Authorization: "Bearer ${token}"
  body:
    name: "John Doe"
    email: "john@example.com"

# Verify responses
- action: "Verify API response"
  status_code: 200
  contains:
    message: "User created"

# Extract data from responses
- action: "Extract from response"
  field: "user.id"
  save_as: "user_id"
```

### 📱 Android Actions
```yaml
# Connect to device
- action: "Connect to android device"
  device_id: "emulator-5554"

# Interact with elements
- action: "Tap element"
  id: "com.app:id/login_button"

- action: "Enter text"
  id: "com.app:id/username"
  text: "testuser"

# Verify screen content
- action: "Verify screen contains"
  text: "Login successful"
```

### ☁️ AWS Actions
```yaml
# S3 operations
- action: "AWS S3 upload"
  bucket: "test-bucket"
  file: "test.txt"
  key: "uploads/test.txt"

# Lambda functions
- action: "AWS Lambda invoke"
  function: "test-function"
  payload:
    message: "test"

# Verify AWS responses
- action: "Verify AWS response"
  contains:
    statusCode: 200
```

### 🔌 WebSocket Actions
```yaml
# Connect to WebSocket
- action: "Connect to websocket"
  url: "ws://localhost:8080/chat"

# Send messages
- action: "Send websocket message"
  message: "Hello World"

# Wait for messages
- action: "Wait for websocket message"
  contains: "Welcome"
  timeout: 10
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
easy-bdd-framework/
├── easy_bdd/                # Framework core
│   ├── core/               # Core functionality
│   │   ├── config.py       # Configuration management
│   │   ├── parser.py       # YAML parser
│   │   ├── generator.py    # Gherkin generator
│   │   └── runner.py       # Test runner
│   └── services/           # Protocol implementations (future)
├── tests/
│   ├── cases/              # Your YAML test definitions
│   └── features/           # Generated Gherkin files
├── config/
│   └── framework.yaml      # Framework configuration
├── reports/                # Test reports and artifacts
├── pyproject.toml          # Python package configuration
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
# Reference external data (future feature)
data_source: "test_data.csv"
steps:
  - action: "Fill form field"
    field: "username"
    value: "${data.username}"  # From CSV column
```

## 🔧 VS Code Integration

The framework includes VS Code tasks for easy execution:

- **Run Tests**: `Ctrl+Shift+P` → "Tasks: Run Task" → "Run Easy BDD Tests"
- **Python Extension**: Automatic syntax highlighting and validation
- **Integrated Terminal**: Run commands directly in VS Code

## 🆚 Comparison with Original Framework

| Feature | Original Framework | Easy BDD Framework |
|---------|-------------------|-------------------|
| Test Definition | Pipe-delimited syntax | Simple YAML |
| Test Storage | TestRail integration | File-based |
| Learning Curve | Requires training | Intuitive for non-programmers |
| Protocol Support | ✅ All protocols | ✅ All protocols (architecture ready) |
| Variable System | `$variable` | `${variable}` |
| Gherkin Generation | ✅ | ✅ |
| Flexibility | High | High |
| Maintenance | Custom syntax | Standard YAML |

## 🤝 Migration from Original Framework

To migrate from your original framework:

1. **Convert Test Cases**: Transform pipe-delimited tests to YAML format
2. **Update Variables**: Change `$var` to `${var}` syntax  
3. **File Organization**: Move tests from TestRail to YAML files
4. **Configuration**: Set up `framework.yaml` configuration
5. **Execution**: Use new command-line interface

## 📋 Development Guidelines

- Keep test definitions simple and readable
- Use descriptive action names
- Organize tests with meaningful tags
- Leverage variables for reusability
- Follow consistent naming conventions

## 🔮 Future Roadmap

- **Service Implementations**: Complete browser, API, WebSocket, Android, AWS, and Serial services
- **Data-Driven Testing**: CSV/Excel file integration
- **Custom Actions**: Plugin system for extending functionality
- **Enhanced Reporting**: Allure integration, video recording
- **IDE Integration**: Enhanced VS Code extension
- **CI/CD Integration**: Jenkins, GitHub Actions templates

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
- action: Wait
  timeout: 2000

# Use role-based selectors (more reliable)
- action: Click element
  role: button
  name: "Submit"

# Check selector in browser DevTools
```

**Issue: File upload fails**
```yaml
# For hidden inputs in iframes, use iframe syntax
- action: Upload file
  selector: 'iframe >> #file-input'
  file_path: 'full/path/to/file.bin'

# Framework automatically handles hidden inputs with file chooser API
```

### AWS Issues

**Issue: AWS credentials not found**
```bash
# Configure AWS CLI
aws configure

# Or set environment variables
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_DEFAULT_REGION="us-east-1"

# Framework uses this priority: explicit params > env vars > AWS CLI config
```

**Issue: Firmware file not found**
```yaml
# The framework stores basename automatically
setup:
  - action: "AWS get latest firmware"
    store_filename_as: "firmware_key"
    # This creates: firmware_key_basename

steps:
  # Use the basename for local file path
  - action: Upload file
    file_path: "Firmware/${firmware_key_basename}"
```

### Test Execution Issues

**Issue: Test hangs or times out**
```yaml
# Increase timeout
- action: Wait for element
  selector: "#slow-element"
  timeout: 30000  # 30 seconds

# Add explicit waits
- action: Wait
  timeout: 5000
```

**Issue: Variables not substituting**
```yaml
# Correct syntax with curly braces
url: "${base_url}/api"  # ✅ Correct

# Wrong syntax
url: "$base_url/api"    # ❌ Won't work
```

**Issue: Assertion fails unexpectedly**
```yaml
# Use soft assertions to see all failures
- action: Assert
  expression: "status_code == 200"
  soft_assert: true

# Check variable values
- action: Assert
  expression: "my_variable is not None"
  message: "Debug: checking variable"
```

### Conditional Steps Issues

**Issue: Condition not evaluating**
```yaml
# Ensure variables are defined before condition
setup:
  - action: "AWS get latest firmware"
    store_version_as: "firmware_version"

steps:
  # Now firmware_version is available
  - condition: "firmware_version >= '2.0.0.0'"
    then:
      - action: Take screenshot
```

**Issue: Syntax error in condition**
```yaml
# Use Python expressions
- condition: "version >= '2.0.0.0'"        # ✅ String comparison
- condition: "count > 5"                    # ✅ Numeric
- condition: "'text' in page_content"      # ✅ String contains
- condition: "item is not None"            # ✅ Existence check
- condition: "status == 'ready' and count > 0"  # ✅ Multiple conditions
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

✅ **User-Friendly**: No programming knowledge required - just write YAML  
✅ **Powerful**: Conditional logic, AWS integration, iframe support, soft assertions  
✅ **Flexible**: Supports all protocols - browser, API, WebSocket, AWS, Serial, Android  
✅ **Maintainable**: Standard YAML format everyone can read  
✅ **Independent**: No external dependencies like TestRail  
✅ **Extensible**: Easy to add new protocols and actions  
✅ **Modern**: Built with Playwright, boto3, and current best practices  
✅ **Fast**: Async execution for 3x faster test runs  

## 📚 Project Structure

See [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for complete directory layout.

```
Automation-Framework/
├── easy_bdd/          # Framework source code
├── tests/cases/       # Your YAML test files  
├── config/            # Configuration files
├── docs/              # Complete documentation
├── reports/           # Test results and screenshots
└── Firmware/          # Downloaded firmware files
```

---

**Ready to get started?** Create your first YAML test file and experience the difference! 🎉

For detailed guides, see the `/docs` folder. For examples, check `/tests/cases/` directory.