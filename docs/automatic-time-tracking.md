# Automatic Time Tracking & Datalake Integration

The Easy BDD Framework now automatically tracks test execution time and posts metrics to your datalake after every test run. This happens seamlessly in the background without requiring any additional configuration in your test files.

## 📊 What Gets Tracked

Every test execution automatically captures:

- **Test Name**: Name of the test that was executed
- **Start Time**: Exact datetime when test began
- **End Time**: Exact datetime when test completed
- **Total Time**: Duration of test execution in seconds
- **Time Savings**: Expected time savings from automation (configurable)
- **Success Status**: Whether test passed or failed
- **Console Output**: Complete test execution log
- **Product Info**: Product being tested (from test variables)
- **MAC Address**: Device identifier (from test variables)

## 🔄 How It Works

### Automatic Capture

The test runner automatically:
1. Records start time at the beginning of each test
2. Captures all console output during execution
3. Tracks test success/failure status
4. Posts metrics to datalake at the end

### No Code Changes Required

Time tracking works automatically for:
- ✅ Single test execution
- ✅ Sequential data iterations (loops)
- ✅ Async/parallel data iterations
- ✅ Tests with setup and cleanup phases

## 📝 Configuration

### Test Variables

To provide accurate metrics, add these optional variables to your test definitions:

```yaml
name: "My Automated Test"
description: "Test that saves time"
variables:
  # Datalake metadata (all optional with defaults)
  product: "MyProduct"              # Default: "Unknown"
  product_category: "Integration"    # Default: "Test"
  mac_address: "AA:BB:CC:DD:EE:FF"  # Default: "00:00:00:00:00:00"
  time_savings: 10.0                 # Default: 5.0 (minutes)
  
  # Your test-specific variables
  username: "testuser"
  password: "testpass"

steps:
  - action: "Open browser"
    url: "https://example.com"
  # ... rest of your test steps
```

### Time Savings Calculation

The `time_savings` variable represents **how many minutes** this automated test saves compared to manual testing.

#### For Single Tests
```yaml
variables:
  time_savings: 5.0  # This test saves 5 minutes per execution
```

#### For Looped Tests
Time savings **multiplies** for each iteration:

```yaml
variables:
  time_savings: 3.0  # 3 minutes per iteration

data:
  - username: "user1"
  - username: "user2"
  - username: "user3"
  - username: "user4"
  - username: "user5"

# Total time savings: 3 minutes × 5 iterations = 15 minutes
```

#### For Extended/Stress Tests
```yaml
variables:
  time_savings: 2.0  # 2 minutes per iteration

data_source: "users.csv"  # 100 users
async_execution: true
max_workers: 10

# Total time savings: 2 minutes × 100 iterations = 200 minutes (3.3 hours)
```

## 📈 Data Iterations & Time Tracking

### Sequential Iterations

Time tracking works automatically for sequential loops:

```yaml
name: "User Login Test"
variables:
  time_savings: 4.0
  
data:
  - username: "user1"
    password: "pass1"
  - username: "user2"
    password: "pass2"
  - username: "user3"
    password: "pass3"

steps:
  - action: "Open browser"
    url: "https://example.com/login"
  - action: "Fill field"
    selector: "#username"
    value: "${username}"
  - action: "Fill field"
    selector: "#password"
    value: "${password}"
  - action: "Click element"
    selector: "#login-button"
```

**Result**: Each iteration posts metrics separately with cumulative time savings.

### Async/Parallel Iterations

Time tracking captures actual execution time for parallel tests:

```yaml
name: "Parallel Load Test"
variables:
  time_savings: 2.0
  
async_execution: true
max_workers: 5

data:
  - user_id: 1
  - user_id: 2
  - user_id: 3
  - user_id: 4
  - user_id: 5
  - user_id: 6
  - user_id: 7
  - user_id: 8
  - user_id: 9
  - user_id: 10

steps:
  - action: "Make API request"
    url: "https://api.example.com/user/${user_id}"
    method: "GET"
```

**Result**: 
- 10 tests run in parallel (5 at a time)
- Each posts its own metrics
- Total time savings: 2 × 10 = 20 minutes
- Actual execution time: ~4 minutes (due to parallelization)

## 🎯 Use Cases

### 1. Manual Regression Suite

```yaml
name: "Full Regression Suite"
description: "Tests entire application workflow"
variables:
  product: "WebApp"
  product_category: "Regression"
  time_savings: 45.0  # Manual testing takes 45 minutes

steps:
  # ... 30 test steps covering full workflow
```

### 2. Device Testing Loop

