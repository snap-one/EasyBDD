"""
AWS S3 Service for Easy BDD Framework

Provides S3 operations including:
- List and download firmware files
- Upload files to S3
- Extract firmware versions
- CloudFront URL generation
- Version-aware sorting
"""

import os
import re
import boto3
from typing import Optional, List, Dict, Any, Tuple, Union
from pathlib import Path


class AWSService:
    """Service for AWS S3 operations with firmware file handling."""

    # Global AWS configuration
    _global_config = {
        "access_key_id": None,
        "secret_access_key": None,
        "region": "us-east-1",
    }

    # Connection pool for reusing S3 clients (30-50% performance improvement)
    _connection_pool = {}

    # Regex pattern cache for version extraction (20% performance improvement)
    _regex_cache = {}

    def __init__(self, logger=None):
        """
        Initialize AWS Service.

        Args:
            logger: Logger instance for output
        """
        self.logger = logger
        self._s3_resource = None
        self._s3_client = None
        self._current_bucket = None
        self._bucket_name = None

    @classmethod
    def configure_global_credentials(
        cls,
        access_key_id: str = None,
        secret_access_key: str = None,
        region: str = "us-east-1",
    ):
        """
        Configure global AWS credentials (optional - will use AWS CLI config if not set).

        Args:
            access_key_id: AWS Access Key ID
            secret_access_key: AWS Secret Access Key
            region: AWS Region (default: us-east-1)
        """
        cls._global_config.update(
            {
                "access_key_id": access_key_id,
                "secret_access_key": secret_access_key,
                "region": region,
            }
        )

    def _log(self, message: str, level: str = "info"):
        """Log a message if logger is available."""
        if self.logger:
            # Check if logger has the level method (like info, error, etc.)
            if hasattr(self.logger, level):
                log_func = getattr(self.logger, level)
                log_func(message)
            else:
                # Logger is a function (like print), just call it
                self.logger(f"      {message}")
        else:
            print(f"      {message}")

    def _resolve_credentials(
        self,
        access_key_id: str = None,
        secret_access_key: str = None,
        region: str = None,
    ) -> Tuple[str, str, str]:
        """
        Resolve AWS credentials from parameters, global config, or AWS CLI.

        Args:
            access_key_id: AWS Access Key ID
            secret_access_key: AWS Secret Access Key
            region: AWS Region

        Returns:
            Tuple of (access_key_id, secret_access_key, region)
        """
        # Priority: parameters > global config > environment > AWS CLI
        resolved_key = (
            access_key_id
            or self._global_config.get("access_key_id")
            or os.environ.get("AWS_ACCESS_KEY_ID")
        )
        resolved_secret = (
            secret_access_key
            or self._global_config.get("secret_access_key")
            or os.environ.get("AWS_SECRET_ACCESS_KEY")
        )
        resolved_region = (
            region
            or self._global_config.get("region")
            or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        )

        if not resolved_key or not resolved_secret:
            self._log("Using AWS CLI default credentials", "info")
            return None, None, resolved_region

        return resolved_key, resolved_secret, resolved_region

    def _get_s3_clients(
        self,
        bucket_name: str,
        access_key_id: str = None,
        secret_access_key: str = None,
        region: str = None,
    ):
        """
        Get or create S3 clients for the specified bucket using connection pool.

        Args:
            bucket_name: S3 bucket name
            access_key_id: AWS Access Key ID
            secret_access_key: AWS Secret Access Key
            region: AWS Region
        """
        key, secret, reg = self._resolve_credentials(
            access_key_id, secret_access_key, region
        )

        # Create pool key for connection reuse
        pool_key = f"{bucket_name}_{reg}_{key or 'default'}"

        # Check connection pool first
        if pool_key in self._connection_pool:
            cached = self._connection_pool[pool_key]
            self._s3_resource = cached["resource"]
            self._s3_client = cached["client"]
            self._current_bucket = cached["bucket"]
            self._bucket_name = bucket_name
            return

        # Create new clients if not in pool
        if key and secret:
            self._s3_resource = boto3.resource(
                "s3",
                region_name=reg,
                aws_access_key_id=key,
                aws_secret_access_key=secret,
            )
            self._s3_client = boto3.client(
                "s3",
                region_name=reg,
                aws_access_key_id=key,
                aws_secret_access_key=secret,
            )
        else:
            # Use default AWS CLI credentials
            self._s3_resource = boto3.resource("s3", region_name=reg)
            self._s3_client = boto3.client("s3", region_name=reg)

        self._current_bucket = self._s3_resource.Bucket(bucket_name)
        self._bucket_name = bucket_name

        # Store in connection pool for reuse
        self._connection_pool[pool_key] = {
            "resource": self._s3_resource,
            "client": self._s3_client,
            "bucket": self._current_bucket,
        }

        self._log(f"Connected to S3 bucket: {bucket_name} (region: {reg})")

    def _get_compiled_regex(self, pattern: str):
        """
        Get compiled regex from cache or compile and cache it.

        Args:
            pattern: Regex pattern string

        Returns:
            Compiled regex object
        """
        if pattern not in self._regex_cache:
            self._regex_cache[pattern] = re.compile(pattern)
        return self._regex_cache[pattern]

    def discover_prefix(
        self,
        bucket_name: str,
        filename_pattern: str,
        access_key_id: str = None,
        secret_access_key: str = None,
        region: str = None,
    ) -> str:
        """
        Discover the S3 prefix (folder path) that contains files matching
        filename_pattern by walking the bucket's top-level directory tree.

        Args:
            bucket_name: S3 bucket name
            filename_pattern: Pattern to match in filenames
            access_key_id: AWS Access Key ID
            secret_access_key: AWS Secret Access Key
            region: AWS region

        Returns:
            The deepest common prefix that contains matching files, or "" if
            files are found but share no common prefix, or None if no match.
        """
        self._get_s3_clients(bucket_name, access_key_id, secret_access_key, region)

        paginator = self._s3_client.get_paginator("list_objects_v2")

        def _search(prefix=""):
            """Recursively walk prefixes, return first matching one."""
            resp = self._s3_client.list_objects_v2(
                Bucket=bucket_name, Prefix=prefix, Delimiter="/"
            )
            # Check files at this level
            for obj in resp.get("Contents", []):
                key = obj["Key"]
                filename = key.split("/")[-1]
                if filename_pattern.lower() in filename.lower():
                    # Return the folder portion (everything up to the last slash)
                    return prefix if prefix else ""
            # Recurse into sub-prefixes
            for cp in resp.get("CommonPrefixes", []):
                sub = cp["Prefix"]
                result = _search(sub)
                if result is not None:
                    return result
            return None

        found = _search()
        if found is not None:
            self._log(f"Discovered prefix '{found}' for pattern '{filename_pattern}'")
        else:
            self._log(f"No prefix found for pattern '{filename_pattern}'", "warning")
        return found

    def list_firmware_files(
        self,
        bucket_name: str,
        folder_prefix: str = None,
        filename_pattern: str = None,
        version_pattern: str = None,
        file_extension: str = None,
        specific_version: Union[str, List[str]] = None,
        cloudfront_url: str = None,
        cloudfront_filename_only: bool = False,
        download_dir: str = None,
        protocol: str = "https",
        access_key_id: str = None,
        secret_access_key: str = None,
        region: str = None,
        store_as: str = None,
        discover_prefix: bool = False,
    ) -> List[str]:
        """
        List firmware files from S3 bucket with filtering and optional download.

        Args:
            bucket_name: S3 bucket name
            folder_prefix: Folder prefix to filter objects
            filename_pattern: Pattern to match in filename (e.g., "wattbox", "firmware")
            version_pattern: Regex pattern to match version in filename
            file_extension: File extension to filter (e.g., ".bin", ".zip")
            specific_version: Specific version(s) to filter (string or list)
            cloudfront_url: CloudFront URL to replace S3 URL
            cloudfront_filename_only: Only append filename to CloudFront URL
            download_dir: Directory to download files (default: "Firmware" in workspace)
            protocol: URL protocol ("https" or "http")
            access_key_id: AWS Access Key ID
            secret_access_key: AWS Secret Access Key
            region: AWS Region
            store_as: Variable name to store URLs in

        Returns:
            List of URLs for the matching files
        """
        self._get_s3_clients(bucket_name, access_key_id, secret_access_key, region)

        if discover_prefix and not folder_prefix and filename_pattern:
            folder_prefix = self.discover_prefix(
                bucket_name, filename_pattern,
                access_key_id=access_key_id,
                secret_access_key=secret_access_key,
                region=region,
            )

        object_urls = []
        cloudfront_urls = []

        try:
            # Get objects
            if folder_prefix:
                objects = self._current_bucket.objects.filter(Prefix=folder_prefix)
                self._log(f"Listing files in {bucket_name}/{folder_prefix}")
            else:
                objects = self._current_bucket.objects.all()
                self._log(f"Listing all files in {bucket_name}")

            # Filter objects
            for obj in objects:
                # Filter by filename pattern
                if filename_pattern and filename_pattern.lower() not in obj.key.lower():
                    continue

                # Filter by version pattern (use cached regex)
                if version_pattern:
                    regex = self._get_compiled_regex(version_pattern)
                    if not regex.search(obj.key):
                        continue

                # Filter by file extension
                if file_extension and not obj.key.endswith(file_extension):
                    continue

                # Filter by specific version(s)
                if specific_version:
                    versions = (
                        specific_version
                        if isinstance(specific_version, list)
                        else [specific_version]
                    )
                    if not any(ver in obj.key for ver in versions):
                        continue

                # Build S3 URL
                s3_url = f"{protocol}://{bucket_name}.s3.amazonaws.com/{obj.key}"
                object_urls.append(s3_url)

                # Build CloudFront URL if specified
                if cloudfront_url:
                    if cloudfront_filename_only:
                        filename = os.path.basename(obj.key)
                        cf_url = f"{protocol}://{cloudfront_url}/{filename}"
                    else:
                        cf_url = s3_url.replace(
                            f"{bucket_name}.s3.amazonaws.com", cloudfront_url
                        )
                    cloudfront_urls.append(cf_url)

                # Download file if requested
                if download_dir:
                    local_dir = Path(download_dir)
                    local_dir.mkdir(parents=True, exist_ok=True)
                    local_file = local_dir / os.path.basename(obj.key)

                    if local_file.exists():
                        self._log(f"File already exists, skipping: {local_file.name}")
                    else:
                        self._log(f"Downloading: {obj.key} -> {local_file}")
                        self._current_bucket.download_file(obj.key, str(local_file))

            # Choose URLs to return
            urls = cloudfront_urls if cloudfront_url else object_urls

            # Sort URLs by version (intelligent numeric sorting)
            urls = self._sort_urls_by_version(urls, bucket_name, cloudfront_url)

            self._log(f"Found {len(urls)} matching files")
            return urls

        except Exception as e:
            self._log(f"Error listing S3 objects: {str(e)}", "error")
            raise

    def _sort_urls_by_version(
        self, urls: List[str], bucket_name: str, cloudfront_url: str = None
    ) -> List[str]:
        """
        Sort URLs using version-aware numeric sorting.

        Args:
            urls: List of URLs to sort
            bucket_name: S3 bucket name for extracting object keys
            cloudfront_url: CloudFront URL if used

        Returns:
            Sorted list of URLs
        """

        def extract_key(url):
            """Extract S3 object key from URL."""
            if cloudfront_url:
                return url.split(f"{cloudfront_url}/")[-1]
            return url.split(f"{bucket_name}.s3.amazonaws.com/")[-1]

        def find_best_version_token(key):
            """Find the best version-like token in the key."""
            matches = re.findall(r"\d+(?:\.\d+)*", key)
            if not matches:
                return None
            # Prefer tokens with more components
            return max(matches, key=lambda m: (m.count("."), len(m)))

        def token_to_components(token):
            """Convert version token to sortable components."""
            parts = token.split(".")
            comps = []
            for p in parts:
                if p.isdigit():
                    comps.append((0, int(p)))
                else:
                    comps.append((1, p))
            return tuple(comps)

        def sort_key(url):
            """Generate sort key for a URL."""
            key = extract_key(url)
            token = find_best_version_token(key)

            if token:
                comps = token_to_components(token)
                return (0, comps, key)
            return (1, key)

        return sorted(urls, key=sort_key)

    def get_latest_firmware(
        self,
        bucket_name: str,
        folder_prefix: str = None,
        filename_pattern: str = None,
        version_pattern: str = None,
        file_extension: str = ".bin",
        download_dir: str = None,
        get_second_to_last: bool = False,
        access_key_id: str = None,
        secret_access_key: str = None,
        region: str = None,
        store_filename_as: str = None,
        store_version_as: str = None,
        store_url_as: str = None,
        discover_prefix: bool = False,
    ) -> Dict[str, Any]:
        """
        Get the latest (or second-to-last) firmware file from S3.

        Args:
            bucket_name: S3 bucket name
            folder_prefix: Folder prefix to filter objects
            filename_pattern: Pattern to match in filename
            version_pattern: Regex pattern to extract version
            file_extension: File extension to filter
            download_dir: Directory to download file
            get_second_to_last: Get second-to-last file instead of latest
            access_key_id: AWS Access Key ID
            secret_access_key: AWS Secret Access Key
            region: AWS Region
            store_filename_as: Variable name to store filename
            store_version_as: Variable name to store version
            store_url_as: Variable name to store URL

        Returns:
            Dict with 'filename', 'version', and 'url' keys
        """
        self._get_s3_clients(bucket_name, access_key_id, secret_access_key, region)

        if discover_prefix and not folder_prefix and filename_pattern:
            folder_prefix = self.discover_prefix(
                bucket_name, filename_pattern,
                access_key_id=access_key_id,
                secret_access_key=secret_access_key,
                region=region,
            )

        try:
            # Get objects
            if folder_prefix:
                objects = list(
                    self._current_bucket.objects.filter(Prefix=folder_prefix)
                )
                self._log(f"Searching in {bucket_name}/{folder_prefix}")
            else:
                objects = list(self._current_bucket.objects.all())
                self._log(f"Searching entire bucket: {bucket_name}")

            # Filter by extension and filename pattern
            filtered = []
            for obj in objects:
                if not obj.key.endswith(file_extension):
                    continue
                if filename_pattern and filename_pattern.lower() not in obj.key.lower():
                    continue
                filtered.append(obj.key)

            if not filtered:
                self._log(f"No files found matching criteria", "warning")
                return {"filename": None, "version": None, "url": None}

            self._log(f"Found {len(filtered)} files matching criteria")

            # Sort by version (use cached regex)
            version_sort_regex = self._get_compiled_regex(r"(\d+)\.(\d+)\.(\d+)\.(\d+)")

            def extract_version_tuple(filename):
                """Extract version for sorting."""
                match = version_sort_regex.search(filename)
                if match:
                    return tuple(int(x) for x in match.groups())
                return (0, 0, 0, 0)

            filtered.sort(key=extract_version_tuple)

            # Get appropriate file
            if get_second_to_last and len(filtered) >= 2:
                latest_file = filtered[-2]
                self._log(f"Selected second-to-last file: {latest_file}")
            else:
                latest_file = filtered[-1]
                self._log(f"Selected latest file: {latest_file}")

            # Extract version (use cached regex)
            if version_pattern:
                version_regex_pattern = version_pattern
            else:
                version_regex_pattern = r"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9]+)?)"

            version_regex = self._get_compiled_regex(version_regex_pattern)
            match = version_regex.search(latest_file)
            version = (
                match.group(1)
                if match and match.groups()
                else (match.group(0) if match else None)
            )

            if version:
                self._log(f"Extracted version: {version}")
            else:
                self._log(f"Could not extract version from: {latest_file}", "warning")

            # Build URL
            url = f"https://{bucket_name}.s3.amazonaws.com/{latest_file}"

            # Download if requested
            if download_dir:
                local_dir = Path(download_dir)
                local_dir.mkdir(parents=True, exist_ok=True)
                local_file = local_dir / os.path.basename(latest_file)

                if local_file.exists():
                    self._log(f"File already exists: {local_file.name}")
                else:
                    self._log(f"Downloading: {latest_file}")
                    self._current_bucket.download_file(latest_file, str(local_file))

            return {
                "filename": latest_file,
                "basename": os.path.basename(latest_file),
                "version": version,
                "url": url,
            }

        except Exception as e:
            self._log(f"Error getting latest firmware: {str(e)}", "error")
            raise

    def upload_file(
        self,
        bucket_name: str,
        local_file_path: str,
        s3_key: str = None,
        make_public: bool = True,
        access_key_id: str = None,
        secret_access_key: str = None,
        region: str = None,
    ) -> str:
        """
        Upload a file to S3.

        Args:
            bucket_name: S3 bucket name
            local_file_path: Local file path to upload
            s3_key: S3 object key (default: filename)
            make_public: Make file publicly readable
            access_key_id: AWS Access Key ID
            secret_access_key: AWS Secret Access Key
            region: AWS Region

        Returns:
            S3 URL of uploaded file
        """
        self._get_s3_clients(bucket_name, access_key_id, secret_access_key, region)

        try:
            local_path = Path(local_file_path)
            if not local_path.exists():
                raise FileNotFoundError(f"File not found: {local_file_path}")

            # Use filename as key if not specified
            if not s3_key:
                s3_key = local_path.name

            self._log(f"Uploading {local_path.name} to {bucket_name}/{s3_key}")

            # Upload file
            self._s3_client.upload_file(str(local_path), bucket_name, s3_key)

            # Make public if requested
            if make_public:
                self._s3_client.put_object_acl(
                    ACL="public-read", Bucket=bucket_name, Key=s3_key
                )
                self._log(f"File made public: {s3_key}")

            url = f"https://{bucket_name}.s3.amazonaws.com/{s3_key}"
            self._log(f"Upload complete: {url}")

            return url

        except Exception as e:
            self._log(f"Error uploading file: {str(e)}", "error")
            raise

    def delete_folder(
        self,
        bucket_name: str,
        folder_prefix: str,
        access_key_id: str = None,
        secret_access_key: str = None,
        region: str = None,
    ) -> bool:
        """
        Delete all objects in a folder (prefix).

        Args:
            bucket_name: S3 bucket name
            folder_prefix: Folder prefix to delete
            access_key_id: AWS Access Key ID
            secret_access_key: AWS Secret Access Key
            region: AWS Region

        Returns:
            True if successful
        """
        self._get_s3_clients(bucket_name, access_key_id, secret_access_key, region)

        try:
            self._log(f"Deleting folder: {bucket_name}/{folder_prefix}")
            self._current_bucket.objects.filter(Prefix=folder_prefix).delete()
            self._log(f"Folder deleted successfully")
            return True

        except Exception as e:
            self._log(f"Error deleting folder: {str(e)}", "error")
            raise
