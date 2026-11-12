"""S3 Storage Adapter with local fallback for AWS and local pipeline execution."""

from __future__ import annotations

import io
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
import pandas as pd

logger = logging.getLogger(__name__)


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme == "s3":
        return parsed.netloc, parsed.path.lstrip("/")
    # If passed as a plain relative or absolute path
    return "", uri


class S3StorageAdapter:
    """Implements StoragePort using Amazon S3 with an automatic local fallback mirror."""

    def __init__(
        self,
        s3_client: Any | None = None,
        allow_local_fallback: bool = True,
        mock_root_dir: str | Path = ".s3_mock",
    ) -> None:
        self.s3_client = s3_client
        self.allow_local_fallback = allow_local_fallback
        self.mock_root = Path(mock_root_dir)

    def _get_client(self) -> Any:
        if self.s3_client is None:
            self.s3_client = boto3.client("s3")
        return self.s3_client

    def read_json(self, uri: str) -> dict[str, Any]:
        bucket, key = _parse_s3_uri(uri)
        if bucket and not os.getenv("MOCK_S3_LOCAL_DIR"):
            try:
                client = self._get_client()
                obj = client.get_object(Bucket=bucket, Key=key)
                return json.loads(obj["Body"].read().decode("utf-8"))
            except (NoCredentialsError, ClientError, BotoCoreError) as err:
                if not self.allow_local_fallback:
                    raise
                logger.warning("S3 read failed (%s), falling back to local storage.", err)

        # Fallback to local
        local_path = self.mock_root / bucket / key if bucket else Path(key)
        if not local_path.is_file():
            # Check direct path
            if Path(uri).is_file():
                local_path = Path(uri)
            else:
                raise FileNotFoundError(f"File not found: {uri} (local candidate: {local_path})")
        return json.loads(local_path.read_text(encoding="utf-8"))

    def write_json(self, uri: str, data: dict[str, Any]) -> str:
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        bucket, key = _parse_s3_uri(uri)

        if bucket and not os.getenv("MOCK_S3_LOCAL_DIR"):
            try:
                client = self._get_client()
                client.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=json_str.encode("utf-8"),
                    ContentType="application/json; charset=utf-8",
                )
                return uri
            except (NoCredentialsError, ClientError, BotoCoreError) as err:
                if not self.allow_local_fallback:
                    raise
                logger.warning("S3 write failed (%s), falling back to local storage.", err)

        local_path = self.mock_root / bucket / key if bucket else Path(key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(json_str, encoding="utf-8")
        return str(local_path)

    def read_csv(self, uri: str) -> pd.DataFrame:
        bucket, key = _parse_s3_uri(uri)
        if bucket and not os.getenv("MOCK_S3_LOCAL_DIR"):
            try:
                client = self._get_client()
                obj = client.get_object(Bucket=bucket, Key=key)
                return pd.read_csv(obj["Body"])
            except (NoCredentialsError, ClientError, BotoCoreError) as err:
                if not self.allow_local_fallback:
                    raise
                logger.warning("S3 read failed (%s), falling back to local storage.", err)

        local_path = self.mock_root / bucket / key if bucket else Path(key)
        if not local_path.is_file():
            if Path(uri).is_file():
                local_path = Path(uri)
            else:
                raise FileNotFoundError(f"CSV not found: {uri} (local candidate: {local_path})")
        return pd.read_csv(local_path)

    def write_csv(self, uri: str, df: pd.DataFrame) -> str:
        csv_str = df.to_csv(index=False)
        bucket, key = _parse_s3_uri(uri)

        if bucket and not os.getenv("MOCK_S3_LOCAL_DIR"):
            try:
                client = self._get_client()
                client.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=csv_str.encode("utf-8"),
                    ContentType="text/csv; charset=utf-8",
                )
                return uri
            except (NoCredentialsError, ClientError, BotoCoreError) as err:
                if not self.allow_local_fallback:
                    raise
                logger.warning("S3 write failed (%s), falling back to local storage.", err)

        local_path = self.mock_root / bucket / key if bucket else Path(key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_text(csv_str, encoding="utf-8")
        return str(local_path)

    def list_keys(self, prefix: str) -> list[str]:
        bucket, key_prefix = _parse_s3_uri(prefix)
        keys: list[str] = []

        if bucket and not os.getenv("MOCK_S3_LOCAL_DIR"):
            try:
                client = self._get_client()
                paginator = client.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=bucket, Prefix=key_prefix):
                    for obj in page.get("Contents", []):
                        keys.append(f"s3://{bucket}/{obj['Key']}")
                if keys:
                    return keys
            except (NoCredentialsError, ClientError, BotoCoreError):
                if not self.allow_local_fallback:
                    raise

        # Local search
        target_dir = self.mock_root / bucket / key_prefix if bucket else Path(key_prefix)
        if target_dir.is_dir():
            for p in target_dir.glob("*.json"):
                keys.append(str(p))
        return sorted(keys)
