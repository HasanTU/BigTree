"""Unified AWS Lambda handler and CLI entrypoint for weather data ingestion."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import pandas as pd

from bigtree.ingestion.s3_uploader import upload_raw_data
from bigtree.ingestion.weather_collector import collect_all_weather

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("bigtree.ingestion.handler")


def _find_default_coordinates_file() -> Path | None:
    """Locate bundled sample coordinates CSV if present."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent / "data" / "sample_district_coordinates.csv",
        Path("data/sample_district_coordinates.csv"),
        Path("/var/task/data/sample_district_coordinates.csv"),  # Standard Lambda root
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def run_ingestion_pipeline(
    bucket_name: str,
    start_date: str = "2023-04-01",
    end_date: str = "2023-04-30",
    coordinates_csv_path: str | Path | None = None,
    s3_coordinates_key: str | None = None,
    s3_prefix: str = "raw/weather",
    allow_local_fallback: bool = True,
) -> dict[str, Any]:
    """Execute the end-to-end weather ingestion pipeline.

    Args:
        bucket_name: Target S3 bucket name.
        start_date: Start date for historical weather (YYYY-MM-DD).
        end_date: End date for historical weather (YYYY-MM-DD).
        coordinates_csv_path: Local filepath to district coordinates CSV.
        s3_coordinates_key: Optional S3 key to download coordinates from if provided by Person 2.
        s3_prefix: Prefix in S3 bucket for weather files (defaults to 'raw/weather').
        allow_local_fallback: Whether to mirror to local filesystem if S3 is unavailable.

    Returns:
        Summary dict containing execution metrics and manifest.
    """
    start_time = datetime.now(timezone.utc)
    logger.info("Starting Dubaimai weather ingestion for period: %s to %s", start_date, end_date)

    # 1. Resolve coordinates DataFrame
    df: pd.DataFrame
    if s3_coordinates_key:
        logger.info("Downloading district coordinates from s3://%s/%s", bucket_name, s3_coordinates_key)
        s3_client = boto3.client("s3")
        obj = s3_client.get_object(Bucket=bucket_name, Key=s3_coordinates_key)
        df = pd.read_csv(obj["Body"])
    elif coordinates_csv_path and Path(coordinates_csv_path).is_file():
        logger.info("Loading district coordinates from %s", coordinates_csv_path)
        df = pd.read_csv(coordinates_csv_path)
    else:
        bundled = _find_default_coordinates_file()
        if bundled:
            logger.info("Loading bundled default coordinates from %s", bundled)
            df = pd.read_csv(bundled)
        else:
            raise FileNotFoundError(
                "No district coordinates CSV found. Provide --csv or set s3_coordinates_key."
            )

    logger.info("Loaded %d district coordinate rows.", len(df))

    # 2. Batch collect weather data from Open-Meteo
    batch_results = collect_all_weather(
        districts=df,
        start_date=start_date,
        end_date=end_date,
    )

    # 3. Upload each district payload to S3
    uploaded_keys: list[str] = []
    success_count = 0
    failure_count = 0

    clean_prefix = s3_prefix.strip("/")
    for result in batch_results:
        meta = result.get("metadata", {})
        district_id = meta.get("district_id", "unknown")
        status = meta.get("status")

        if status == "SUCCESS":
            success_count += 1
        else:
            failure_count += 1

        dest_uri = f"s3://{bucket_name}/{clean_prefix}/district_{district_id}.json"
        saved_uri = upload_raw_data(
            data=result,
            destination=dest_uri,
            allow_local_fallback=allow_local_fallback,
        )
        uploaded_keys.append(saved_uri)

    # 4. Generate and upload audit manifest
    end_time = datetime.now(timezone.utc)
    duration_seconds = (end_time - start_time).total_seconds()

    manifest: dict[str, Any] = {
        "pipeline_version": "1.0.0",
        "pipeline_role": "Person 1 - Weather Data Ingestion",
        "started_at_utc": start_time.isoformat(),
        "completed_at_utc": end_time.isoformat(),
        "duration_seconds": duration_seconds,
        "query_parameters": {
            "start_date": start_date,
            "end_date": end_date,
            "target_bucket": bucket_name,
            "target_prefix": clean_prefix,
        },
        "summary": {
            "total_districts": len(batch_results),
            "successful_extractions": success_count,
            "failed_extractions": failure_count,
        },
        "destinations": uploaded_keys,
    }

    manifest_dest = f"s3://{bucket_name}/{clean_prefix}/manifest.json"
    manifest_uri = upload_raw_data(
        data=manifest,
        destination=manifest_dest,
        allow_local_fallback=allow_local_fallback,
    )
    manifest["manifest_uri"] = manifest_uri

    logger.info(
        "Ingestion complete: %d/%d succeeded in %.2fs. Manifest: %s",
        success_count,
        len(batch_results),
        duration_seconds,
        manifest_uri,
    )
    return manifest


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda entrypoint.

    Accepts event configuration overrides or falls back to environment variables.
    """
    logger.info("Lambda invoked with event: %s", json.dumps(event))

    bucket_name = event.get("bucket_name") or os.getenv("S3_BUCKET_NAME", "dubaimai-data")
    start_date = event.get("start_date") or os.getenv("START_DATE", "2023-04-01")
    end_date = event.get("end_date") or os.getenv("END_DATE", "2023-04-30")
    s3_coordinates_key = event.get("s3_coordinates_key") or os.getenv("S3_COORDINATES_KEY")
    s3_prefix = event.get("s3_prefix") or os.getenv("S3_PREFIX", "raw/weather")

    try:
        manifest = run_ingestion_pipeline(
            bucket_name=bucket_name,
            start_date=start_date,
            end_date=end_date,
            s3_coordinates_key=s3_coordinates_key,
            s3_prefix=s3_prefix,
            allow_local_fallback=False,  # Enforce real S3 when in Lambda
        )
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(manifest),
        }
    except Exception as exc:
        logger.exception("Lambda ingestion pipeline failed: %s", exc)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "status": "ERROR",
                "error_message": str(exc),
            }),
        }


def main() -> None:
    """CLI runner for local execution."""
    parser = argparse.ArgumentParser(description="BigTree Weather Data Ingestion CLI")
    parser.add_argument("--bucket", default=os.getenv("S3_BUCKET_NAME", "dubaimai-data"), help="S3 bucket name")
    parser.add_argument("--start-date", default=os.getenv("START_DATE", "2023-04-01"), help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=os.getenv("END_DATE", "2023-04-30"), help="End date (YYYY-MM-DD)")
    parser.add_argument("--csv", default=None, help="Path to district coordinates CSV")
    parser.add_argument("--prefix", default="raw/weather", help="S3 destination prefix")

    args = parser.parse_args()
    manifest = run_ingestion_pipeline(
        bucket_name=args.bucket,
        start_date=args.start_date,
        end_date=args.end_date,
        coordinates_csv_path=args.csv,
        s3_prefix=args.prefix,
        allow_local_fallback=True,
    )
    print(json.dumps(manifest["summary"], indent=2))


if __name__ == "__main__":
    main()
