# Easy BDD Framework - User Guide

Complete guide for using the Easy BDD Testing Framework, from installation to advanced features.

## 📋 Table of Contents

1. [Getting Started](#getting-started)
2. [Test Builder Web Application](#test-builder-web-application)
3. [Writing Tests](#writing-tests)
4. [Running Tests](#running-tests)
5. [Test Suites](#test-suites)
6. [Metrics & Analytics](#metrics--analytics)
7. [AI Assistant](#ai-assistant)
8. [Variables & Environments](#variables--environments)
9. [Best Practices](#best-practices)
10. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd easy_bdd
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install framework:**
   ```bash
   pip install --upgrade pip
   pip install -e .
   playwright install chromium
   ```

4. **Install Test Builder (Optional but Recommended):**
   ```bash
   cd frontend
   pip install -r requirements_builder.txt
   cd ..
   ```

### Quick Start

1. **Start Test Builder:**
   ```bash
   cd frontend
   python start_builder.py
   ```

2. **Open in browser:**
   - Navigate to http://localhost:8000
   - You'll see the dashboard

3. **Run a demo test:**
   - Go to **Test Suites** → **Demo Test Suite**
   - Click **Execute Suite**
   - Watch the tests run in real-time

### First Test

Create your first test using the Test Builder:

1. Click **New Test** in the sidebar
2. Enter test name and description
3. Click **Add Step**
4. Select an action (e.g., "Open Browser")
5. Fill in parameters
6. Click **Save**
7. Click **Run Test**

---

## Test Builder Web Application

### Overview

The Test Builder is a modern web interface for creating and managing tests without writing code.

### Main Views

- **Dashboard** - Overview of tests, results, and quick actions
- **My Tests** - Browse and manage all tests
- **Test Builder** - Create and edit tests visually
- **Test Results** - View execution results and reports
- **Test Suites** - Group and execute multiple tests
- **Actions Library** - Browse all available actions
- **Templates** - Start from pre-built templates
- **Variables** - Manage test variables and environments
- **Metrics & Analytics** - View test performance metrics
- **Settings** - Configure framework settings

### Navigation

- Use the sidebar to switch between views
- Click test/suite names to open them
- Use browser back/forward buttons
- URLs are shareable and bookmarkable

### Creating a Test

1. Click **New Test** or navigate to `/tests/new`
2. Fill in test metadata:
   - Name
   - Description
   - Tags (optional)
   - Workspace (optional)
3. Add steps:
   - Click **Add Step**
   - Select action from library
   - Fill in parameters
   - Click **Add Step** to save
4. Configure variables (optional):
   - Go to Variables tab
   - Add key-value pairs
5. Save test:
   - Click **Save** button
   - Test is saved as YAML file

### Editing a Test

1. Navigate to **My Tests**
2. Click on test name
3. Make changes
4. Click **Save**

### Running a Test

1. Open test in Test Builder
2. Click **Run Test** button
3. Watch execution in progress modal
4. View results when complete

---

## Writing Tests

### Test Structure

```yaml
name: My Test
description: Test description
tags: [tag1, tag2]
workspace: my-workspace

variables:
  url: https://example.com
  username: testuser

setup:
  - action: log
    message: Starting test

steps:
  - action: browser.open
    url: ${url}
  
  - action: browser.fill
    field: input[name="username"]
    value: ${username}

cleanup:
  - action: log
    message: Test complete
```

### Common Actions

#### Browser Actions

```yaml
# Open browser
- action: browser.open
  url: https://example.com

# Click element
- action: browser.click
  selector: button#submit

# Fill form field
- action: browser.fill
  field: input[name="email"]
  value: user@example.com

# Take screenshot
- action: browser.take_screenshot
  name: homepage

# Assert text
- action: test.assert_text_contains
  selector: h1
  text: Welcome
```

#### API Actions

```yaml
# GET request
- action: API request
  method: GET
  url: https://api.example.com/users
  store_response: users

# POST request
- action: API request
  method: POST
  url: https://api.example.com/users
  headers:
    Content-Type: application/json
  body:
    name: John Doe
    email: john@example.com
  store_response: new_user

# Assert response
- action: Assert response
  response: ${new_user}
  expect:
    status: 201
```

### Variables

Use `${variable_name}` to reference variables:

```yaml
variables:
  base_url: https://example.com
  username: testuser

steps:
  - action: browser.open
    url: ${base_url}/login
  
  - action: browser.fill
    field: input[name="username"]
    value: ${username}
```

### Conditional Logic

```yaml
steps:
  - action: if
    condition: ${status} == "success"
    then:
      - action: log
        message: Success!
    else:
      - action: log
        message: Failed!
```

### Data-Driven Testing

```yaml
data:
  - username: user1
    password: pass1
  - username: user2
    password: pass2

steps:
  - action: browser.fill
    field: input[name="username"]
    value: ${username}
  
  - action: browser.fill
    field: input[name="password"]
    value: ${password}
```

---

## Running Tests

### From Test Builder

1. Open test in Test Builder
2. Click **Run Test**
3. Monitor progress in modal
4. View results when complete

### From Command Line

```bash
# Run single test
python -m easy_bdd run tests/cases/my_test.yaml

# Run with visible browser
python -m easy_bdd run tests/cases/my_test.yaml --headed

# Run by tag
python -m easy_bdd run tests/cases/ --tags browser

# Run test suite
python -m easy_bdd run tests/cases/ --suite my_suite
```

### Test Suites

1. Navigate to **Test Suites**
2. Click **Create New Suite**
3. Add tests to suite
4. Configure execution order
5. Click **Execute Suite**

---

## Test Suites

### Creating a Suite

1. Go to **Test Suites**
2. Click **Create New Suite**
3. Enter suite name and description
4. Add tests:
   - Click **Add Test**
   - Select tests from list
   - Click **Add**
5. Reorder tests (drag and drop)
6. Enable/disable tests
7. Save suite

### Editing Tests in Suite

1. Open suite
2. Click **Edit** button next to test
3. Make changes in Test Builder
4. Click **Save**
5. Return to suite (prompted automatically)

### Executing Suites

1. Open suite
2. Click **Execute Suite**
3. Configure execution:
   - Max tests to run
   - Headless mode
4. Click **Execute**
5. Monitor progress
6. View results

---

## Metrics & Analytics

### Accessing Metrics

1. Navigate to **Metrics & Analytics** from sidebar
2. View comprehensive dashboard

### Time Period Filtering

1. Select time period from dropdown:
   - Last 7 Days
   - Last 2 Weeks
   - Last 3 Weeks
   - Last Month (default)
   - Last Quarter
2. Metrics automatically reload

### Available Metrics

- **Test Health** - Failing tests, flaky tests, stale tests
- **Execution Trends** - Time trends, failure rates, peak hours
- **Test Coverage** - By workspace, action type, complexity
- **Quick Insights** - Velocity, streaks, recent failures
- **Resource Tracking** - Storage usage

---

## AI Assistant

### Setup

1. Go to **Settings** → **OpenAI Configuration**
2. Enter your OpenAI API key
3. Click **Save**

### Using the Assistant

1. Click chat icon (💬) in top-right toolbar
2. Type your question
3. Press Enter or click Send
4. View response

### Features

- **Persistent** - Stays open across pages
- **Context Aware** - Knows your workspace, directory, current test
- **Message History** - Messages persist across refreshes
- **Token Tracking** - Shows remaining tokens

### Example Queries

- "How do I create a login test?"
- "What actions are available for API testing?"
- "Help me fix this error: [paste error]"
- "Show me examples of form submission"
- "What's the best way to handle waits?"

---

## Variables & Environments

### Variable Types

1. **Test Variables** - Defined in test file
2. **Environment Variables** - Shared across tests
3. **Collection Variables** - Workspace-specific
4. **Suite Variables** - Suite-specific

### Creating Variables

1. Go to **Variables**
2. Select variable type
3. Click **Create**
4. Enter name and value
5. Save

### Using Variables

```yaml
variables:
  api_url: ${env.api_url}
  workspace_var: ${collection.my_var}
  suite_var: ${suite.config}
```

### Variable Resolution

Variables are resolved in this order:
1. Test variables
2. Suite variables
3. Collection variables
4. Environment variables

---

## Best Practices

### Test Organization

- Use workspaces to organize tests
- Use tags for categorization
- Keep test names descriptive
- Group related tests in suites

### Test Design

- Keep tests focused and atomic
- Use variables for reusable values
- Add descriptions to steps
- Use setup/cleanup for common tasks

### Maintenance

- Review metrics regularly
- Update stale tests
- Fix flaky tests promptly
- Keep test data current

### Performance

- Use headless mode for CI/CD
- Group tests in suites for efficiency
- Use data-driven testing for variations
- Monitor execution times

---

## Troubleshooting

### Test Builder Not Starting

```bash
# Check dependencies
cd frontend
pip install -r requirements_builder.txt

# Check port availability
# Try different port: python start_builder.py --port 8001
```

### Tests Not Running

- Check test file syntax (YAML)
- Verify all required parameters are filled
- Check browser is installed: `playwright install chromium`
- Review error messages in execution logs

### AI Assistant Not Working

- Verify API key is configured
- Check token quota hasn't been exceeded
- Ensure chat panel is open
- Check browser console for errors

### Metrics Not Loading

- Ensure test results exist
- Try different time period
- Refresh page
- Check browser console

### Common Issues

**Issue: "File not found"**
- Verify test file path is correct
- Check file exists in tests directory
- Ensure file has .yaml extension

**Issue: "Action not found"**
- Check action name spelling
- Verify action is available in Actions Library
- Review action documentation

**Issue: "Variable not resolved"**
- Check variable name spelling
- Verify variable is defined
- Check variable scope (test/suite/collection/env)

---

## Additional Resources

- [New Features Guide](NEW_FEATURES.md) - Latest features and improvements
- [Test Builder Guide](TEST_BUILDER.md) - Detailed Test Builder documentation
- [Syntax Cheat Sheet](SYNTAX_CHEATSHEET.md) - Quick action reference
- [API Reference](API_REFERENCE.md) - REST API documentation
- [Examples](examples.md) - Real-world test examples
- [Troubleshooting Guide](troubleshooting.md) - Common issues and solutions

---

## Getting Help

1. **Check Documentation** - Review relevant guides
2. **Use AI Assistant** - Ask questions in the chat
3. **View Examples** - Check demo tests and examples
4. **Review Metrics** - Identify patterns in test failures
5. **Check Logs** - Review execution logs for details

For more help, see the [Troubleshooting Guide](troubleshooting.md) or open an issue on GitHub.

