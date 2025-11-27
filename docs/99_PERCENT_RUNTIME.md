# 99% Runtime Rate Guide

This guide explains how to achieve and maintain a 99% runtime rate with the Easy BDD Framework.

## 🎯 What is 99% Runtime?

99% runtime means the framework is executing tests **99% of the time**, with minimal downtime between test executions. This is achieved through:

- **Test Queue System** - Continuous queue of tests ready to execute
- **Automatic Retry** - Failed tests automatically retry
- **Health Monitoring** - System health checks and auto-recovery
- **Continuous Execution Mode** - Tests run continuously without gaps
- **Resource Management** - Optimal resource utilization

## 🚀 Quick Start

### 1. Navigate to Test Queue Page

Access the Test Queue management page from the sidebar navigation. The page provides a comprehensive UI for managing test execution, continuous execution, retries, and health monitoring.

**URL:** `http://localhost:8000/queue`

### 2. Enable Continuous Execution

**Via Web UI:**
1. Navigate to **Test Queue** from the sidebar
2. In the "Continuous Execution" card, click the **Enable** button
3. The status will update immediately to show "Tests run continuously"

**Via API:**
```bash
curl -X POST "http://localhost:8000/api/tests/continuous-execution?enabled=true"
```

### 3. Configure Automatic Retry

**Via Web UI:**
1. In the Test Queue page, scroll to the "Automatic Retry" card
2. Check **Enable Automatic Retries**
3. Configure:
   - **Max Retries**: Number of retry attempts (default: 3)
   - **Retry Delay**: Seconds between retries (default: 5)
   - **Retry on Test Failure**: Automatically retry failed tests
   - **Retry on Test Error**: Automatically retry errored tests
4. Changes are saved automatically

**Via API:**
```bash
curl -X PUT "http://localhost:8000/api/tests/retry-config" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "max_retries": 3,
    "retry_delay": 5,
    "retry_on_failure": true,
    "retry_on_error": true
  }'
```

### 4. Enable Health Monitoring

**Via Web UI:**
1. In the Test Queue page, scroll to the "Health Monitoring" card
2. Click the **Enable** button
3. Monitor real-time system status:
   - **System Status**: Healthy, Degraded, or Critical
   - **CPU Usage**: Current CPU percentage
   - **Memory Usage**: Current memory percentage
   - **Last Check**: Timestamp of last health check

**Via API:**
```bash
curl -X POST "http://localhost:8000/api/health/monitor?enabled=true"
```

### 5. Configure Max Concurrent Tests

**Via Web UI:**
1. In the Test Queue page, find "Max Concurrent Tests" in the Continuous Execution card
2. Enter a value between 1-10 in the number input
3. Click **Update** to save

**Via API:**
```bash
curl -X PUT "http://localhost:8000/api/tests/max-concurrent?max_tests=3"
```

### 6. Queue Tests

```bash
# Add tests to queue
curl -X POST "http://localhost:8000/api/tests/queue" \
  -H "Content-Type: application/json" \
  -d '{
    "test_path": "tests/cases/my_test.yaml",
    "headless": true
  }'
```

## 📋 Features

### Test Queue System

The queue system ensures tests execute continuously:

- **Automatic Processing** - Queue processor runs continuously
- **Priority Support** - Tests execute in queue order
- **Concurrent Execution** - Run multiple tests simultaneously
- **Queue Management** - Add, remove, and monitor queued tests

**API Endpoints:**
- `POST /api/tests/queue` - Add test to queue
- `GET /api/tests/queue` - Get queue status
- `DELETE /api/tests/queue/{test_id}` - Remove from queue

### Automatic Retry

Failed tests automatically retry to maximize success rate:

**Configuration:**
```json
{
  "enabled": true,
  "max_retries": 3,
  "retry_delay": 5,
  "retry_on_failure": true,
  "retry_on_error": true
}
```

**Features:**
- Configurable retry attempts
- Exponential backoff (optional)
- Separate retry logic for failures vs errors
- Automatic re-queuing on failure

**API Endpoints:**
- `PUT /api/tests/retry-config` - Update retry configuration
- `GET /api/tests/retry-config` - Get current configuration

### Health Monitoring

Monitor system health to maintain 99% runtime:

**Monitored Metrics:**
- CPU usage
- Memory usage
- Running test count
- Queue length
- System status (healthy/degraded/critical)

**API Endpoints:**
- `POST /api/health/monitor` - Enable/disable monitoring
- `GET /api/health/status` - Get current health status

### Continuous Execution Mode

Run tests continuously without gaps:

**Features:**
- Automatic queue processing
- Zero downtime between tests
- Automatic re-queuing of completed tests (optional)
- Resource-aware execution

**API Endpoints:**
- `POST /api/tests/continuous-execution` - Enable/disable
- `GET /api/tests/continuous-execution` - Get status

### Concurrent Execution

Run multiple tests simultaneously:

**Configuration:**
```bash
# Set max concurrent tests
curl -X PUT "http://localhost:8000/api/tests/max-concurrent?max_tests=3"
```

**Benefits:**
- Faster test execution
- Better resource utilization
- Higher throughput

## 📊 Monitoring 99% Runtime

### Check Queue Status

```bash
curl "http://localhost:8000/api/tests/queue"
```

