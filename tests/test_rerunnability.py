"""Idempotency and Rerunnability tests.

Guarantees that executing the pipeline multiple times produces deterministic,
identical results without side effects, state pollution, or record duplication.
"""

from __future__ import annotations

import pandas as pd

from bigtree.adapters.in_memory_storage import InMemoryStorageAdapter
from bigtree.use_cases.transform_and_validate import TransformAndValidateDatasetUseCase


def test_transformation_pipeline_is_rerunnable_and_idempotent() -> None:
    mock_weather = {
        "metadata": {"district_id": "001", "district_name": "Bang Rak"},
        "raw_response": {
            "hourly": {
                "time": ["2023-04-01T00:00", "2023-04-01T01:00"],
                "temperature_2m": [30.0, 32.0] * 12,
            }
        },
    }
    green_df = pd.DataFrame([{"district": "Bang Rak", "green_area_sqm": 45000.0, "parks_count": 3}])
    coords_df = pd.DataFrame([{"district": "Bang Rak", "latitude": 13.72, "longitude": 100.52}])

    storage = InMemoryStorageAdapter({
        "raw/weather/district_001.json": mock_weather,
        "data/green_space.csv": green_df,
        "data/coords.csv": coords_df,
    })

    use_case = TransformAndValidateDatasetUseCase(storage=storage)

    # Run 1
    manifest_1 = use_case.execute(
        raw_weather_files=["raw/weather/district_001.json"],
        green_space_csv_uri="data/green_space.csv",
        coordinates_csv_uri="data/coords.csv",
        curated_output_uri="curated/district_analysis.csv",
        rejected_output_uri="not_pass/rejected_records.csv",
        manifest_output_uri="curated/manifest.json",
    )
    curated_1 = storage.read_csv("curated/district_analysis.csv")

    # Run 2 (Rerun with same input)
    manifest_2 = use_case.execute(
        raw_weather_files=["raw/weather/district_001.json"],
        green_space_csv_uri="data/green_space.csv",
        coordinates_csv_uri="data/coords.csv",
        curated_output_uri="curated/district_analysis.csv",
        rejected_output_uri="not_pass/rejected_records.csv",
        manifest_output_uri="curated/manifest.json",
    )
    curated_2 = storage.read_csv("curated/district_analysis.csv")

    # Verify identical counts and values (Idempotency guarantee)
    assert len(curated_1) == 1
    assert len(curated_2) == 1
    assert manifest_1["summary"]["curated_records_count"] == manifest_2["summary"]["curated_records_count"]
    pd.testing.assert_frame_equal(curated_1, curated_2)
