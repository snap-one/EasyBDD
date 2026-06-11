# Easy BDD Testing Framework

A user-friendly, YAML-based BDD testing framework that supports multiple protocols and doesn't require programming knowledge.

## 🚀 Quick Start

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd Automation-Framework
   ```

2. **Set up Python environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On macOS/Linux
   # .venv\Scripts\activate   # On Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -e .
   ```

4. **Install Playwright browsers:**
   ```bash
   playwright install
   ```

### First Test

Create a simple test file `tests/cases/my_first_test.yaml`:

```yaml
name: My First Test
description: A simple web test
tags:
  - browser
  - demo

variables:
  website: https://example.com

steps:
  - action: Open browser
    url: ${website}
    description: Open the website
  
  - action: Take screenshot
    name: homepage
    description: Capture the homepage
  
  - action: Verify text
    text: "Example Domain"
    description: Check page title
```

Run the test:
```bash
python -m easy_bdd run tests/cases/my_first_test.yaml --headed
```

## 📚 Documentation Index

- **[Setup Guide](./setup.md)** - Complete installation and configuration
- **[Syntax Reference](./syntax.md)** - YAML syntax and structure
- **[Actions Reference](./actions.md)** - All available test actions
- **[TestRail Integration Guide](./testrail-integration.md)** - Run tests from TestRail (Feature, Shared, Var, Setup, Teardown)
- **[Data-Driven Testing](./data-driven.md)** - Using data arrays and variables
- **[Advanced Features](./advanced.md)** - Async execution, setup/cleanup
- **[Examples](./examples/)** - Real-world test examples
- **[Troubleshooting](./troubleshooting.md)** - Common issues and solutions

### Quick Start for TestRail Authors

Start here if you write test content directly in TestRail:

- **[TestRail-Safe Syntax (Recommended)](./testrail-integration.md#testrail-safe-syntax-recommended)**
- **[API + Token + Assert Recipes](./testrail-integration.md#api--token--assert-recipes)**
- **[Response Variables and Extraction Rules](./testrail-integration.md#response-variables-and-extraction-rules)**
- **[YAML File Format vs TestRail Feature Format](./testrail-integration.md#yaml-file-format-vs-testrail-feature-format)**
- **[Feature: Cases — Writing Steps in TestRail](./testrail-integration.md#feature-cases--writing-steps-in-testrail)**

Recommended authoring pattern inside TestRail fields (flow style):

```yaml
- api.request: {method: POST, url: "${url}/system/login", body: {user: "${username}", password: "${password}"}}
- eval.run: {expression: "last_json['restful_res']['token']", store_as: token}
- api.request: {method: GET, url: "${url}/system/status", headers: {Authorization: "Bearer ${token}"}}
- assert: {expression: "'systemInfo' in last_json"}
```

## 🎯 Key Features

- **No Programming Required** - Write tests in simple YAML
- **Multi-Protocol Support** - Browser, API, WebSocket, Mobile, AWS
- **Data-Driven Testing** - Run same test with multiple data sets
- **Async Execution** - Run tests concurrently for speed
- **Setup/Cleanup** - Organize test phases properly
- **Variable Substitution** - Use `${variable}` syntax throughout
- **Rich Reporting** - Screenshots, logs, and detailed results

## 🏗 Framework Architecture

```
easy_bdd/
├── core/                 # Framework core
│   ├── config.py        # Configuration management
│   ├── parser.py        # YAML/JSON parsing
│   ├── generator.py     # Gherkin generation
│   └── runner.py        # Test execution
├── services/            # Protocol implementations
│   ├── browser_service.py  # Browser automation
│   └── ...             # Other services
└── __main__.py         # CLI entry point

tests/
├── cases/              # Test definitions
├── data/               # Test data files
├── features/           # Generated Gherkin
└── templates/          # Test templates

config/
└── framework.yaml      # Framework configuration

reports/                # Test results
└── screenshots/        # Test screenshots
```

## 🎮 Command Line Usage

```bash
# Run specific test
python -m easy_bdd run tests/cases/my_test.yaml

# Run with browser visible
python -m easy_bdd run tests/cases/my_test.yaml --headed

# Run tests by tag
python -m easy_bdd run tests/cases/ --tags browser

# Generate Gherkin only
python -m easy_bdd generate tests/cases/my_test.yaml

# Dry run (parse only)
python -m easy_bdd run tests/cases/ --dry-run
```

## 📝 Basic Test Structure

```yaml
# Test metadata
name: Test Name
description: What this test does
tags: [tag1, tag2]

# Variables (optional)
variables:
  key: value

# Data array for data-driven testing (optional)
data:
  - param1: value1
    param2: value2
  - param1: value3
    param2: value4

# Setup steps (optional)
setup:
  - action: Setup Action
    parameter: value

# Main test steps (required)
steps:
  - action: Test Action
    parameter: value

# Cleanup steps (optional)
cleanup:
  - action: Cleanup Action
    parameter: value
```

## 🔗 Related Documentation

- [Playwright Documentation](https://playwright.dev/python/)
- [BDD Best Practices](https://cucumber.io/docs/bdd/)
- [YAML Syntax Guide](https://docs.ansible.com/ansible/latest/reference_appendices/YAMLSyntax.html)

## 📞 Support

For questions, issues, or contributions:
- Check the [Troubleshooting Guide](./troubleshooting.md)
- Review [Examples](./examples/)
- Create an issue in the repository

---

*Easy BDD Framework - Making test automation accessible to everyone* 🧪