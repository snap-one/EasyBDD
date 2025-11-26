# New Features Guide

This document covers the latest features added to the Easy BDD Framework. For general usage, see the [Main README](../README.md) and [Test Builder Guide](TEST_BUILDER.md).

## 📊 Metrics & Analytics with Time Period Filtering

The Metrics & Analytics dashboard now supports time-based filtering to analyze test performance over different periods.

### Available Time Periods

- **Last 7 Days** - Short-term analysis
- **Last 2 Weeks** - Bi-weekly trends
- **Last 3 Weeks** - Extended short-term view
- **Last Month** (30 days) - Default, monthly analysis
- **Last Quarter** (90 days) - Long-term trends

### How to Use

1. Navigate to **Metrics & Analytics** from the sidebar
2. Select a time period from the dropdown in the top-right corner
3. Metrics automatically reload with data filtered to the selected period
4. All metrics are recalculated based on the time period:
   - Most failing tests
   - Flaky tests
   - Execution trends
   - Failure rate trends
   - Peak hours
   - Slowest tests
   - Quick insights

### What Gets Filtered

- Test execution results within the selected time period
- Execution time trends
- Failure rate trends
- All health metrics (failing, flaky, stale tests)
- Quick insights and velocity metrics

**Note:** Test coverage metrics (by workspace, action type, complexity) are not time-filtered as they represent the current state of your test suite.

---

## 🤖 AI Assistant with Persistent Context

The AI Assistant is now persistent across all pages and maintains context about your workspace, directory, and current state.

### Features

- **Persistent Chat Panel** - Stays open when navigating between pages
- **Message History** - Chat messages persist across page refreshes
- **Context Awareness** - Automatically includes workspace, directory, current test, and view information
- **Auto-Updates** - Context updates automatically when you change views, workspaces, or tests

### How to Use

1. **Open AI Assistant** - Click the chat icon (💬) in the top-right toolbar
2. **Configure API Key** (First Time):
   - Go to **Settings** → **OpenAI Configuration**
   - Enter your OpenAI API key
   - Click **Save**
3. **Start Chatting** - Type your question or request in the chat input
4. **Navigate Freely** - The chat panel stays open as you navigate between pages

### Context Information

The AI Assistant automatically includes:

- **Current View** - Which page you're on (dashboard, tests, results, etc.)
- **Current Test** - If editing a test, includes test name, description, workspace, and step count
- **Workspace/Directory** - Current selected workspace or directory
- **Available Workspaces** - List of all available workspaces
- **Current Route** - Current page URL
- **Recent Errors** - Recent test failures for troubleshooting
- **Test Count** - Total number of tests in the system

### Example Queries

- "How do I create a test that logs into a website?"
- "What actions are available for API testing?"
- "Help me fix the failing test in my current workspace"
- "Show me examples of browser automation"
- "What's the best way to handle form submissions?"

### Token Management

- Free tier: 100,000 tokens per month
- Token usage is tracked and displayed in the chat panel
- Low token warnings appear when tokens are running low
- Token status updates automatically after each message

---

## ♻️ Rerun Tests from Results

You can now rerun tests directly from the test results pages without navigating away.

### How to Use

1. **From Results List**:
   - Navigate to **Test Results** from the sidebar
   - Find the test result you want to rerun
   - Click the **Re-run** button (🔄) on the result card

2. **From Results Preview**:
   - Click on a result card to open the preview panel
   - Click the **Re-run** button in the preview panel toolbar

3. **Execution**:
   - The test execution modal opens automatically
   - Progress is shown in real-time
   - New results appear in the results list when complete

### Use Cases

- Quickly rerun a failed test to verify a fix
- Re-execute a test with different data
- Verify test stability by running multiple times
- Debug intermittent failures

---

## ✏️ Edit Tests During Suite Creation/Editing

You can now edit individual tests while creating or editing a test suite without losing your suite context.

### How to Use

1. **While Creating/Editing a Suite**:
   - Click the **Edit** button (✏️) next to any test in the suite
   - The test opens in the Test Builder
   - Make your changes and click **Save**

2. **Return to Suite**:
   - After saving, you'll be prompted to return to suite editing
   - Click **Yes** to return to the suite
   - Your suite context is preserved

3. **Alternative Method**:
   - Use the **Back to Suite** button in the Test Builder header
   - This appears when editing a test from a suite

### Benefits

- No need to remember which suite you were editing
- Suite context is automatically preserved
- Changes to tests are immediately reflected in the suite
- Seamless workflow for test maintenance

---

## 🗺️ Routing and Page Refresh Support

