# Long-Running Tests Guide

This guide covers how the Easy BDD Framework handles long-running tests (tests that run for hours or even days).

## ✅ What Works Out of the Box

### Test Execution
- **No hard timeouts** - The test runner itself has no maximum execution time limit
- **Process management** - Tests run as subprocesses and can run indefinitely
- **Output streaming** - Real-time output is captured and streamed throughout execution
- **Result storage** - Results are saved even if the test runs for hours

### Browser Sessions
- **Playwright/Selenium** - Browser sessions can remain open for extended periods
- **Session persistence** - Browser contexts stay alive throughout the test
- **Memory management** - Browser services handle cleanup automatically

### Backend
- **Async execution** - Tests run in background tasks that don't block
- **WebSocket streaming** - Real-time output is broadcast to connected clients
- **Status tracking** - Test status is tracked throughout execution

## ⚠️ Current Limitations & Solutions

### 1. Frontend Polling (Fixed)
**Previous Issue:** Frontend stopped polling after 10 minutes  
**Status:** ✅ **FIXED** - Now supports up to 10 hours of polling

**What Changed:**
- Polling timeout increased from 10 minutes to 10 hours
- Supports tests up to 9 hours with headroom

### 2. Async Iteration Timeout (Fixed)
**Previous Issue:** Async data iterations had a 2-minute timeout  
**Status:** ✅ **FIXED** - Now supports up to 10 hours per iteration

**What Changed:**
- Iteration timeout increased from 2 minutes to 10 hours
- Each data iteration can now run for extended periods

### 3. Memory Management
**Consideration:** Long-running browser sessions can consume significant memory

**Recommendations:**
```yaml
# Add periodic cleanup steps in long-running tests
steps:
  - action: browser.open
    url: https://example.com
  
  # ... long-running operations ...
  
  # Periodic cleanup (every few hours)
  - action: log
    message: "Performing periodic cleanup"
  
  # Take screenshots periodically instead of keeping browser open
  - action: browser.take_screenshot
    name: "progress_checkpoint_1"
  
  # Continue with test...
```

### 4. WebSocket Connections
**Consideration:** Browser tabs may disconnect WebSocket after inactivity

**Solution:**
- Results are still saved to files even if WebSocket disconnects
- You can check test status via the API: `GET /api/tests/execution/{test_id}`
- Results are available in the Results page after completion

## 📋 Best Practices for Long-Running Tests

### 1. Add Checkpoints
```yaml
name: "Long Running Test"
description: "Test that runs for 9 hours"

steps:
  - action: log
    message: "Starting 9-hour test at checkpoint 1"
  
  - action: browser.open
    url: https://example.com
  
  # ... operations ...
  
  - action: log
    message: "Checkpoint 2 - 3 hours elapsed"
  
  - action: browser.take_screenshot
    name: "checkpoint_3h"
  
  # ... more operations ...
  
  - action: log
    message: "Checkpoint 3 - 6 hours elapsed"
  
  - action: browser.take_screenshot
    name: "checkpoint_6h"
  
  # ... final operations ...
  
  - action: log
    message: "Test completed - 9 hours elapsed"
```

### 2. Use Variables for Time Tracking
```yaml
variables:
  start_time: "${datetime.now()}"
  expected_duration_hours: 9

steps:
  - action: log
    message: "Test started at ${start_time}, expected duration: ${expected_duration_hours} hours"
  
  # ... long-running operations ...
  
  - action: log
    message: "Progress update - continuing test execution"
```

### 3. Monitor Resource Usage
```yaml
# Add system resource checks periodically
steps:
  - action: log
    message: "Checking system resources"
  
  # If using OvrC device monitoring
  - action: ovrc.start device updates
    store_as: device_status
  
  - action: wait
    time: 5
  
  # Log resource usage
  - action: log
    message: "CPU: ${device_status.cpu_percent}%, Memory: ${device_status.memory_percent}%"
```