**Response:**
```json
{
  "queue_length": 5,
  "currently_running": 2,
  "max_concurrent": 3,
  "continuous_execution": true,
  "queue": [
    {
      "test_id": "...",
      "test_path": "tests/cases/test1.yaml",
      "queued_at": "2024-01-01T10:00:00",
      "retry_count": 0
    }
  ]
}
```

### Check Health Status

```bash
curl "http://localhost:8000/api/health/status"
```

**Response:**
```json
{
  "enabled": true,
  "status": "healthy",
  "cpu_percent": 45.2,
  "memory_percent": 62.1,
  "running_tests": 2,
  "queued_tests": 5,
  "last_check": "2024-01-01T10:00:00"
}
```

### Check Continuous Execution Status

```bash
curl "http://localhost:8000/api/tests/continuous-execution"
```

## 🎯 Best Practices

### 1. Maintain Queue Depth

Keep the queue populated to ensure continuous execution:

```bash
# Add multiple tests to queue
for test in tests/*.yaml; do
  curl -X POST "http://localhost:8000/api/tests/queue" \
    -H "Content-Type: application/json" \
    -d "{\"test_path\": \"$test\", \"headless\": true}"
done
```

### 2. Configure Appropriate Retry Settings

```json
{
  "enabled": true,
  "max_retries": 3,        // Retry up to 3 times
  "retry_delay": 5,        // Wait 5 seconds between retries
  "retry_on_failure": true, // Retry on test failures
  "retry_on_error": true   // Retry on system errors
}
```

### 3. Monitor System Resources

Enable health monitoring and set alerts:

```bash
# Enable health monitoring
curl -X POST "http://localhost:8000/api/health/monitor?enabled=true"

# Check status periodically
watch -n 60 'curl -s http://localhost:8000/api/health/status | jq'
```

### 4. Optimize Concurrent Execution

Balance between speed and resource usage:

- **Low resources**: `max_concurrent = 1`
- **Medium resources**: `max_concurrent = 2-3`
- **High resources**: `max_concurrent = 4-5`

```bash
# Adjust based on system capacity
curl -X PUT "http://localhost:8000/api/tests/max-concurrent?max_tests=3"
```

### 5. Handle Long-Running Tests

For 9-hour tests, ensure queue can handle them:

- Set appropriate `max_concurrent` to avoid resource exhaustion
- Monitor memory usage during long tests
- Use health monitoring to detect issues

## 🔧 Configuration Examples

### Full 99% Runtime Setup

```bash
# 1. Enable continuous execution
curl -X POST "http://localhost:8000/api/tests/continuous-execution?enabled=true"

# 2. Configure retry
curl -X PUT "http://localhost:8000/api/tests/retry-config" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "max_retries": 3,
    "retry_delay": 5,
    "retry_on_failure": true,
    "retry_on_error": true
  }'

# 3. Set concurrent execution
curl -X PUT "http://localhost:8000/api/tests/max-concurrent?max_tests=3"

# 4. Enable health monitoring
curl -X POST "http://localhost:8000/api/health/monitor?enabled=true"

# 5. Queue tests
curl -X POST "http://localhost:8000/api/tests/queue" \
  -H "Content-Type: application/json" \
  -d '{"test_path": "tests/cases/test1.yaml", "headless": true}'
```

### Scheduled Test Execution

```bash
# Use cron to continuously add tests to queue
# Add to crontab:
*/5 * * * * curl -X POST "http://localhost:8000/api/tests/queue" -H "Content-Type: application/json" -d '{"test_path": "tests/cases/scheduled_test.yaml", "headless": true}'
```

## 📈 Measuring Runtime Rate

### Calculate Runtime Percentage

```
Runtime % = (Time Tests Running / Total Time) × 100
```

**Example:**
- Total time: 24 hours (86400 seconds)
- Tests running: 23.76 hours (85536 seconds)
- Runtime: 85536 / 86400 × 100 = **99%**

### Monitoring Tools

1. **Queue Status** - Check queue length and running tests
2. **Health Status** - Monitor system resources
3. **Test Results** - Track test execution times
4. **Metrics Dashboard** - View comprehensive analytics

## 🚨 Troubleshooting

### Queue Not Processing

**Problem:** Tests stuck in queue

**Solutions:**
1. Check continuous execution is enabled
2. Verify max_concurrent is set correctly
3. Check system resources (CPU/memory)
4. Review server logs for errors

### High Failure Rate

**Problem:** Many tests failing

**Solutions:**
1. Enable automatic retry
2. Increase retry attempts
3. Check test stability
4. Review error logs

### Resource Exhaustion

**Problem:** System running out of resources

**Solutions:**
1. Reduce max_concurrent
2. Enable health monitoring
3. Add resource cleanup steps
4. Monitor with health status API

### Tests Not Retrying

**Problem:** Failed tests not retrying

**Solutions:**
1. Verify retry config is enabled
2. Check retry_on_failure/retry_on_error settings
3. Ensure queue processor is running
4. Check retry_count in queue items

## ✅ Summary

To achieve 99% runtime:

1. ✅ **Enable Continuous Execution** - Tests run continuously
2. ✅ **Configure Automatic Retry** - Failed tests retry automatically
3. ✅ **Enable Health Monitoring** - Monitor system health
4. ✅ **Maintain Queue Depth** - Keep queue populated
5. ✅ **Optimize Concurrent Execution** - Balance speed and resources
6. ✅ **Monitor Metrics** - Track runtime percentage

**Result:** Framework executes tests 99% of the time with minimal downtime!

