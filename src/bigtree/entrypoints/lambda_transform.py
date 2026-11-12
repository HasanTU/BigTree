"""AWS Lambda entrypoint for Data Transformation & Quality Validation task."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from bigtree.adapters.s3_storage import S3StorageAdapter
from bigtree.use_cases.transform_and_validate import TransformAndValidateDatasetUseCase

logger = logging.getLogger("bigtree.entrypoints.lambda_transform")
logging.basicConfig(level=logging.INFO)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Step Functions task handler for Transformation."""
    logger.info("Transform Lambda invoked with event: %s", json.dumps(event))

    bucket_name = event.get("bucket_name") or os.getenv("S3_BUCKET_NAME", "dubaimai-data")
    raw_prefix = event.get("raw_prefix", "raw/weather")
    green_key = event.get("green_space_key", "data/green_space.csv")
    coords_key = event.get("coordinates_key", "spatial/district_coordinates.csv")

    curated_key = event.get("curated_key", "curated/district_analysis.csv")
    rejected_key = event.get("rejected_key", "not_pass/rejected_records.csv")
    manifest_key = event.get("transformation_manifest_key", "curated/manifest.json")

    storage = S3StorageAdapter(allow_local_fallback=False)
    use_case = TransformAndValidateDatasetUseCase(storage=storage)

    # 1. Resolve raw weather files
    raw_files = storage.list_keys(f"s3://{bucket_name}/{raw_prefix}/district_")
    if not raw_files:
        # Fallback to local files if testing locally
        storage.allow_local_fallback = True
        raw_files = storage.list_keys(f"s3://{bucket_name}/{raw_prefix}")

    # Fallback paths for green space and coordinates if relative
    green_uri = f"s3://{bucket_name}/{green_key}" if not green_key.startswith("s3://") else green_key
    coords_uri = f"s3://{bucket_name}/{coords_key}" if not coords_key.startswith("s3://") else coords_key

    curated_uri = f"s3://{bucket_name}/{curated_key}"
    rejected_uri = f"s3://{bucket_name}/{rejected_key}"
    manifest_uri = f"s3://{bucket_name}/{manifest_key}"

    try:
        manifest = use_case.execute(
            raw_weather_files=raw_files,
            green_space_csv_uri=green_uri,
            coordinates_csv_uri=coords_uri,
            curated_output_uri=curated_uri,
            rejected_output_uri=rejected_uri,
            manifest_output_uri=manifest_uri,
        )

        return {
            "statusCode": 200,
            "bucket_name": bucket_name,
            "curated_uri": curated_uri,
            "rejected_uri": rejected_uri,
            "curated_count": manifest["summary"]["curated_records_count"],
            "rejected_count": manifest["summary"]["rejected_records_count"],
            "manifest": manifest,
        }
    except Exception as exc:
        logger.exception("Transformation failed: %s", exc)
        return {
            "statusCode": 500,
            "status": "ERROR",
            "error_message": str(exc),
        }
