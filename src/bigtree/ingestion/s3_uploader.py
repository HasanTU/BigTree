"""S3 uploader for raw ingestion data with local filesystem fallback."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    """Parse 's3://bucket-name/key/path' into (bucket, key)."""
    parsed = urlparse(uri)
    if parsed.scheme != "s3":
        raise ValueError(f"Invalid S3 URI scheme '{parsed.scheme}'. Expected 's3://'.")
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        raise ValueError(f"Malformed S3 URI '{uri}'. Must include both bucket and object key.")
    return bucket, key


def upload_raw_data(
    data: dict[str, Any],
    destination: str,
    s3_client: Any | None = None,
    allow_local_fallback: bool = True,
) -> str:
    """Upload raw data payload as JSON to S3, or mirror locally if S3 is unavailable.

    Args:
        data: Dict payload (e.g. containing metadata and raw API response).
        destination: Target S3 URI (e.g., 's3://dubaimai/raw/weather/district_001.json')
                     or local filepath if fallback is active.
        s3_client: Optional pre-configured boto3 S3 client.
        allow_local_fallback: If True, writes to a local '.s3_mock' directory when
                             AWS credentials are absent or MOCK_S3_LOCAL_DIR is set.

    Returns:
        The URI where the object was stored.
    """
    json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

    # Check for forced local mock mode via env var
    mock_base = os.getenv("MOCK_S3_LOCAL_DIR")

    if destination.startswith("s3://") and not mock_base:
        bucket, key = _parse_s3_uri(destination)
        client = s3_client or boto3.client("s3")
        try:
            logger.info("Uploading %d bytes to S3: s3://%s/%s", len(json_bytes), bucket, key)
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=json_bytes,
                ContentType="application/json; charset=utf-8",
            )
            return destination
        except (NoCredentialsError, ClientError, BotoCoreError) as s3_err:
            if not allow_local_fallback:
                raise
            logger.warning(
                "S3 upload failed (%s). Falling back to local filesystem storage.",
                s3_err,
            )
            mock_base = ".s3_mock"

    # Local storage fallback
    if mock_base or not destination.startswith("s3://"):
        if destination.startswith("s3://"):
            bucket, key = _parse_s3_uri(destination)
            target_path = Path(mock_base or ".s3_mock") / bucket / key
        else:
            target_path = Path(destination)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(json_bytes)
        logger.info("Saved local raw mirror to %s", target_path.resolve())
        return str(target_path)

    return destination
