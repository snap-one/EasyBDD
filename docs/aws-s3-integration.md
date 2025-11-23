# AWS S3 Integration

**Access firmware files, extract versions, and manage S3 operations from your tests**

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [AWS Credentials](#aws-credentials)
4. [Available Actions](#available-actions)
5. [Examples](#examples)
6. [Best Practices](#best-practices)

---

## Overview

The AWS S3 integration allows you to:

- **List firmware files** with intelligent version sorting
- **Download firmware** to your workspace
- **Extract latest versions** automatically
- **Upload files** to S3 buckets
- **Use CloudFront URLs** for faster downloads
- **Filter by patterns** (filename, version, extension)

All operations support AWS CLI credentials or explicit key/secret parameters.

---

## Quick Start

### List Firmware Files

```yaml
steps:
  - action: "AWS list firmware files"
    bucket_name: "firmware-703"
    folder_prefix: "wattbox/"
    filename_pattern: "wattbox"
    file_extension: ".bin"
    download_dir: "Firmware"
    store_as: "firmware_urls"
```

### Get Latest Firmware

```yaml
steps:
  - action: "AWS get latest firmware"
    bucket_name: "firmware-703"
    folder_prefix: "wattbox/"
    filename_pattern: "wattboxvps"
    file_extension: ".bin"
    download_dir: "Firmware"
    store_filename_as: "firmware_file"
    store_version_as: "firmware_version"
    store_url_as: "firmware_url"
  
  - action: "Assert"
    expression: "firmware_version is not None"
    message: "Should extract firmware version"
```

---

## AWS Credentials

### Priority Order

1. **Explicit parameters** in YAML (highest priority)
2. **Global configuration** via `configure_global_credentials`
3. **Environment variables** (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
4. **AWS CLI default profile** (lowest priority)

### Using AWS CLI (Recommended)

```bash
# Configure AWS CLI once
aws configure

# Your tests will automatically use these credentials
python -m easy_bdd run tests/cases/firmware_test.yaml
```

### Explicit Credentials in YAML

```yaml
variables:
  aws_access_key: "${env:AWS_ACCESS_KEY_ID}"
  aws_secret_key: "${env:AWS_SECRET_ACCESS_KEY}"
  aws_region: "us-east-1"

steps:
  - action: "AWS list firmware files"
    bucket_name: "firmware-703"
    access_key_id: "${aws_access_key}"
    secret_access_key: "${aws_secret_key}"
    region: "${aws_region}"
```

### Environment Variables

```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"

python -m easy_bdd run tests/cases/firmware_test.yaml
```

---

## Available Actions

### 1. AWS List Firmware Files

List and optionally download firmware files from S3.

**Parameters:**

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `bucket_name` | Yes | string | S3 bucket name |
| `folder_prefix` | No | string | Folder prefix to filter (e.g., "wattbox/") |
| `filename_pattern` | No | string | Pattern to match in filename |
| `version_pattern` | No | string | Regex pattern to match version |
| `file_extension` | No | string | File extension filter (e.g., ".bin") |
| `specific_version` | No | string/list | Specific version(s) to find |
| `cloudfront_url` | No | string | CloudFront URL to replace S3 URL |
| `cloudfront_filename_only` | No | boolean | Append only filename to CloudFront |
| `download_dir` | No | string | Download directory (default: "Firmware") |
| `protocol` | No | string | URL protocol (default: "https") |
| `store_as` | No | string | Variable name to store URL list |
| `access_key_id` | No | string | AWS Access Key ID |
| `secret_access_key` | No | string | AWS Secret Access Key |
| `region` | No | string | AWS Region |

**Example:**

```yaml
- action: "AWS list firmware files"
  bucket_name: "firmware-703"
  folder_prefix: "lumens/"
  filename_pattern: "LUM-420"
  file_extension: ".bin"
  specific_version: ["4.2.0", "4.2.1"]
  cloudfront_url: "d12345.cloudfront.net"
  download_dir: "Firmware/Lumens"
  store_as: "firmware_list"
```

### 2. AWS Get Latest Firmware

Get the latest (or second-to-last) firmware file with automatic version extraction.

**Parameters:**

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `bucket_name` | Yes | string | S3 bucket name |
| `folder_prefix` | No | string | Folder prefix to filter |
| `filename_pattern` | No | string | Pattern to match in filename |
| `version_pattern` | No | string | Regex to extract version |
| `file_extension` | No | string | File extension (default: ".bin") |
| `download_dir` | No | string | Download directory |
| `get_second_to_last` | No | boolean | Get second-to-last instead of latest |
| `store_filename_as` | No | string | Variable for filename |
| `store_version_as` | No | string | Variable for version |
| `store_url_as` | No | string | Variable for URL |
| `access_key_id` | No | string | AWS Access Key ID |
| `secret_access_key` | No | string | AWS Secret Access Key |
| `region` | No | string | AWS Region |

**Example:**

```yaml
- action: "AWS get latest firmware"
  bucket_name: "firmware-703"
  folder_prefix: "wattbox/"
  filename_pattern: "wattboxvps"
  file_extension: ".bin"
  download_dir: "Firmware"
  store_filename_as: "fw_file"
  store_version_as: "fw_version"
  store_url_as: "fw_url"

- action: "Print"
  message: "Latest firmware: ${fw_version}"
```

### 3. AWS Upload File

Upload a local file to S3.

**Parameters:**

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `bucket_name` | Yes | string | S3 bucket name |
| `local_file_path` | Yes | string | Path to local file |
| `s3_key` | No | string | S3 object key (default: filename) |
| `make_public` | No | boolean | Make file publicly readable (default: true) |
| `store_as` | No | string | Variable to store URL |
| `access_key_id` | No | string | AWS Access Key ID |
| `secret_access_key` | No | string | AWS Secret Access Key |
| `region` | No | string | AWS Region |

**Example:**

```yaml
- action: "AWS upload file"
  bucket_name: "test-results-bucket"
  local_file_path: "reports/test_report.html"
  s3_key: "reports/latest/test_report.html"
  make_public: true
  store_as: "report_url"
```

### 4. AWS Delete Folder

Delete all objects in an S3 folder (prefix).

**Parameters:**

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `bucket_name` | Yes | string | S3 bucket name |
| `folder_prefix` | Yes | string | Folder prefix to delete |
| `access_key_id` | No | string | AWS Access Key ID |
| `secret_access_key` | No | string | AWS Secret Access Key |
| `region` | No | string | AWS Region |

**Example:**

```yaml
- action: "AWS delete folder"
  bucket_name: "test-artifacts"
  folder_prefix: "old-builds/"
```

---

## Examples

### Example 1: Download Latest WattBox Firmware

```yaml
name: "Download Latest WattBox Firmware"
description: "Get the latest WattBox VPS firmware from S3"
tags: ["firmware", "wattbox", "s3"]

steps:
  - action: "AWS get latest firmware"
    bucket_name: "firmware-703"
    folder_prefix: "files/Vendor WATTBOX/"
    filename_pattern: "wattboxvps"
    file_extension: ".bin"
    version_pattern: "\\d+\\.\\d+\\.\\d+\\.\\d+"
    download_dir: "Firmware/WattBox"
    store_filename_as: "firmware_filename"
    store_version_as: "firmware_version"
    store_url_as: "firmware_url"
  
  - action: "Print"
    message: "Downloaded firmware ${firmware_version}"
  
  - action: "Assert"
    expression: "firmware_version is not None"
    message: "Should extract firmware version"
  
  - action: "Assert"
    expression: "'wattboxvps' in firmware_filename"
    message: "Should download correct firmware file"
```

### Example 2: List Specific Firmware Versions

```yaml
name: "Find Specific Firmware Versions"
description: "List firmware files for specific versions only"
tags: ["firmware", "s3", "version-filter"]

variables:
  target_versions:
    - "1.00.48"
    - "1.00.54"

steps:
  - action: "AWS list firmware files"
    bucket_name: "firmware-703"
    folder_prefix: "wattbox/"
    filename_pattern: "wattboxwifi"
    file_extension: ".bin"
    specific_version: "${target_versions}"
    download_dir: "Firmware/Specific"
    store_as: "firmware_urls"
  
  - action: "Print"
    message: "Found ${len(firmware_urls)} firmware files"
  
  - action: "Assert"
    expression: "len(firmware_urls) >= 2"
    message: "Should find both target versions"
```

### Example 3: CloudFront URL Generation

```yaml
name: "Generate CloudFront URLs"
description: "List firmware with CloudFront URLs for fast distribution"
tags: ["firmware", "s3", "cloudfront"]

steps:
  - action: "AWS list firmware files"
    bucket_name: "firmware-703"
    folder_prefix: "lumens/"
    filename_pattern: "LUM-420"
    file_extension: ".bin"
    cloudfront_url: "d12345abcdef.cloudfront.net"
    cloudfront_filename_only: false
    protocol: "https"
    store_as: "cdn_urls"
  
  - action: "Print"
    message: "CloudFront URLs: ${cdn_urls}"
```

### Example 4: Get Second-to-Last Firmware (Rollback)

```yaml
name: "Get Previous Firmware Version"
description: "Download second-to-last firmware for rollback testing"
tags: ["firmware", "rollback", "s3"]

steps:
  - action: "AWS get latest firmware"
    bucket_name: "firmware-703"
    folder_prefix: "wattbox/"
    filename_pattern: "wattboxvps"
    file_extension: ".bin"
    get_second_to_last: true
    download_dir: "Firmware/Rollback"
    store_filename_as: "rollback_file"
    store_version_as: "rollback_version"
  
  - action: "Print"
    message: "Rollback firmware: ${rollback_version}"
```

### Example 5: Upload Test Results

```yaml
name: "Upload Test Results to S3"
description: "Upload HTML report to S3 bucket"
tags: ["s3", "upload", "results"]

teardown:
  - action: "AWS upload file"
    bucket_name: "test-results"
    local_file_path: "reports/test_report.html"
    s3_key: "results/${test_name}_${timestamp}.html"
    make_public: true
    store_as: "result_url"
  
  - action: "Print"
    message: "Test results uploaded: ${result_url}"
```

### Example 6: Complete Firmware Workflow

```yaml
name: "Complete Firmware Download and Validation"
description: "Download firmware, validate version, and verify file"
tags: ["firmware", "complete", "workflow"]

variables:
  expected_min_version: "2.0.0.0"

steps:
  # Get latest firmware
  - action: "AWS get latest firmware"
    bucket_name: "firmware-703"
    folder_prefix: "wattbox/"
    filename_pattern: "wattboxvps"
    file_extension: ".bin"
    download_dir: "Firmware"
    store_filename_as: "fw_file"
    store_version_as: "fw_version"
    store_url_as: "fw_url"
  
  # Print firmware info
  - action: "Print"
    message: "Firmware: ${fw_file}"
  
  - action: "Print"
    message: "Version: ${fw_version}"
  
  - action: "Print"
    message: "URL: ${fw_url}"
  
  # Validate firmware
  - action: "Assert"
    expression: "fw_version is not None"
    message: "Firmware version should be extracted"
  
  - action: "Assert"
    expression: "fw_version >= expected_min_version"
    message: "Firmware version should be at least ${expected_min_version}"
  
  - action: "Assert"
    expression: "'.bin' in fw_file"
    message: "Firmware file should be .bin format"
```

---

## Best Practices

### 1. Use AWS CLI Credentials

```yaml
# No need to specify credentials if AWS CLI is configured
steps:
  - action: "AWS get latest firmware"
    bucket_name: "firmware-703"
    folder_prefix: "wattbox/"
```

### 2. Store Results in Variables

```yaml
steps:
  - action: "AWS get latest firmware"
    bucket_name: "firmware-703"
    store_version_as: "firmware_version"
  
  # Use in later steps
  - action: "Print"
    message: "Testing with firmware ${firmware_version}"
```

### 3. Use Specific Patterns

```yaml
# Be specific to avoid downloading unnecessary files
- action: "AWS list firmware files"
  bucket_name: "firmware-703"
  folder_prefix: "wattbox/"
  filename_pattern: "wattboxvps"  # Specific model
  file_extension: ".bin"           # Specific extension
  specific_version: "2.2.1.0"      # Specific version
```

### 4. Validate Downloaded Files

```yaml
steps:
  - action: "AWS get latest firmware"
    bucket_name: "firmware-703"
    store_filename_as: "fw_file"
  
  - action: "Assert"
    expression: "fw_file is not None"
    message: "Firmware file should be found"
  
  - action: "Assert"
    expression: "os.path.exists(f'Firmware/{os.path.basename(fw_file)}')"
    message: "Firmware file should be downloaded"
```

### 5. Use Version Filters

```yaml
# Find specific versions for regression testing
- action: "AWS list firmware files"
  bucket_name: "firmware-703"
  specific_version: ["1.00.48", "1.00.54", "2.0.0.0"]
  store_as: "test_firmwares"
```

### 6. CloudFront for Distribution

```yaml
# Use CloudFront for faster downloads in CI/CD
- action: "AWS list firmware files"
  bucket_name: "firmware-703"
  cloudfront_url: "d12345.cloudfront.net"
  cloudfront_filename_only: true
```

---

## Version Sorting

The AWS service uses **intelligent version-aware sorting**:

```
Files in S3:
- firmware_1.2.3.bin
- firmware_1.2.10.bin
- firmware_1.2.20.bin
- firmware_2.0.0.bin

Sorted correctly:
- firmware_1.2.3.bin
- firmware_1.2.10.bin
- firmware_1.2.20.bin
- firmware_2.0.0.bin

Not alphabetically:
- firmware_1.2.10.bin  ❌
- firmware_1.2.20.bin  ❌
- firmware_1.2.3.bin   ❌
- firmware_2.0.0.bin   ✓
```

The sorting automatically detects version patterns like:
- `1.2.3`
- `1.2.3.4`
- `1.2.3-4`
- `v2.0.0`

---

## Troubleshooting

### AWS Credentials Not Found

```
Error: Unable to locate credentials
```

**Solution:** Configure AWS CLI or set environment variables:

```bash
aws configure
# OR
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
```

### No Files Found

```
Warning: No files found matching criteria
```

**Solution:** Check your filters:

```yaml
- action: "AWS list firmware files"
  bucket_name: "firmware-703"
  folder_prefix: "correct/path/"  # Verify this exists
  filename_pattern: "exact-name"  # Case-sensitive
  file_extension: ".bin"          # Include the dot
```

### Version Not Extracted

```
Warning: Could not extract version from: filename.bin
```

**Solution:** Provide a custom version pattern:

```yaml
- action: "AWS get latest firmware"
  bucket_name: "firmware-703"
  version_pattern: "\\d+\\.\\d+\\.\\d+\\.\\d+"  # Escape backslashes in YAML
```

---

## Next Steps

- See [examples/](../tests/cases/) for complete test examples
- Read [API Authentication](api-authentication.md) for API testing
- Check [Assertions](assertions.md) for validation patterns
