# Setup and Installation Guide

Complete guide to setting up the Easy BDD Testing Framework.

## 🎯 Prerequisites

### System Requirements
- **Python 3.8+** (Check: `python --version`)
- **Git** (Check: `git --version`)
- **4GB+ RAM** (for browser automation)
- **2GB+ disk space** (for dependencies)

### Operating System Support
- ✅ macOS 10.15+
- ✅ Windows 10+
- ✅ Linux (Ubuntu 18.04+, CentOS 7+)

## 📥 Installation

### Step 1: Clone Repository
```bash
git clone <repository-url>
cd Easy_BDD
```

### Step 2: Create Virtual Environment
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# macOS/Linux:
source .venv/bin/activate

# Windows:
.venv\Scripts\activate
```

### Step 3: Install Framework
```bash
# Install in development mode
pip install -e .

# Or install from requirements
pip install -r requirements.txt
```

### Step 4: Install Browser Dependencies
```bash
# Install Playwright browsers
playwright install

# Install specific browser only
playwright install chromium
```

### Step 5: Verify Installation
```bash
# Test framework installation
python -m easybdd --help

# Run example test
python -m easybdd run tests/cases/simple_test.yaml --headed
```

## ⚙️ Configuration

### Framework Configuration
Edit `config/framework.yaml`:

```yaml
# Browser settings
browser:
  type: "chromium"          # chromium, firefox, webkit
  headless: false           # true for headless mode
  timeout: 30000           # Page load timeout (ms)
  slowMo: 0                # Slow down actions (ms)
  
# Reporting
reporting:
  output_dir: "reports"     # Report output directory
  screenshots: true         # Enable screenshots
  video: false             # Enable video recording
  
# Test execution
execution:
  default_timeout: 5000     # Element timeout (ms)
  retry_count: 3           # Retry failed actions
  parallel_workers: 1      # Default parallel execution
  
# Logging
logging:
  level: "INFO"            # DEBUG, INFO, WARNING, ERROR
  file: "logs/test.log"    # Log file location
```

### Environment Variables
Create `.env` file for sensitive data:

```env
# Application URLs
STAGING_URL=https://staging.example.com
PROD_URL=https://example.com
LOCAL_URL=http://localhost:3000

# Credentials (use secure storage in production)
TEST_USERNAME=test_user
TEST_PASSWORD=secure_password
API_KEY=your_api_key_here

# Browser settings
HEADLESS=false
SLOW_MO=0
```

Reference in tests:
```yaml
variables:
  app_url: "{{STAGING_URL}}"
  username: "{{TEST_USERNAME}}"
  password: "{{TEST_PASSWORD}}"
```

## 🗂 Project Structure Setup

### Recommended Directory Layout
```
Easy_BDD/
├── config/                 # Configuration files
│   ├── framework.yaml     # Main framework config
│   └── environments/      # Environment-specific configs
├── tests/
│   ├── cases/             # Test definitions (.yaml)
│   ├── data/              # Test data files (.csv, .json)
│   ├── features/          # Generated Gherkin files
│   └── templates/         # Reusable test templates
├── reports/               # Test results
│   ├── screenshots/       # Test screenshots
│   ├── videos/           # Test recordings
│   └── logs/             # Execution logs
├── docs/                  # Documentation
├── .env                   # Environment variables
├── .gitignore            # Git ignore rules
└── requirements.txt       # Python dependencies
```

### Create Directory Structure
```bash
# Create directories
mkdir -p tests/{cases,data,features,templates}
mkdir -p config/environments
mkdir -p reports/{screenshots,videos,logs}
mkdir -p docs

# Create basic files
touch .env
touch config/environments/{dev,staging,prod}.yaml
touch tests/data/.gitkeep
touch reports/.gitkeep
```

## 🧪 First Test Setup

### Create Simple Test
Create `tests/cases/hello_world.yaml`:

```yaml
name: Hello World Test
description: My first Easy BDD test
tags:
  - demo
  - smoke

variables:
  website: "https://example.com"
  
steps:
  - browser.open:
      url: "{{website}}"
      description: Open the test website
    
  - browser.screenshot:
      filename: "homepage"
      description: Capture homepage
    
  - browser.verify_text:
      text: "Example Domain"
      description: Verify page loaded correctly
```

### Run First Test
```bash
# Run with visible browser
python -m easybdd run tests/cases/hello_world.yaml --headed

