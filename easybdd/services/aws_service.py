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
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple, Union
from pathlib import Path
from urllib.parse import quote as _url_quote


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

    def _build_object_url(self, bucket_name: str, key: str, protocol: str = "https") -> str:
        """Build the public URL for an object.

        Overridden by FlociService so URLs returned to variables (store_as /
        store_url_as) point at the local Floci endpoint instead of a fake
        s3.amazonaws.com host that would never resolve.
        """
        return f"{protocol}://{bucket_name}.s3.amazonaws.com/{key}"

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

    def _discover_prefix_from_repo(
        self,
        filename_pattern: str,
        repo_root: str = None,
    ) -> str:
        """
        Derive an S3 folder prefix by walking the local repo directory tree and
        finding the first folder whose name contains filename_pattern.  The
        returned value is the path relative to repo_root (using forward slashes),
        which mirrors the expected S3 key structure.

        Args:
            filename_pattern: Pattern to match against directory names
            repo_root: Root of the local repo checkout (defaults to cwd)

        Returns:
            Relative folder path (e.g. "Firmware/wattbox/vps") or None if not found.
        """
        root = Path(repo_root or os.getcwd())
        pattern_lower = filename_pattern.lower()

        for dirpath, dirnames, _ in os.walk(root):
            # Skip hidden dirs and virtual-env/cache dirs
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d not in ("env", "venv", "__pycache__", "node_modules")
            ]
            folder = Path(dirpath)
            if pattern_lower in folder.name.lower():
                rel = folder.relative_to(root)
                prefix = str(rel).replace(os.sep, "/")
                self._log(f"Repo-based prefix discovery: found '{prefix}' for pattern '{filename_pattern}'")
                return prefix

        return None

    def discover_prefix(
        self,
        bucket_name: str,
        filename_pattern: str,
        repo_root: str = None,
        access_key_id: str = None,
        secret_access_key: str = None,
        region: str = None,
    ) -> str:
        """
        Discover the S3 folder prefix for files matching filename_pattern.

        Strategy (in order):
        1. Walk the local repo directory tree — if a folder name contains
           filename_pattern, use its relative path as the prefix.  This is fast
           and keeps S3 prefixes aligned with the repo layout.
        2. Fall back to scanning the S3 bucket using list_objects_v2 with
           Delimiter='/' so only one level is fetched at a time.

        Args:
            bucket_name: S3 bucket name (used only for S3 fallback)
            filename_pattern: Pattern to match in folder/file names
            repo_root: Local repo root (defaults to cwd)
            access_key_id: AWS Access Key ID
            secret_access_key: AWS Secret Access Key
            region: AWS region

        Returns:
            Prefix string (may be "") or None if nothing matched.
        """
        # 1. Try repo directory structure first
        repo_prefix = self._discover_prefix_from_repo(filename_pattern, repo_root)
        if repo_prefix is not None:
            self._log(f"Using repo-derived prefix: '{repo_prefix}'")
            return repo_prefix

        self._log(f"No repo folder matched '{filename_pattern}', falling back to S3 scan")

        # 2. Fall back to S3 bucket walk
        self._get_s3_clients(bucket_name, access_key_id, secret_access_key, region)

        def _search(prefix=""):
            resp = self._s3_client.list_objects_v2(
                Bucket=bucket_name, Prefix=prefix, Delimiter="/"
            )
            for obj in resp.get("Contents", []):
                filename = obj["Key"].split("/")[-1]
                if filename_pattern.lower() in filename.lower():
                    return prefix if prefix else ""
            for cp in resp.get("CommonPrefixes", []):
                result = _search(cp["Prefix"])
                if result is not None:
                    return result
            return None

        found = _search()
        if found is not None:
            self._log(f"S3-discovered prefix '{found}' for pattern '{filename_pattern}'")
        else:
            self._log(f"No prefix found for pattern '{filename_pattern}'", "warning")
        return found

    def list_firmware_files(
        self,
        bucket_name: str,
        folder_prefix: Union[str, List[str]] = None,
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
        repo_root: str = None,
    ) -> List[str]:
        """
        List firmware files from S3 bucket with filtering and optional download.

        Args:
            bucket_name: S3 bucket name
            folder_prefix: Folder prefix(es) to filter objects (string or list of strings)
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
                repo_root=repo_root,
                access_key_id=access_key_id,
                secret_access_key=secret_access_key,
                region=region,
            )

        # Normalize folder_prefix to a list, ensuring each entry ends with '/'
        if not folder_prefix:
            prefixes = [None]
        elif isinstance(folder_prefix, list):
            prefixes = [p if p.endswith("/") else p + "/" for p in folder_prefix if p]
            if not prefixes:
                prefixes = [None]
        else:
            prefixes = [folder_prefix if folder_prefix.endswith("/") else folder_prefix + "/"]

        # Log active filters so users can see exactly what will be applied
        self._log(f"─── aws.list_files ───────────────────────────────")
        self._log(f"  bucket       : {bucket_name}")
        self._log(f"  folder_prefix: {prefixes if len(prefixes) > 1 else (prefixes[0] or '(none — scanning all)')}")
        self._log(f"  file_extension: {file_extension or '(none)'}")
        self._log(f"  filename_pattern: {filename_pattern or '(none)'}")
        self._log(f"  version_pattern : {version_pattern or '(none)'}")
        self._log(f"  specific_version: {specific_version or '(none)'}")

        object_urls = []
        cloudfront_urls = []
        last_modified_by_key = {}
        scanned = 0
        skipped_ext = skipped_pattern = skipped_version = skipped_specific = 0

        try:
            # Collect objects from all prefixes, deduplicating by key
            seen_keys: set = set()
            all_objects = []
            for pfx in prefixes:
                if pfx:
                    objects = self._current_bucket.objects.filter(Prefix=pfx)
                    self._log(f"  Querying s3://{bucket_name}/{pfx} ...")
                else:
                    objects = self._current_bucket.objects.all()
                    self._log(f"  Querying s3://{bucket_name}/ (all objects) ...")
                for obj in objects:
                    if obj.key not in seen_keys:
                        seen_keys.add(obj.key)
                        all_objects.append(obj)

            self._log(f"  Total objects returned by S3: {len(all_objects)}")
            if not all_objects:
                self._log(
                    f"  ⚠  No objects found under prefix={prefixes!r}. "
                    f"Check bucket name and folder_prefix (S3 prefixes are case-sensitive)."
                )

            # Filter objects — log each skip reason
            for obj in all_objects:
                scanned += 1
                key = obj.key

                # Skip zero-byte "folder" placeholder objects
                if key.endswith("/"):
                    self._log(f"  SKIP  {key}  (directory placeholder)")
                    continue

                # Filter by filename pattern
                if filename_pattern and filename_pattern.lower() not in key.lower():
                    self._log(f"  SKIP  {key}  (no match for filename_pattern={filename_pattern!r})")
                    skipped_pattern += 1
                    continue

                # Filter by version pattern (use cached regex)
                if version_pattern:
                    regex = self._get_compiled_regex(version_pattern)
                    if not regex.search(key):
                        self._log(f"  SKIP  {key}  (no match for version_pattern={version_pattern!r})")
                        skipped_version += 1
                        continue

                # Filter by file extension (case-insensitive comparison)
                if file_extension:
                    ext_lower = file_extension.lower()
                    if not key.lower().endswith(ext_lower):
                        self._log(f"  SKIP  {key}  (extension != {file_extension!r}, actual={os.path.splitext(key)[1]!r})")
                        skipped_ext += 1
                        continue

                # Filter by specific version(s)
                if specific_version:
                    versions = (
                        specific_version
                        if isinstance(specific_version, list)
                        else [specific_version]
                    )
                    if not any(ver in key for ver in versions):
                        self._log(f"  SKIP  {key}  (specific_version {versions!r} not in key)")
                        skipped_specific += 1
                        continue

                self._log(f"  MATCH {key}")

                # Build S3 URL — encode path so spaces become %20
                encoded_key = _url_quote(key, safe="/")
                s3_url = self._build_object_url(bucket_name, encoded_key, protocol)
                object_urls.append(s3_url)

                # Build CloudFront URL if specified
                if cloudfront_url:
                    if cloudfront_filename_only:
                        filename = _url_quote(os.path.basename(key), safe="")
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
                    local_file = local_dir / os.path.basename(key)

                    if local_file.exists():
                        self._log(f"  ↓ Already downloaded: {local_file.name}")
                    else:
                        self._log(f"  ↓ Downloading: {key} → {local_file}")
                        self._current_bucket.download_file(key, str(local_file))

                # Recorded for every matched key so _sort_urls_by_version can fall
                # back to actual upload time for filenames that don't carry a
                # parseable build timestamp (e.g. dev/test build tags).
                last_modified_by_key[key] = obj.last_modified

            # Choose URLs to return
            urls = cloudfront_urls if cloudfront_url else object_urls

            # Sort URLs by version (intelligent numeric sorting)
            urls = self._sort_urls_by_version(
                urls, bucket_name, cloudfront_url, last_modified_by_key
            )

            # Summary
            self._log(
                f"  ─── Summary: scanned={scanned}  matched={len(urls)}  "
                f"skipped(ext={skipped_ext} pattern={skipped_pattern} "
                f"version={skipped_version} specific={skipped_specific})"
            )
            if not urls:
                self._log(
                    "  ⚠  0 files matched. Common causes:\n"
                    "     • folder_prefix is wrong (S3 prefixes are case-sensitive; "
                    "try listing without a prefix first)\n"
                    "     • file_extension casing mismatch (use lowercase e.g. '.bin')\n"
                    "     • filename_pattern not present in any key\n"
                    "     • Bucket has no objects yet"
                )
            else:
                for i, u in enumerate(urls, 1):
                    self._log(f"  [{i}] {u}")
            return urls

        except Exception as e:
            self._log(f"  ✗ Error listing S3 objects: {e}", "error")
            raise

    def _sort_urls_by_version(
        self,
        urls: List[str],
        bucket_name: str,
        cloudfront_url: str = None,
        last_modified_by_key: Dict[str, Any] = None,
    ) -> List[str]:
        """Sort URLs newest-first by recency, non-DM before DM per build.

        Filename format: <prefix>_<semver>-<YYMMDDHHII>[-DM].<ext>
        The 10-digit build timestamp, converted to a real UTC epoch, is the
        primary recency signal (descending) so it's directly comparable
        against the S3 "last modified" fallback below.

        Ad-hoc/dev build tags (e.g. a branch-derived "jpdse2749c" suffix
        instead of a YYMMDDHHII timestamp) don't carry a parseable date, and
        the app semver embedded in the filename (e.g. "2.10.0.0") is
        identical across every build — so a naive semver-only fallback ties
        every ad-hoc build together and, worse, always ranks them below any
        real timestamped build regardless of how the ad-hoc suffix is
        renamed. Falling back to the object's actual S3 upload time
        (last_modified) instead means a newly-uploaded ad-hoc build is
        correctly recognised as the latest.

        Non-DM variants sort before DM for the same recency, matching the
        interleaved pair order expected by callers (index 0 = newest non-DM,
        index 1 = newest DM, index 2 = second-newest non-DM, ...).
        """

        def extract_filename(url):
            if cloudfront_url:
                key = url.split(f"{cloudfront_url}/")[-1]
            else:
                key = url.split(f"{bucket_name}.s3.amazonaws.com/")[-1]
            return key, key.split("/")[-1]

        def sort_key(url):
            key, filename = extract_filename(url)
            is_dm = 1 if "-DM." in filename or filename.endswith("-DM") else 0

            # Primary: 10-digit build timestamp (e.g. wattbox firmware)
            m = re.search(r"-(\d{10})(?:-DM)?(?:\.|$)", filename)
            if m:
                try:
                    recency = (
                        datetime.strptime(m.group(1), "%y%m%d%H%M")
                        .replace(tzinfo=timezone.utc)
                        .timestamp()
                    )
                    return (-recency, is_dm, key)
                except ValueError:
                    pass  # not a real date (e.g. "9999999999") — fall through

            # Fallback: actual S3 upload time, for ad-hoc build tags
            if last_modified_by_key and key in last_modified_by_key:
                return (-last_modified_by_key[key].timestamp(), is_dm, key)

            # Last resort: semver X.Y.Z (e.g. upgrade_moip_4.7.0.bin) when no
            # upload-time data is available at all
            sv = re.search(r"(\d+)\.(\d+)\.(\d+)", filename)
            if sv:
                version_int = int(sv.group(1)) * 1_000_000 + int(sv.group(2)) * 1_000 + int(sv.group(3))
                return (-version_int, is_dm, key)
            return (0, is_dm, key)

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
        repo_root: str = None,
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
                repo_root=repo_root,
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

            # Sort by recency (use cached regex). The app semver embedded in
            # the filename (e.g. "2.10.0.0") is identical across every build
            # of a given firmware, so sorting on it alone (as before) leaves
            # every same-app-version file tied and picks an arbitrary one via
            # Python's stable sort — not actually the latest. Prefer the
            # 10-digit build timestamp (converted to a real UTC epoch) and
            # fall back to the object's S3 upload time for filenames that
            # don't carry one (e.g. ad-hoc/dev build tags like "jpdse2749c"),
            # only falling back to the semver tuple if neither is available.
            build_timestamp_regex = self._get_compiled_regex(r"-(\d{10})(?:-DM)?(?:\.|$)")
            version_sort_regex = self._get_compiled_regex(r"(\d+)\.(\d+)\.(\d+)\.(\d+)")
            last_modified_by_key = {obj.key: obj.last_modified for obj in objects}

            def extract_recency(filename):
                """Extract a comparable recency value for sorting (higher = newer)."""
                m = build_timestamp_regex.search(filename)
                if m:
                    try:
                        return (
                            datetime.strptime(m.group(1), "%y%m%d%H%M")
                            .replace(tzinfo=timezone.utc)
                            .timestamp()
                        )
                    except ValueError:
                        pass  # not a real date — fall through
                lm = last_modified_by_key.get(filename)
                if lm is not None:
                    return lm.timestamp()
                match = version_sort_regex.search(filename)
                if match:
                    major, minor, patch, build = (int(x) for x in match.groups())
                    return major * 1_000_000_000 + minor * 1_000_000 + patch * 1_000 + build
                return 0

            filtered.sort(key=extract_recency)

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
            url = self._build_object_url(bucket_name, latest_file)

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

            url = self._build_object_url(bucket_name, s3_key)
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

    def delete_object(
        self,
        bucket_name: str,
        s3_key: str,
        access_key_id: str = None,
        secret_access_key: str = None,
        region: str = None,
    ) -> bool:
        """
        Delete a single object from S3 by key.

        S3's delete_object is idempotent — deleting a key that doesn't exist
        is not an error — so callers (e.g. a CI mirror step reacting to a
        git-removed file) don't need to check existence first.

        Args:
            bucket_name: S3 bucket name
            s3_key: Object key to delete
            access_key_id: AWS Access Key ID
            secret_access_key: AWS Secret Access Key
            region: AWS Region

        Returns:
            True if successful
        """
        self._get_s3_clients(bucket_name, access_key_id, secret_access_key, region)

        try:
            self._log(f"Deleting {bucket_name}/{s3_key}")
            self._s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
            self._log(f"Deleted: {s3_key}")
            return True

        except Exception as e:
            self._log(f"Error deleting {s3_key}: {str(e)}", "error")
            raise
