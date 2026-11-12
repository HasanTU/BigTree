"""Unified Command-Line Interface for running the entire Dubaimai pipeline."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from bigtree.adapters.s3_storage import S3StorageAdapter
from bigtree.ingestion.handler import run_ingestion_pipeline
from bigtree.use_cases.analyze_research_questions import AnalyzeResearchQuestionsUseCase
from bigtree.use_cases.transform_and_validate import TransformAndValidateDatasetUseCase

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("bigtree.cli")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dubaimai Big Data Pipeline Runner")
    parser.add_argument("command", choices=["ingest", "transform", "analyze", "all"], default="all", nargs="?")
    parser.add_argument("--bucket", default="dubaimai-data", help="S3 bucket or local mirror namespace")
    parser.add_argument("--start-date", default="2023-04-01", help="Weather query start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default="2023-04-30", help="Weather query end date (YYYY-MM-DD)")
    parser.add_argument("--coords", default="data/district_coordinates.csv", help="Path to district coordinates CSV")
    parser.add_argument("--green-csv", default="data/green_space.csv", help="Path to green space CSV")
    parser.add_argument("--reports-dir", default="reports/visualizations", help="Directory for generated visualizations")

    args = parser.parse_args()
    storage = S3StorageAdapter(allow_local_fallback=True)

    bucket = args.bucket
    raw_prefix = f"s3://{bucket}/raw/weather"
    curated_uri = f"s3://{bucket}/curated/district_analysis.csv"
    rejected_uri = f"s3://{bucket}/not_pass/rejected_records.csv"
    metrics_uri = f"s3://{bucket}/reports/research_metrics.json"

    # Step 1: Ingestion
    if args.command in ["ingest", "all"]:
        logger.info("=== STEP 1: Weather Ingestion (Person 1) ===")
        run_ingestion_pipeline(
            bucket_name=bucket,
            start_date=args.start_date,
            end_date=args.end_date,
            coordinates_csv_path=args.coords,
            allow_local_fallback=True,
        )

    # Step 2: Transformation
    if args.command in ["transform", "all"]:
        logger.info("=== STEP 2: Data Transformation & Validation (Person 3) ===")
        raw_files = storage.list_keys(raw_prefix)
        transform_uc = TransformAndValidateDatasetUseCase(storage=storage)
        res_transform = transform_uc.execute(
            raw_weather_files=raw_files,
            green_space_csv_uri=args.green_csv,
            coordinates_csv_uri=args.coords,
            curated_output_uri=curated_uri,
            rejected_output_uri=rejected_uri,
            manifest_output_uri=f"s3://{bucket}/curated/manifest.json",
        )
        print("\n--- Transformation Summary ---")
        print(json.dumps(res_transform["summary"], indent=2))

    # Step 3: Analysis
    if args.command in ["analyze", "all"]:
        logger.info("=== STEP 3: Statistical Analysis & Visualization (Person 4) ===")
        analyze_uc = AnalyzeResearchQuestionsUseCase(storage=storage)
        res_analysis = analyze_uc.execute(
            curated_data_uri=curated_uri,
            output_metrics_uri=metrics_uri,
            visualizations_dir=args.reports_dir,
        )
        print("\n--- Research Questions Findings ---")
        print("Q1:", res_analysis["q1_temporal_analysis"]["findings"])
        print("Q2:", res_analysis["q2_group_comparison"]["findings"])
        print("Q3:", res_analysis["q3_correlation_analysis"]["findings"])
        print("\nCharts generated:", res_analysis["generated_visualizations"])


if __name__ == "__main__":
    main()