# Run in headless mode
python -m easybdd run tests/cases/hello_world.yaml

# Generate Gherkin only
python -m easybdd generate tests/cases/hello_world.yaml
```

## 🔧 IDE Setup

### VS Code Extensions
Recommended extensions:

1. **Python** - Python language support
2. **YAML** - YAML syntax highlighting
3. **GitLens** - Git integration
4. **Playwright Test for VSCode** - Playwright integration

### VS Code Settings
Add to `.vscode/settings.json`:

```json
{
  "python.defaultInterpreterPath": "./.venv/bin/python",
  "python.terminal.activateEnvironment": true,
  "files.associations": {
    "*.yaml": "yaml"
  }
}
```

> There's no bundled JSON Schema for `tests/cases/*.yaml` — syntax is validated at
> runtime via `make validate` / `python -m easybdd validate`, not by an IDE schema.

### IntelliJ/PyCharm Setup
1. Open project directory
2. Configure Python interpreter to use `.venv/bin/python`
3. Install Python and YAML plugins
4. Configure run configurations for test execution

## 🚀 Advanced Setup

### Docker Support
The repo already ships a `Dockerfile` at the project root — no need to create one.

```bash
# Build image
docker build -t easy-bdd-framework .

# Run tests (default CMD runs everything in tests/cases/)
docker run -v $(pwd)/reports:/app/reports easy-bdd-framework

# Or override the command
docker run -v $(pwd)/reports:/app/reports easy-bdd-framework python -m easybdd run tests/cases/ --tags smoke
```

Alternatively, `make run` on the CLI target is usually simpler for local dev — Docker is
mainly useful for reproducing CI-exact browser dependencies.

### CI/CD Integration

This repo's CI already lives in the `Jenkinsfile*` files at the root (see
[ONBOARDING.md](../ONBOARDING.md#7-cicd--jenkins-pipelines) for what each one does) plus
one GitHub Actions workflow, `.github/workflows/create-smoke-run.yml`. Adding a new
GitHub Actions workflow follows the same shape:

```yaml
name: Easy BDD Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        pip install -e .
        playwright install --with-deps chromium

    - name: Run tests
      run: |
        python -m easybdd run tests/cases/ --tags smoke

    - name: Upload test results
      uses: actions/upload-artifact@v4
      if: always()
      with:
        name: test-results
        path: reports/
```

See [docs/ci-cd-integration.md](./ci-cd-integration.md) for TestRail-run-creation details.

#### Jenkins Pipeline
The repo already has multiple `Jenkinsfile.*` pipelines at the root — see
[ONBOARDING.md](../ONBOARDING.md#7-cicd--jenkins-pipelines) for what each covers. There's
no need to author a new one for standard test runs; point a Jenkins job at the existing
`Jenkinsfile` (or one of the `Jenkinsfile.testrail-*` variants) and supply the required
credentials/parameters. Only write a new `Jenkinsfile.<name>` if you need a genuinely new
pipeline shape.

## 🔍 Troubleshooting Setup

### Common Issues

#### Python Version Issues
```bash
# Check Python version
python --version

# Use specific Python version
python3.9 -m venv .venv
```

#### Permission Issues (macOS/Linux)
```bash
# Fix permissions
chmod +x .venv/bin/activate
sudo chown -R $USER:$USER .
```

#### Browser Installation Issues
```bash
# Reinstall browsers
playwright uninstall --all
playwright install

# Install system dependencies (Linux)
sudo playwright install-deps
```

#### Import Issues
```bash
# Reinstall in development mode
pip uninstall easy-bdd-framework
pip install -e .

# Clear Python cache
find . -name "__pycache__" -delete
find . -name "*.pyc" -delete
```

### Verification Commands
```bash
# Test Python import
python -c "import easybdd; print('Framework imported successfully')"

# Test Playwright
python -c "from playwright.sync_api import sync_playwright; print('Playwright working')"

# Test browser launch
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    browser.close()
    print('Browser launch successful')
"
```

### Getting Help

1. **Check logs**: `reports/logs/test.log`
2. **Enable debug mode**: Set `logging.level: DEBUG` in config
3. **Run with debug logging**: Set `logging.level: DEBUG` in `config/framework.yaml`, then `python -m easybdd run`
4. **Check documentation**: See other guides in `docs/`

---

*Next: Read the [Syntax Reference](./syntax.md) to start writing tests*