The Test Builder now uses proper routing, so you can refresh pages without losing state or encountering errors.

### Features

- **URL-Based Navigation** - Each page has its own URL
- **State Persistence** - Page state is restored from the URL on refresh
- **Browser History** - Back/forward buttons work correctly
- **Deep Linking** - Share direct links to specific tests or suites

### Supported Routes

- `/` or `/dashboard` - Dashboard
- `/tests` - Test list
- `/tests/:id` - Specific test (e.g., `/tests/1234`)
- `/tests/new` - New test creation
- `/results` - Test results
- `/suites` - Test suites list
- `/suites/:id` - Specific suite
- `/actions` - Actions library
- `/templates` - Test templates
- `/docs` - Documentation
- `/variables` - Variable management
- `/metrics` - Metrics & Analytics
- `/settings` - Settings

### Benefits

- Refresh any page without errors
- Bookmark specific tests or suites
- Share links with team members
- Use browser back/forward navigation
- Better browser history tracking

---

## 🚨 Error Pages

Custom error pages are now available for common HTTP errors, providing a better user experience.

### Available Error Pages

- **404 Not Found** - Page or resource not found
- **400 Bad Request** - Invalid request format
- **401 Unauthorized** - Authentication required
- **403 Forbidden** - Access denied
- **500 Internal Server Error** - Server error
- **502 Bad Gateway** - Gateway error
- **503 Service Unavailable** - Service temporarily unavailable
- **504 Gateway Timeout** - Gateway timeout

### Features

- **User-Friendly Messages** - Clear error descriptions
- **Navigation Options** - "Go Home" and "Go Back" buttons
- **Consistent Design** - Matches the main application theme
- **Error Details** - Additional information when available (in debug mode)

### Testing Error Pages

You can test error pages using the test endpoints:

```bash
# Test 500 error
curl http://localhost:8000/api/test-error-500

# Test 503 error
curl http://localhost:8000/api/test-error-503

# Test 404 error
curl http://localhost:8000/api/test-error-404
```

Or use the provided test script:

```bash
cd frontend
python test_error_pages.py
```

---

## 📈 System Resource Auto-Detection

System resource monitoring has been improved to automatically detect and extract CPU, memory, disk, and network data from device updates.

### Features

- **Automatic Detection** - Resources are extracted automatically from device updates
- **OS-Agnostic** - Works with different device types and operating systems
- **Percentage Calculation** - Automatically calculates percentages from raw values
- **Multiple Pattern Matching** - Recognizes various resource naming conventions
- **Debug Logging** - Enable `DEBUG_RESOURCES=true` for verbose logging

### How It Works

1. When `ovrc.start device updates` is called, the system:
   - Starts receiving device update messages
   - Automatically extracts system resource data
   - Calculates percentages (CPU, memory, disk usage)
   - Stores results in variables for use in tests

2. Resource data is available in variables:
   - `${system_resources.cpu_percent}` - CPU usage percentage
   - `${system_resources.memory_percent}` - Memory usage percentage
   - `${system_resources.disk_percent}` - Disk usage percentage
   - `${system_resources.network}` - Network statistics

### Example Usage

```yaml
steps:
  - action: ovrc.start device updates
    description: Start receiving device updates
  
  - action: wait
    time: 10
    description: Wait for system resources to be collected
  
  - action: log
    message: "CPU Usage: ${system_resources.cpu_percent}%"
  
  - action: log
    message: "Memory Usage: ${system_resources.memory_percent}%"
```

---

## 🎬 Demo Test Cases and Test Suite

Demo test cases are now available to help you get started and demonstrate the framework's capabilities.

### Demo Test Suite

The **Demo Test Suite** includes three test cases:

1. **Demo UI Test** (`tests/cases/demo_ui_test.yaml`)
   - Simple browser automation
   - Form filling and submission
   - Screenshot capture
   - Text assertions

2. **Demo API Test** (`tests/cases/demo_api_test.yaml`)
   - REST API testing
   - GET, POST, PUT, DELETE requests
   - Response validation
   - Public API endpoints (no authentication required)

3. **Demo UI Advanced** (`tests/cases/demo_ui_advanced.yaml`)
   - Advanced browser interactions
   - Multiple form fields
   - Navigation testing
   - Browser back button

### How to Use

1. **View Demo Suite**:
   - Navigate to **Test Suites** from the sidebar
   - Find "Demo Test Suite" in the list
   - Click to view details

2. **Run Demo Suite**:
   - Click **Execute Suite** button
   - Watch tests execute in real-time
   - View results when complete

3. **Run Individual Tests**:
   - Navigate to **My Tests**
   - Find demo tests (prefixed with "Demo")
   - Click to open and run individually