```yaml
name: "Multi-Device Test"
variables:
  product: "IoT Device"
  product_category: "Hardware"
  time_savings: 10.0  # 10 minutes per device manually

data:
  - mac_address: "00:11:22:33:44:55"
    device_name: "Device 1"
  - mac_address: "00:11:22:33:44:56"
    device_name: "Device 2"
  - mac_address: "00:11:22:33:44:57"
    device_name: "Device 3"
  # ... more devices

# Total savings: 10 × number of devices
```

### 3. API Load Testing

```yaml
name: "API Stress Test"
variables:
  product: "API Server"
  product_category: "Performance"
  time_savings: 1.0  # Small per-iteration time

async_execution: true
max_workers: 20

data_source: "test_data.csv"  # 1000 rows

# Total savings: 1 × 1000 = 1000 minutes (16.7 hours)
```

## 📊 Datalake Metrics Format

The framework posts this JSON structure to your datalake:

```json
{
  "test_name": "User Login Test",
  "product": "MyProduct",
  "product_category": "Integration",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "start_time": "2024-01-15T10:30:00",
  "end_time": "2024-01-15T10:32:30",
  "total_time": 150.5,
  "time_savings": 5.0,
  "success": true,
  "type": "testrail",
  "parameters": {
    "console": "... captured test output ...",
    "testrail": {
      "run_url": ""
    }
  }
}
```

## 🔧 Advanced Configuration

### Custom Datalake Endpoint

The datalake configuration is in `easy_bdd/core/datalake_logger.py`:

```python
# Default configuration
DATALAKE_ENDPOINT = "https://jpdsauto.snapone.com/publish"
API_KEY = "FiORf06Q3g6m6dEigH8YE85BANHKaHnA3FRBxlON"
```

### Disable Datalake Posting

To run tests without posting to datalake:

```python
# In runner.py, set post_results=False
datalake_logger = DatalakeLogger(
    artifact_path="reports",
    post_results=False  # Disable datalake posting
)
```

### Console Output Capture

The framework automatically captures all test output including:
- Step execution logs
- Success/failure messages
- Error messages and tracebacks
- Setup and cleanup logs
- Video recording notifications

## 📋 Example Output

When a test runs, you'll see:

```
Executing test 1/1: User Login Test
    === Setup Phase ===
    Setup 1/1: Open browser
           → Navigate to https://example.com/login
    ✅ Step 1 completed successfully
    === Main Test Phase ===
    Step 1/3: Fill field
           → Fill #username with testuser
    ✅ Step 1 completed successfully
    Step 2/3: Fill field
           → Fill #password with ••••••••
    ✅ Step 2 completed successfully
    Step 3/3: Click element
           → Click #login-button
    ✅ Step 3 completed successfully
    === Cleanup Phase ===
    Cleanup 1/1: Close browser
    ✅ Step 1 completed successfully
    📊 Test metrics posted to datalake
  ✅ PASSED: User Login Test
```

## 🎓 Best Practices

### 1. Accurate Time Savings

Estimate time savings based on **actual manual testing time**:
- ✅ Include setup time (opening apps, navigating)
- ✅ Include execution time (filling forms, clicking buttons)
- ✅ Include verification time (checking results)
- ✅ Include cleanup time (closing apps, resetting state)

### 2. Product Categorization

Use consistent product categories:
- `Regression` - Full workflow tests
- `Smoke` - Quick sanity checks
- `Integration` - Multi-system tests
- `Performance` - Load/stress tests
- `Unit` - Component-level tests

### 3. Device Identification

For hardware/IoT testing:
- Use actual MAC addresses when testing devices
- Use placeholder MAC for simulation tests
- Include device info in test name or variables

### 4. Extended Test Runs

For long-running tests with many iterations:
- Set realistic `time_savings` per iteration
- Use `async_execution` to reduce actual execution time
- Monitor datalake for cumulative time savings

## 🐛 Troubleshooting

### Metrics Not Posted

If you see `⚠️ Datalake posting error`:

1. **Check network connectivity**:
   ```bash
   curl -X PUT https://jpdsauto.snapone.com/publish
   ```

2. **Verify API key** in `datalake_logger.py`

3. **Check test variables** are valid (no special characters)

### Inaccurate Time Tracking

If execution time seems wrong:
- Check for `time.sleep()` delays in test steps
- Verify browser loading times
- Check network latency for API tests
- Review video recording overhead

### Missing Console Output

If console output is empty:
- Ensure all print statements are in test execution phase
- Check for exceptions during test execution
- Verify stdout redirection is working

## 📚 Related Documentation

- [Datalake Logger Guide](datalake-logger.md) - Complete logging system documentation
- [Data-Driven Testing](data-driven.md) - Using data iterations
- [Device Configuration](DEVICE_AGNOSTIC_SETUP.md) - Multi-device testing setup
- [Custom Assertions](assertions.md) - Advanced test validation
