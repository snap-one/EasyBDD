# Browser Configuration Guide

## Running Tests with Different Browser Options

### Headless Mode (No Browser Window)

Run tests without showing the browser window (faster, good for CI):

```bash
# Run headless
python -m easy_bdd run tests/cases/katalon_test.yaml --headless

# Explicit headless mode
python -m easy_bdd run tests/cases/ --headless

# Run all tests headless
python -m easy_bdd run --headless
```

### Headed Mode (Show Browser Window)

Run tests with visible browser window (good for debugging):

```bash
# Run with browser window visible (default)
python -m easy_bdd run tests/cases/katalon_test.yaml --headed

# Explicit headed mode
python -m easy_bdd run tests/cases/ --headed
```

### Ignore HTTPS Certificate Errors

For sites with self-signed certificates or internal sites:

```bash
# Ignore HTTPS certificate errors
python -m easy_bdd run tests/cases/katalon_test.yaml --ignore-https

# Combine with headless
python -m easy_bdd run tests/cases/ --headless --ignore-https

# Perfect for your internal site
python -m easy_bdd run tests/cases/katalon_test.yaml --headed --ignore-https
```

### Choose Browser

Specify which browser to use:

```bash
# Use Chrome (default)
python -m easy_bdd run tests/cases/ --browser chrome

# Use Firefox
python -m easy_bdd run tests/cases/ --browser firefox

# Use Edge
python -m easy_bdd run tests/cases/ --browser edge
```

### Combine Options

You can combine multiple options:

```bash
# Headless Chrome with HTTPS ignored
python -m easy_bdd run tests/cases/katalon_test.yaml --headless --browser chrome --ignore-https

# Headed Firefox with HTTPS ignored (for debugging)
python -m easy_bdd run tests/cases/katalon_test.yaml --headed --browser firefox --ignore-https
```

## Configuration File Options

You can also set defaults in `config/framework.yaml`:

```yaml
config:
  browser:
    default: "chrome"
    headless: false          # Set to true for headless by default
    headed: true            # Show browser window
    ignore_https_errors: true    # Ignore certificate errors
    ignore_certificate_errors: true
    window_size: [1920, 1080]
    timeout: 30
    args:                   # Additional browser arguments
      - "--ignore-certificate-errors"
      - "--ignore-ssl-errors"
      - "--disable-web-security"
      - "--allow-running-insecure-content"
```

## For Your Katalon Test Specifically

Your test uses `http://192.168.100.8` which is an internal IP. Here are the recommended commands:

### Development/Debugging (see what's happening)
```bash
python -m easy_bdd run tests/cases/katalon_test.yaml --headed --ignore-https
```

### CI/Automation (fast execution)
```bash
python -m easy_bdd run tests/cases/katalon_test.yaml --headless --ignore-https
```

### Convert and Run in One Command
```bash
# Convert your JSON and run with HTTPS ignored
python -m easy_bdd convert tests/cases/katalon_test.json
python -m easy_bdd run tests/cases/katalon_test_converted.yaml --headed --ignore-https
```

## Troubleshooting

### If browser doesn't start:
```bash
# Try with explicit browser
python -m easy_bdd run tests/cases/ --browser chrome --headed
```

### If HTTPS errors persist:
```bash
# Use maximum HTTPS bypass
python -m easy_bdd run tests/cases/ --ignore-https --headed
```

### For debugging XPath issues:
```bash
# Run headed to see element selection
python -m easy_bdd run tests/cases/katalon_test.yaml --headed --ignore-https
```

### CLI Help
```bash
# See all browser options
python -m easy_bdd run --help
```

The framework automatically handles:
- Certificate verification bypass
- Internal network access
- XPath selector execution
- Browser lifecycle management

Perfect for your internal testing environment at `192.168.100.8`!