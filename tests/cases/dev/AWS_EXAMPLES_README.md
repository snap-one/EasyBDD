# AWS S3 Example Tests

These examples demonstrate the AWS S3 integration for firmware management.

## ✅ What Works

The AWS S3 integration is **fully functional** and includes:

- ✅ List firmware files with filtering
- ✅ Get latest firmware with version extraction  
- ✅ Upload files to S3
- ✅ Delete S3 folders
- ✅ CloudFront URL generation
- ✅ Intelligent version sorting
- ✅ Automatic file downloads

## 🔧 Setup Required

### 1. Configure AWS Credentials

```bash
# Option 1: AWS CLI (Recommended)
aws configure

# Option 2: Environment Variables
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"
```

### 2. Update Test Files

Each example test has placeholder values that need to be updated:

```yaml
variables:
  bucket_name: "your-firmware-bucket"  # ← Change to your bucket
  folder_prefix: "wattbox/"            # ← Update path
```

### 3. Install Dependencies

```bash
pip install boto3
```

## 📄 Example Tests

### `aws_s3_connection_test.yaml`
Simple test to verify setup - no real AWS calls

### `aws_s3_latest_firmware.yaml`
Download and validate the latest firmware file

**Requires:**
- Valid S3 bucket name
- Folder with firmware files (`.bin` extension)

### `aws_s3_list_firmware.yaml`
List multiple firmware files with version filtering

**Requires:**
- Valid S3 bucket name
- Multiple firmware files in the folder

### `aws_s3_cloudfront.yaml`
Generate CloudFront URLs for faster downloads

**Requires:**
- Valid S3 bucket name
- CloudFront distribution configured

## 🚀 Running Tests

```bash
# Run with virtual environment
.venv/bin/python -m easy_bdd run tests/cases/aws_s3_connection_test.yaml

# After configuring your bucket
.venv/bin/python -m easy_bdd run tests/cases/aws_s3_latest_firmware.yaml
```

## 📖 Full Documentation

See `docs/aws-s3-integration.md` for:
- Complete parameter reference
- All available actions
- Advanced examples
- Best practices
- Troubleshooting guide

## ✨ Features Demonstrated

### Smart Version Sorting
Files are sorted numerically: `1.2.3` → `1.2.10` → `1.2.20` → `2.0.0`

### Automatic Version Extraction
```yaml
- action: "AWS get latest firmware"
  store_version_as: "fw_version"  # Extracts: "2.2.1.0"
```

### Flexible Filtering
```yaml
filename_pattern: "wattboxvps"      # Match specific product
file_extension: ".bin"              # Only .bin files
specific_version: ["1.00.48"]       # Specific versions
```

### CloudFront URLs
```yaml
cloudfront_url: "d12345.cloudfront.net"
cloudfront_filename_only: true
```

## 🎯 Real-World Usage

Once configured with your actual S3 bucket, these tests can:

1. **Download latest firmware** for automated testing
2. **Validate firmware versions** before testing
3. **Upload test results** to S3
4. **Generate shareable URLs** with CloudFront
5. **Clean up old test artifacts**

## 💡 Tips

- Use AWS CLI for easiest credential management
- Store sensitive values in environment variables
- Use CloudFront for faster downloads in CI/CD
- Enable version filtering for regression testing