### 4. Handle Interruptions Gracefully
```yaml
# Use try-catch equivalent with conditional steps
steps:
  - action: browser.open
    url: https://example.com
  
  # Long-running operation with error handling
  - action: browser.wait_for_selector
    selector: ".completion-indicator"
    timeout: 32400000  # 9 hours in milliseconds (9 * 60 * 60 * 1000)
  
  # If operation completes, continue
  - action: browser.assert_text_contains
    selector: ".completion-indicator"
    text: "Complete"
```

### 5. Save Progress Periodically
```yaml
steps:
  # Initial setup
  - action: browser.open
    url: https://example.com
  
  # Save state every hour
  - action: log
    message: "Hour 1 - Saving progress"
  - action: browser.take_screenshot
    name: "progress_hour_1"
  
  - action: wait
    time: 3600  # Wait 1 hour
  
  - action: log
    message: "Hour 2 - Saving progress"
  - action: browser.take_screenshot
    name: "progress_hour_2"
  
  # Continue pattern...
```

## 🔍 Monitoring Long-Running Tests

### Via Web UI
1. **Test Results Page** - Shows test status and progress
2. **Real-time Output** - View live output during execution (if WebSocket connected)
3. **Execution Status API** - Check status programmatically

### Via API
```bash
# Check test execution status
curl http://localhost:8000/api/tests/execution/{test_id}

# Response includes:
{
  "status": "running",
  "started": "2024-01-01T10:00:00",
  "output": [...],  # All output lines
  "progress": 50  # If available
}
```

### Via Command Line
```bash
# Run test in background and monitor
nohup python -m easybdd run tests/cases/long_test.yaml > test.log 2>&1 &

# Monitor progress
tail -f test.log

# Check if still running
ps aux | grep easybdd
```

## 🚨 Troubleshooting

### Test Stops Unexpectedly
**Possible Causes:**
- System resource limits (memory, CPU)
- Browser session timeout (rare)
- Network interruptions

**Solutions:**
- Check system resources: `htop` or Activity Monitor
- Review test logs for error messages
- Add more frequent checkpoints
- Consider breaking into smaller tests

### Frontend Shows "Test Not Running"
**Cause:** WebSocket disconnected or polling stopped

**Solution:**
- Test is still running in background
- Check API: `GET /api/tests/execution/{test_id}`
- Results will appear when test completes

### Memory Issues
**Symptoms:** High memory usage, system slowdown

**Solutions:**
```yaml
# Add cleanup steps
cleanup:
  - action: browser.close
  - action: log
    message: "Cleaning up resources"
```

Or break the test into smaller chunks:
```yaml
# Instead of one 9-hour test, use multiple shorter tests
# Test 1: Hours 0-3
# Test 2: Hours 3-6  
# Test 3: Hours 6-9
```

## 📊 Performance Considerations

### Browser Memory
- **Playwright**: ~100-200MB per browser instance
- **Selenium**: ~150-300MB per browser instance
- **Recommendation**: Close and reopen browser if test exceeds 6 hours

### System Resources
- **CPU**: Minimal when browser is idle
- **Memory**: Grows with browser session duration
- **Disk**: Screenshots and videos can accumulate

### Network
- **WebSocket**: May disconnect after extended inactivity
- **HTTP**: More reliable for long connections
- **Recommendation**: Use periodic "heartbeat" actions

## ✅ Summary

The framework **fully supports** long-running tests up to 9+ hours:

- ✅ No execution time limits
- ✅ Extended polling support (10 hours)
- ✅ Extended iteration timeouts (10 hours)
- ✅ Real-time output streaming
- ✅ Result persistence
- ✅ Background execution

**Best Practices:**
1. Add periodic checkpoints and screenshots
2. Monitor resource usage
3. Handle errors gracefully
4. Consider breaking into smaller tests if memory becomes an issue
5. Use the API to check status if WebSocket disconnects