### Benefits

- **No Setup Required** - Uses public websites and APIs
- **No Authentication** - Works out of the box
- **Comprehensive Examples** - Shows UI and API testing
- **Ready to Run** - Execute immediately
- **Learning Resource** - Study the test structure

---

## 🔄 Data Refresh and Cache-Busting

The Test Builder now ensures data is always up-to-date when navigating or refreshing pages.

### Features

- **Automatic Refresh** - Data reloads when accessing a page
- **Cache-Busting** - API requests include timestamps to prevent caching
- **Fresh Suite Data** - Suite details are reloaded from server
- **Real-Time Updates** - Changes are immediately reflected

### How It Works

- All GET requests to API endpoints include a timestamp parameter
- This prevents browsers from serving cached responses
- Data loading functions are called on every page access
- Suite data is explicitly reloaded when viewing suite details

### Benefits

- Always see the latest test data
- No stale information
- Changes are immediately visible
- Better collaboration experience

---

## 📝 Additional Improvements

### Test Loading Error Handling

- **Detailed Error Messages** - Clear indication of what went wrong
- **File Path Information** - Shows which file failed to load
- **Edit Helper** - Quick command to open the problematic file
- **Platform-Specific Commands** - Commands for macOS, Linux, and Windows

### Modal Interaction

- **Explicit Close Buttons** - All modals have clear close buttons
- **No Accidental Closes** - Modals don't close on backdrop click or Escape key
- **Better UX** - Prevents accidental data loss

### Test Results Improvements

- **Deduplication** - Duplicate results are automatically filtered
- **Unique Identification** - Results are identified by unique keys
- **Better Logging** - Basic and debug log views
- **Interactive Preview** - Click results to view details

---

## 🚀 Getting Started with New Features

### Quick Start Checklist

1. ✅ **Install Framework** - Follow the [Quick Start Guide](../README.md#-quick-start)
2. ✅ **Start Test Builder** - Run `python frontend/start_builder.py`
3. ✅ **Configure AI Assistant** - Go to Settings → OpenAI Configuration
4. ✅ **Explore Demo Tests** - Navigate to Test Suites → Demo Test Suite
5. ✅ **View Metrics** - Check Metrics & Analytics with different time periods
6. ✅ **Run a Test** - Execute a demo test and view results
7. ✅ **Rerun Tests** - Use the rerun button from results pages

### Next Steps

- Read the [Test Builder Guide](TEST_BUILDER.md) for detailed usage
- Check [Examples](examples.md) for real-world test patterns
- Review [Syntax Cheat Sheet](SYNTAX_CHEATSHEET.md) for action reference
- Explore [Metrics & Analytics](metrics-analytics.md) for insights

---

## 📚 Related Documentation

- [Test Builder Guide](TEST_BUILDER.md) - Complete Test Builder documentation
- [Metrics & Analytics](metrics-analytics.md) - Detailed metrics guide
- [API Reference](API_REFERENCE.md) - REST API documentation
- [Syntax Cheat Sheet](SYNTAX_CHEATSHEET.md) - Quick action reference
- [Main README](../README.md) - Framework overview and installation

---

## 💡 Tips and Best Practices

### AI Assistant

- Be specific in your questions for better responses
- Include context about what you're trying to achieve
- Use the assistant to learn about available actions
- Ask for help with error messages

### Metrics

- Use shorter periods (7 days) for recent issues
- Use longer periods (quarter) for trend analysis
- Compare different periods to identify patterns
- Check metrics regularly to catch issues early

### Test Reruns

- Rerun failed tests immediately after fixes
- Use rerun to verify test stability
- Check results after reruns to confirm fixes
- Document rerun patterns for flaky tests

### Suite Editing

- Edit tests from suites for quick fixes
- Use "Back to Suite" to maintain context
- Save test changes before returning to suite
- Verify suite reflects test changes

---

## 🐛 Troubleshooting

### AI Assistant Not Working

- Check OpenAI API key is configured in Settings
- Verify token quota hasn't been exceeded
- Check browser console for errors
- Ensure chat panel is open and visible

### Metrics Not Loading

- Check that test results exist for the selected period
- Try a different time period
- Refresh the page
- Check browser console for errors

### Rerun Not Working

- Verify test file still exists
- Check test path is correct
- Ensure test is valid YAML
- Check execution logs for errors

### Routing Issues

- Clear browser cache
- Check URL is correct
- Use navigation buttons instead of direct URL entry
- Refresh the page

---

For more help, see the [Troubleshooting Guide](troubleshooting.md) or open an issue on GitHub.

