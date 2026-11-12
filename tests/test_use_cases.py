"""Integration tests for Use Cases using the hermetic InMemoryStorageAdapter.

100% offline, zero network, zero external API dependencies.
"""

from __future__ import annotations

import pandas as pd
import pytest

from bigtree.adapters.in_memory_storage import InMemoryStorageAdapter
from bigtree.transformation import validate_data
from bigtree.use_cases.analyze_research_questions import AnalyzeResearchQuestionsUseCase
from bigtree.use_cases.transform_and_validate import TransformAndValidateDatasetUseCase


def test_transform_and_validate_use_case_in_memory() -> None:
    # Set up in-memory fixture files
    mock_weather_1 = {
        "metadata": {"district_id": "001", "district_name": "Bang Rak"},
        "raw_response": {
            "hourly": {
                "time": ["2023-04-01T00:00", "2023-04-01T01:00", "2023-04-01T02:00"],
                "temperature_2m": [28.0, 32.0, 36.0] * 8,  # 24 readings
            }
        },
    }
    mock_weather_2 = {
        "metadata": {"district_id": "002", "district_name": "Dusit"},
        "raw_response": {
            "hourly": {
                "time": ["2023-04-01T00:00", "2023-04-01T01:00"],
                "temperature_2m": [27.0, 31.0, 34.0] * 8,
            }
        },
    }
    mock_weather_corrupt = {
        "metadata": {"district_id": "003", "district_name": "Broken District"},
        "raw_response": {
            "hourly": {
                "time": ["2023-04-01T00:00"],
                "temperature_2m": [60.0] * 24,  # Violates temperature plausibility
            }
        },
    }

    green_df = pd.DataFrame([
        {"district": "Bang Rak", "green_area_sqm": 50000.0, "parks_count": 4},
        {"district": "Dusit", "green_area_sqm": 120000.0, "parks_count": 6},
        {"district": "Broken District", "green_area_sqm": 30000.0, "parks_count": 1},
    ])

    coords_df = pd.DataFrame([
        {"district": "Bang Rak", "latitude": 13.72, "longitude": 100.52},
        {"district": "Dusit", "latitude": 13.77, "longitude": 100.52},
        {"district": "Broken District", "latitude": 13.70, "longitude": 100.50},
    ])

    storage = InMemoryStorageAdapter({
        "raw/weather/w1.json": mock_weather_1,
        "raw/weather/w2.json": mock_weather_2,
        "raw/weather/w3.json": mock_weather_corrupt,
        "data/green_space.csv": green_df,
        "data/coords.csv": coords_df,
    })

    use_case = TransformAndValidateDatasetUseCase(storage=storage)
    manifest = use_case.execute(
        raw_weather_files=["raw/weather/w1.json", "raw/weather/w2.json", "raw/weather/w3.json"],
        green_space_csv_uri="data/green_space.csv",
        coordinates_csv_uri="data/coords.csv",
        curated_output_uri="curated/district_analysis.csv",
        rejected_output_uri="not_pass/rejected_records.csv",
        manifest_output_uri="curated/manifest.json",
    )

    assert manifest["summary"]["curated_records_count"] == 2
    assert manifest["summary"]["rejected_records_count"] == 1

    curated_df = storage.read_csv("curated/district_analysis.csv")
    assert len(curated_df) == 2
    assert set(curated_df["district"]) == {"Bang Rak", "Dusit"}

    rejected_df = storage.read_csv("not_pass/rejected_records.csv")
    assert len(rejected_df) == 1
    assert rejected_df.iloc[0]["district"] == "Broken District"
    assert "outside plausible bounds" in rejected_df.iloc[0]["rejection_reasons"]


def test_analyze_research_questions_use_case_in_memory() -> None:
    curated_df = pd.DataFrame([
        {"district": f"District_{i}", "avg_temperature": 34.0 - (i * 0.5), "max_temperature": 38.0 - (i * 0.5), "min_temperature": 26.0, "green_area_sqm": 10000.0 * (i + 1), "parks_count": i + 1, "reading_count": 24}
        for i in range(10)
    ])

    storage = InMemoryStorageAdapter({
        "curated/district_analysis.csv": curated_df,
    })

    use_case = AnalyzeResearchQuestionsUseCase(storage=storage)
    results = use_case.execute(
        curated_data_uri="curated/district_analysis.csv",
        output_metrics_uri="reports/research_metrics.json",
        visualizations_dir=None,  # No disk plotting needed for pure unit test
    )

    assert results["curated_records_analyzed"] == 10

    # Q1 checks
    q1 = results["q1_temporal_analysis"]
    assert q1["bangkok_overall_mean_temp_celsius"] > 25.0

    # Q2 checks
    q2 = results["q2_group_comparison"]
    assert q2["high_green_districts_count"] > 0
    assert q2["low_green_districts_count"] > 0
    assert q2["temperature_delta_celsius"] > 0

    # Q3 checks
    q3 = results["q3_correlation_analysis"]
    assert q3["pearson_r"] < -0.9  # Synthetic slope was negative
    assert q3["r_squared"] > 0.8
    assert "ACADEMIC LIMITATION" in q3["academic_disclaimer"]

    # Verify report saved to memory
    saved_metrics = storage.read_json("reports/research_metrics.json")
    assert saved_metrics["curated_records_analyzed"] == 10


def test_validate_data_facade() -> None:
    test_df = pd.DataFrame([
        {"district": "Phra Nakhon", "avg_temperature": 32.0, "max_temperature": 36.0, "min_temperature": 27.0, "green_area_sqm": 20000.0, "parks_count": 2, "reading_count": 24},
        {"district": "Bad_District", "avg_temperature": 75.0, "max_temperature": 80.0, "min_temperature": 70.0, "green_area_sqm": -50.0, "parks_count": -1, "reading_count": 24},
    ])

    curated, rejected = validate_data(test_df)
    assert len(curated) == 1
    assert curated.iloc[0]["district"] == "Phra Nakhon"
    assert len(rejected) == 1
    assert rejected.iloc[0]["district"] == "Bad_District"
