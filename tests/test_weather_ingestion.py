"""Unit and integration tests for BigTree weather ingestion module."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import requests
import responses

from bigtree.ingestion.s3_uploader import upload_raw_data
from bigtree.ingestion.weather_client import (
    OPEN_METEO_ARCHIVE_URL,
    WeatherRateLimitError,
    WeatherServerError,
    WeatherTimeoutError,
    WeatherValidationError,
    fetch_weather,
)
from bigtree.ingestion.weather_collector import collect_all_weather


def test_validate_inputs_bounds() -> None:
    """Ensure coordinates and date ranges are properly checked before API calls."""
    with pytest.raises(WeatherValidationError, match="Latitude must be within"):
        fetch_weather(latitude=91.0, longitude=100.5, start_date="2023-04-01", end_date="2023-04-05")

    with pytest.raises(WeatherValidationError, match="Longitude must be within"):
        fetch_weather(latitude=13.7, longitude=185.0, start_date="2023-04-01", end_date="2023-04-05")

    with pytest.raises(WeatherValidationError, match="Invalid start_date"):
        fetch_weather(latitude=13.7, longitude=100.5, start_date="2023/04/01", end_date="2023-04-05")

    with pytest.raises(WeatherValidationError, match="cannot be later than"):
        fetch_weather(latitude=13.7, longitude=100.5, start_date="2023-04-10", end_date="2023-04-05")


@responses.activate
def test_fetch_weather_success() -> None:
    """Verify clean 200 OK response parsing."""
    mock_payload = {
        "latitude": 13.75,
        "longitude": 100.5,
        "timezone": "Asia/Bangkok",
        "hourly": {
            "time": ["2023-04-01T00:00", "2023-04-01T01:00"],
            "temperature_2m": [28.5, 28.2],
        },
    }
    responses.add(
        responses.GET,
        OPEN_METEO_ARCHIVE_URL,
        json=mock_payload,
        status=200,
    )

    data = fetch_weather(
        latitude=13.75,
        longitude=100.5,
        start_date="2023-04-01",
        end_date="2023-04-02",
    )
    assert data["latitude"] == 13.75
    assert data["hourly"]["temperature_2m"] == [28.5, 28.2]


@responses.activate
def test_fetch_weather_400_bad_request() -> None:
    """Verify 400 Bad Request raises WeatherValidationError."""
    responses.add(
        responses.GET,
        OPEN_METEO_ARCHIVE_URL,
        json={"error": True, "reason": "Invalid parameter"},
        status=400,
    )
    with pytest.raises(WeatherValidationError, match="Open-Meteo 400 Bad Request"):
        fetch_weather(
            latitude=13.75,
            longitude=100.5,
            start_date="2023-04-01",
            end_date="2023-04-02",
        )


@responses.activate
def test_fetch_weather_429_retry_success() -> None:
    """Verify retry handles transient 429 rate limit then recovers on 200."""
    responses.add(
        responses.GET,
        OPEN_METEO_ARCHIVE_URL,
        json={"error": True, "reason": "Limit exceeded"},
        headers={"X-RateLimit-Reset": "0"},
        status=429,
    )
    responses.add(
        responses.GET,
        OPEN_METEO_ARCHIVE_URL,
        json={"latitude": 13.75, "hourly": {"temperature_2m": [30.0]}},
        status=200,
    )

    result = fetch_weather(
        latitude=13.75,
        longitude=100.5,
        start_date="2023-04-01",
        end_date="2023-04-02",
        base_backoff_seconds=0.01,
    )
    assert result["latitude"] == 13.75


@responses.activate
def test_fetch_weather_429_exhaustion() -> None:
    """Verify repeated 429 rate limits raise WeatherRateLimitError after retries."""
    for _ in range(4):
        responses.add(
            responses.GET,
            OPEN_METEO_ARCHIVE_URL,
            json={"error": True, "reason": "Limit exceeded"},
            status=429,
        )

    with pytest.raises(WeatherRateLimitError, match="rate limit exceeded"):
        fetch_weather(
            latitude=13.75,
            longitude=100.5,
            start_date="2023-04-01",
            end_date="2023-04-02",
            max_retries=2,
            base_backoff_seconds=0.01,
        )


@responses.activate
def test_fetch_weather_500_exhaustion() -> None:
    """Verify 5xx server errors raise WeatherServerError after retries."""
    for _ in range(3):
        responses.add(
            responses.GET,
            OPEN_METEO_ARCHIVE_URL,
            body="Internal Server Error",
            status=500,
        )

    with pytest.raises(WeatherServerError, match="server error 500"):
        fetch_weather(
            latitude=13.75,
            longitude=100.5,
            start_date="2023-04-01",
            end_date="2023-04-02",
            max_retries=1,
            base_backoff_seconds=0.01,
        )


@responses.activate
def test_collect_all_weather_resilience() -> None:
    """Verify batch collection processes all districts and captures failures without halting."""
    districts_df = pd.DataFrame([
        {"district_id": "001", "district_name": "Phra Nakhon", "latitude": 13.7563, "longitude": 100.5018},
        {"district_id": "002", "district_name": "Dusit", "latitude": 13.7769, "longitude": 100.5209},
        {"district_id": "003", "district_name": "Bad_Coords", "latitude": "invalid", "longitude": 100.0},
    ])

    # First call succeeds
    responses.add(
        responses.GET,
        OPEN_METEO_ARCHIVE_URL,
        json={"latitude": 13.7563, "hourly": {"temperature_2m": [32.0]}},
        status=200,
    )
    # Second call fails with 500
    for _ in range(3):
        responses.add(
            responses.GET,
            OPEN_METEO_ARCHIVE_URL,
            body="Gateway Timeout",
            status=504,
        )

    results = collect_all_weather(districts_df, start_date="2023-04-01", end_date="2023-04-02")
    assert len(results) == 3

    # District 1: Success
    assert results[0]["metadata"]["status"] == "SUCCESS"
    assert results[0]["raw_response"] is not None

    # District 2: Failed due to 504 server error
    assert results[1]["metadata"]["status"] == "FAILED"
    assert results[1]["metadata"]["error_type"] == "WeatherServerError"
    assert results[1]["raw_response"] is None

    # District 3: Failed due to invalid coordinates conversion
    assert results[2]["metadata"]["status"] == "FAILED"
    assert results[2]["metadata"]["error_type"] == "InvalidCoordinateType"
    assert results[2]["raw_response"] is None


def test_upload_raw_data_local_fallback(tmp_path: Path) -> None:
    """Verify local filesystem fallback when S3 destination is provided."""
    sample_data = {
        "metadata": {"district_id": "001", "status": "SUCCESS"},
        "raw_response": {"test": "data"},
    }

    mock_dir = tmp_path / "s3_mock"
    destination = "s3://dubaimai/raw/weather/district_001.json"

    import os
    os.environ["MOCK_S3_LOCAL_DIR"] = str(mock_dir)
    try:
        saved_path = upload_raw_data(sample_data, destination)
        saved_file = Path(saved_path)
        assert saved_file.exists()
        loaded = json.loads(saved_file.read_text(encoding="utf-8"))
        assert loaded["metadata"]["district_id"] == "001"
    finally:
        os.environ.pop("MOCK_S3_LOCAL_DIR", None)
