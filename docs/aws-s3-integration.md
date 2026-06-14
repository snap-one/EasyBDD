# AWS S3 Integration

**Access firmware files, extract versions, and manage S3 operations from your tests**

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [AWS Credentials](#aws-credentials)
4. [Available Actions](#available-actions)
5. [Auto-Discovery of Folder Prefix](#auto-discovery-of-folder-prefix)
6. [Examples](#examples)
7. [Best Practices](#best-practices)

---

## Overview

The AWS S3 integration allows you to:

- **List firmware files** with intelligent version sorting
- **Download firmware** to your workspace
- **Extract latest versions** automatically
- **Upload files** to S3 buckets
- **Use CloudFront URLs** for faster downloads
- **Filter by patterns** (filename, version, extension)
- **Auto-discover folder prefixes** without hardcoding S3 paths

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

### Auto-Discover Prefix (No Hardcoded Path)

```yaml
steps:
  - action: aws.list_files
    bucket_name: jpdsauto-wattbox
    filename_pattern: wattboxvps
    discover_prefix: true
    store_as: firmware_urls
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
| `folder_prefix` | No | string | Folder prefix to filter (e.g., "wattbox/"). Must be a string, not a list — see warning below. |
| `filename_pattern` | No | string | Pattern to match in filename |
| `version_pattern` | No | string | Regex pattern to match version |
| `file_extension` | No | string | File extension filter (e.g., ".bin") |
| `specific_version` | No | string/list | Specific version(s) to find |
| `cloudfront_url` | No | string | CloudFront URL to replace S3 URL |
| `cloudfront_filename_only` | No | boolean | Append only filename to CloudFront |
| `download_dir` | No | string | Download directory (default: "Firmware") |
| `protocol` | No | string | URL protocol (default: "https") |
| `store_as` | No | string | Variable name to store URL list |
| `discover_prefix` | No | boolean | Auto-discover folder prefix when `folder_prefix` is not set (default: false) |
| `repo_root` | No | string | Root directory for local repo walk during prefix discovery (default: current working dir) |
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
| `folder_prefix` | No | string | Folder prefix to filter. Must be a string, not a list — see warning below. |
| `filename_pattern` | No | string | Pattern to match in filename |
| `version_pattern` | No | string | Regex to extract version |
| `file_extension` | No | string | File extension (default: ".bin") |
| `download_dir` | No | string | Download directory |
| `get_second_to_last` | No | boolean | Get second-to-last instead of latest |
| `store_filename_as` | No | string | Variable for filename |
| `store_version_as` | No | string | Variable for version |
| `store_url_as` | No | string | Variable for URL |
| `discover_prefix` | No | boolean | Auto-discover folder prefix when `folder_prefix` is not set (default: false) |
| `repo_root` | No | string | Root directory for local repo walk during prefix discovery (default: current working dir) |
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

## Auto-Discovery of Folder Prefix

When you do not know the exact S3 folder path ahead of time — or want tests that remain stable even when bucket layout changes — set `discover_prefix: true` and omit `folder_prefix`. The framework will locate the correct prefix automatically.

### How It Works

Discovery is two-phase and stops as soon as a match is found:

**Phase 1 — Repo walk (fast)**

The framework walks the local directory tree starting at `repo_root` (defaults to the current working directory). It looks for any folder whose name contains `filename_pattern` (case-insensitive). When a match is found, the relative path from `repo_root` is returned immediately as the prefix — no S3 call is made.

**Phase 2 — S3 fallback**

If no local folder matches, the framework scans the S3 bucket recursively using `list_objects_v2` with `Delimiter='/'`, inspecting each common prefix for a file that matches `filename_pattern`. The first matching prefix is used.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `discover_prefix` | boolean | `false` | Enable auto-discovery. Has no effect when `folder_prefix` is also provided. |
| `repo_root` | string | cwd | Root directory for the repo walk in Phase 1. |

### Example

```yaml
- action: aws.list_files
  bucket_name: jpdsauto-wattbox
  filename_pattern: wattboxvps
  discover_prefix: true
  store_as: firmware_urls
```

No `folder_prefix` is set. The framework first checks the local repo for a directory containing `wattboxvps`, then falls back to scanning the S3 bucket if nothing is found locally.

### When to Use

- You do not know the bucket folder layout in advance.
- The folder path varies across environments or bucket configurations.
- You want to avoid maintaining hardcoded prefixes across multiple test files.

### Interaction with `folder_prefix`

If `folder_prefix` is explicitly provided, `discover_prefix` is ignored regardless of its value. Discovery only activates when `folder_prefix` is absent.

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

### Example 7: Auto-Discover Prefix

```yaml
name: "Download Firmware with Auto-Discovered Prefix"
description: "Let the framework find the correct S3 folder automatically"
tags: ["firmware", "wattbox", "s3", "discover-prefix"]

steps:
  - action: aws.list_files
    bucket_name: jpdsauto-wattbox
    filename_pattern: wattboxvps
    discover_prefix: true
    store_as: firmware_urls
  
  - action: "Print"
    message: "Found ${len(firmware_urls)} firmware files"
  
  - action: "Assert"
    expression: "len(firmware_urls) > 0"
    message: "Should find at least one firmware file"
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

### 7. Prefer `discover_prefix` Over Hardcoded Lists

When the folder path is uncertain, use `discover_prefix: true` rather than guessing or constructing a list of possible prefixes. The discovery mechanism handles both local and remote lookup cleanly and avoids the list-value bug described in Troubleshooting below.

---

## Version Sorting

The AWS service uses **intelligent version-aware sorting** with a semver fallback for files that do not contain 10-digit timestamps.

### Sorting rules

1. Files with a 10-digit timestamp in the name are sorted by timestamp descending (newest first).
2. Files without a timestamp are sorted by semantic version descending — so `4.7.0` comes before `4.6.1`.
3. Within version-sorted results, non-DM files sort before DM files of the same version.

```
Files in S3 (no timestamps):
- upgrade_moip_4.6.1.bin
- upgrade_moip_4.6.1-DM.bin
- upgrade_moip_4.7.0.bin
- upgrade_moip_4.7.0-DM.bin

Sorted result (version descending):
[0] upgrade_moip_4.7.0.bin      ← latest non-DM
[1] upgrade_moip_4.7.0-DM.bin   ← latest DM
[2] upgrade_moip_4.6.1.bin
[3] upgrade_moip_4.6.1-DM.bin
```

This means you can reliably index the result list:

```yaml
- aws.list_files:
    bucket_name: ${bucket_name}
    folder_prefix: moip/
    file_extension: .bin
    store_as: firmware_files

# firmware_files[0] = latest non-DM firmware (e.g., upgrade_moip_4.7.0.bin)
# firmware_files[1] = latest -DM firmware    (e.g., upgrade_moip_4.7.0-DM.bin)
- eval.run:
    expression: "firmware_files[0]"
    store_as: upgrade_file
- eval.run:
    expression: "firmware_files[1]"
    store_as: downgrade_file
```

Alternatively, use `next(...)` with a condition to be explicit:

```yaml
- eval.run:
    expression: "next((f for f in firmware_files if '-DM' not in f), None)"
    store_as: upgrade_file
- eval.run:
    expression: "next((f for f in firmware_files if '-DM' in f), None)"
    store_as: downgrade_file
```

### Classic version pattern examples

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

### WARNING: Do Not Set `folder_prefix` to a List

**Error:**

```
Invalid type for parameter Prefix, value: ['upgrade', 'dummy'], type: <class 'list'>, valid types: <class 'str'>
```

**Cause:** The AWS S3 API requires the `Prefix` parameter to be a plain string. If `folder_prefix` is set to a YAML list (e.g., `['upgrade', 'dummy']`) — whether typed directly or resolved from a variable that holds a list — the boto3 client will raise this error immediately.

**Wrong:**

```yaml
- action: "AWS list firmware files"
  bucket_name: "jpdsauto-wattbox"
  folder_prefix:
    - "upgrade"
    - "dummy"
```

**Correct — use `discover_prefix` instead:**

```yaml
- action: aws.list_files
  bucket_name: jpdsauto-wattbox
  filename_pattern: wattboxvps
  discover_prefix: true
  store_as: firmware_urls
```

Or, if you know the exact string prefix:

```yaml
- action: "AWS list firmware files"
  bucket_name: "jpdsauto-wattbox"
  folder_prefix: "upgrade/"
```

---

## Next Steps

- See [examples/](../tests/cases/) for complete test examples
- Read [API Authentication](api-authentication.md) for API testing
- Check [Assertions](assertions.md) for validation patterns
