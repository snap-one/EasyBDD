"""
Floci Service for Easy BDD Framework

Floci (https://floci.io) is a free, open-source local emulator for AWS
services — it speaks the real AWS wire protocol on a single endpoint
(default http://localhost:4566), so boto3/AWS CLI clients work against it
unmodified, with no real credentials required.

This service is a thin variant of AWSService: it reuses every bit of the S3
firmware logic (listing, get-latest, upload, delete, version sorting, prefix
discovery) and only changes *where* boto3 connects to and *what* identity it
uses. Real AWS S3 access (AWSService / the "aws.*" and "s3.*" actions) is
completely unaffected — Floci is an additional, independent target selected
via the "floci.*" action prefix.
"""

import os
from typing import Optional, Tuple

from .aws_service import AWSService

DEFAULT_FLOCI_ENDPOINT = "http://localhost:4566"
DEFAULT_FLOCI_IDENTITY = "test"


class FlociService(AWSService):
    """AWSService variant that targets a local Floci endpoint instead of real AWS."""

    # Separate from AWSService._global_config / _connection_pool so configuring
    # or connecting to Floci can never leak into (or be confused with) real S3.
    _global_config = {
        "access_key_id": None,
        "secret_access_key": None,
        "region": "us-east-1",
        "endpoint_url": None,
    }
    _connection_pool = {}

    def __init__(self, logger=None, endpoint_url: str = None):
        super().__init__(logger=logger)
        self._explicit_endpoint = endpoint_url

    @classmethod
    def configure_global_credentials(
        cls,
        access_key_id: str = None,
        secret_access_key: str = None,
        region: str = "us-east-1",
        endpoint_url: str = None,
    ):
        """Configure global Floci defaults (endpoint, region, identity)."""
        cls._global_config.update(
            {
                "access_key_id": access_key_id,
                "secret_access_key": secret_access_key,
                "region": region,
                "endpoint_url": endpoint_url,
            }
        )

    def _resolve_endpoint(self, endpoint_url: str = None) -> str:
        return (
            endpoint_url
            or self._explicit_endpoint
            or self._global_config.get("endpoint_url")
            or os.environ.get("FLOCI_ENDPOINT_URL")
            or DEFAULT_FLOCI_ENDPOINT
        )

    def _build_object_url(self, bucket_name: str, key: str, protocol: str = "https") -> str:
        # Path-style addressing — virtual-hosted-style (bucket.localhost:4566)
        # requires DNS/hosts-file setup Floci doesn't assume by default.
        endpoint = self._resolve_endpoint().rstrip("/")
        return f"{endpoint}/{bucket_name}/{key}"

    def _resolve_credentials(
        self,
        access_key_id: str = None,
        secret_access_key: str = None,
        region: str = None,
    ) -> Tuple[str, str, str]:
        # Deliberately does NOT fall back to "AWS CLI default profile" like
        # AWSService does — that profile is irrelevant to Floci and usually
        # won't exist in CI. Floci accepts any identity, so we always resolve
        # to a concrete value instead of signalling "use boto3 defaults".
        resolved_key = (
            access_key_id
            or self._global_config.get("access_key_id")
            or os.environ.get("FLOCI_ACCESS_KEY_ID")
            or DEFAULT_FLOCI_IDENTITY
        )
        resolved_secret = (
            secret_access_key
            or self._global_config.get("secret_access_key")
            or os.environ.get("FLOCI_SECRET_ACCESS_KEY")
            or DEFAULT_FLOCI_IDENTITY
        )
        resolved_region = (
            region
            or self._global_config.get("region")
            or os.environ.get("FLOCI_REGION", "us-east-1")
        )
        return resolved_key, resolved_secret, resolved_region

    def _get_s3_clients(
        self,
        bucket_name: str,
        access_key_id: str = None,
        secret_access_key: str = None,
        region: str = None,
    ):
        import boto3

        key, secret, reg = self._resolve_credentials(
            access_key_id, secret_access_key, region
        )
        endpoint = self._resolve_endpoint()

        pool_key = f"{endpoint}_{bucket_name}_{reg}_{key}"

        if pool_key in self._connection_pool:
            cached = self._connection_pool[pool_key]
            self._s3_resource = cached["resource"]
            self._s3_client = cached["client"]
            self._current_bucket = cached["bucket"]
            self._bucket_name = bucket_name
            return

        self._s3_resource = boto3.resource(
            "s3",
            region_name=reg,
            endpoint_url=endpoint,
            aws_access_key_id=key,
            aws_secret_access_key=secret,
        )
        self._s3_client = boto3.client(
            "s3",
            region_name=reg,
            endpoint_url=endpoint,
            aws_access_key_id=key,
            aws_secret_access_key=secret,
        )

        self._ensure_bucket(bucket_name)

        self._current_bucket = self._s3_resource.Bucket(bucket_name)
        self._bucket_name = bucket_name

        self._connection_pool[pool_key] = {
            "resource": self._s3_resource,
            "client": self._s3_client,
            "bucket": self._current_bucket,
        }

        self._log(f"Connected to Floci bucket: {bucket_name} (endpoint: {endpoint})")

    def _ensure_bucket(self, bucket_name: str) -> None:
        """Create the bucket if it doesn't exist yet — Floci starts empty on
        every fresh container, unlike real S3 where buckets are provisioned
        out of band."""
        try:
            self._s3_client.head_bucket(Bucket=bucket_name)
        except Exception:
            try:
                self._s3_client.create_bucket(Bucket=bucket_name)
                self._log(f"Created Floci bucket: {bucket_name}")
            except Exception as e:
                self._log(f"Could not ensure Floci bucket {bucket_name!r}: {e}", "warning")
