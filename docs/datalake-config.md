# Datalake Logging Configuration

## Overview

The Easy BDD Framework supports configurable datalake logging for test metrics and results. You can control whether tests are logged, and optionally only log failures for debugging purposes.

## Configuration Options

Add the following to your `config/framework.yaml`:

```yaml
config:
  # Datalake logging configuration
  datalake:
    enabled: true  # Set to false to disable all datalake logging
    post_on_failure_only: false  # Set to true to only log failed tests
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | `true` | Master switch for datalake logging. Set to `false` to completely disable all datalake posts |
| `post_on_failure_only` | boolean | `false` | When `true`, only failed tests are posted to the datalake. Useful for debugging |

## Use Cases

### 1. Disable All Datalake Logging (Development/Debugging)

```yaml
datalake:
  enabled: false
  post_on_failure_only: false
```

**Output:**
```
⏭️  Datalake logging disabled
```

**Use when:**
- Running tests locally during development
- Debugging test issues
- Running tests that shouldn't be tracked
- Avoiding pollution of datalake with test runs

### 2. Only Log Failures (Troubleshooting)

```yaml
datalake:
  enabled: true
  post_on_failure_only: true
```

**Output for passed tests:**
```
⏭️  Skipping datalake post (test passed, failure-only mode)
```

**Output for failed tests:**
```
📊 Test metrics posted to datalake
```

**Use when:**
- Investigating failures in production
- Reducing datalake noise during large test runs
- Focusing on problematic tests only

### 3. Log All Tests (Production/Default)

```yaml
datalake:
  enabled: true
  post_on_failure_only: false
```

**Output:**
```
📊 Test metrics posted to datalake
```

**Use when:**
- Running CI/CD pipelines
- Tracking all test metrics
- Production test runs
- Building historical data

## Quick Disable Methods

### Method 1: Edit Config File

Edit `config/framework.yaml`:
```yaml
datalake:
  enabled: false
```

### Method 2: Temporary Override (Command Line)

You can also set environment variables (if supported in future versions):
```bash
export EASYBDD_DATALAKE_ENABLED=false
```

### Method 3: Per-Test Disable

To disable for specific tests, you can add test-level configuration (planned feature).

## Examples

### Full Configuration Example

```yaml
config:
  browser:
    default: "chrome"
    headless: false
  
  reporting:
    output_dir: "reports"
    screenshots: true
    html_report: true
  
  # Datalake configuration
  datalake:
    enabled: true
    post_on_failure_only: false
  
  parallel:
    workers: 2
```

### Development Mode Configuration

```yaml
config:
  browser:
    headless: true  # Run headless during dev
  
  datalake:
    enabled: false  # Don't log dev runs
  
  reporting:
    output_dir: "reports"
```

### CI/CD Configuration

```yaml
config:
  browser:
    headless: true
  
  datalake:
    enabled: true
    post_on_failure_only: false  # Log everything in CI
  
  reporting:
    output_dir: "reports"
```

## Console Output Reference

| Setting | Passed Test Output | Failed Test Output |
|---------|-------------------|-------------------|
| `enabled: false` | `⏭️  Datalake logging disabled` | `⏭️  Datalake logging disabled` |
| `enabled: true, post_on_failure_only: true` | `⏭️  Skipping datalake post (test passed, failure-only mode)` | `📊 Test metrics posted to datalake` |
| `enabled: true, post_on_failure_only: false` | `📊 Test metrics posted to datalake` | `📊 Test metrics posted to datalake` |

## Troubleshooting

### Datalake Still Logging When Disabled

1. Check your config file path:
   ```bash
   cat config/framework.yaml | grep -A 3 datalake
   ```

2. Verify the YAML syntax is correct (proper indentation)

3. Restart your test session

### Configuration Not Taking Effect

The configuration is loaded at test runtime. Make sure:
- The `config/framework.yaml` file exists
- YAML syntax is valid
- The file has proper indentation (2 spaces)
- You're running tests from the workspace root

## See Also

- [Test Metrics & Automatic Time Tracking](./automatic-time-tracking.md)
- [Configuration Guide](./setup.md)
- [Reporting Options](./EXPORT_RESULTS.md)
