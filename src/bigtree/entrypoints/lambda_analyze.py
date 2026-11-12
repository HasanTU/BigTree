"""AWS Lambda entrypoint for Statistical Research Analysis task."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from bigtree.adapters.s3_storage import S3StorageAdapter
from bigtree.use_cases.analyze_research_questions import AnalyzeResearchQuestionsUseCase

logger = logging.getLogger("bigtree.entrypoints.lambda_analyze")
logging.basicConfig(level=logging.INFO)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Step Functions task handler for Analysis."""
    logger.info("Analyze Lambda invoked with event: %s", json.dumps(event))

    bucket_name = event.get("bucket_name") or os.getenv("S3_BUCKET_NAME", "dubaimai-data")
    curated_uri = event.get("curated_uri") or f"s3://{bucket_name}/curated/district_analysis.csv"
    metrics_uri = event.get("metrics_uri") or f"s3://{bucket_name}/reports/research_metrics.json"

    storage = S3StorageAdapter(allow_local_fallback=False)
    use_case = AnalyzeResearchQuestionsUseCase(storage=storage)

    try:
        results = use_case.execute(
            curated_data_uri=curated_uri,
            output_metrics_uri=metrics_uri,
            visualizations_dir="/tmp/visualizations",
        )

        return {
            "statusCode": 200,
            "bucket_name": bucket_name,
            "metrics_uri": metrics_uri,
            "q1_summary": results["q1_temporal_analysis"],
            "q2_summary": results["q2_group_comparison"],
            "q3_summary": results["q3_correlation_analysis"],
        }
    except Exception as exc:
        logger.exception("Analysis failed: %s", exc)
        return {
            "statusCode": 500,
            "status": "ERROR",
            "error_message": str(exc),
        }
