"""Orchestrates batch weather data collection across Bangkok districts."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

from bigtree.ingestion.weather_client import (
    WeatherAPIError,
    fetch_weather,
)

logger = logging.getLogger(__name__)


def _normalize_column_name(df: pd.DataFrame, candidates: list[str]) -> str:
    """Find the first matching column name from a list of candidates."""
    lower_map = {col.lower(): col for col in df.columns}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    raise KeyError(f"None of {candidates} found in DataFrame columns: {list(df.columns)}")


def collect_all_weather(
    districts: pd.DataFrame,
    start_date: str = "2023-04-01",
    end_date: str = "2023-04-30",
    hourly: str = "temperature_2m",
    daily: str | None = None,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Iterate through district coordinates, query Open-Meteo, and record metadata and failures.

    Args:
        districts: DataFrame containing at least district name/id and coordinates.
        start_date: Start date formatted as YYYY-MM-DD (defaults to April 2023).
        end_date: End date formatted as YYYY-MM-DD.
        hourly: Hourly weather variable(s) (defaults to 'temperature_2m').
        daily: Optional daily summary metrics.
        session: Optional pre-configured requests session.

    Returns:
        list of dicts, each containing:
            - 'metadata': District info, coordinate values, query bounds, timestamp, and status.
            - 'raw_response': The unaltered Open-Meteo response dict (or None if failed).
    """
    if districts.empty:
        logger.warning("Empty districts DataFrame passed to collect_all_weather.")
        return []

    lat_col = _normalize_column_name(districts, ["latitude", "lat", "y"])
    lon_col = _normalize_column_name(districts, ["longitude", "lon", "lng", "x"])

    # District name/id resolution
    has_name = any(c.lower() in [col.lower() for col in districts.columns] for c in ["district", "district_name", "dname", "name_th", "name_en"])
    name_col = _normalize_column_name(districts, ["district", "district_name", "dname", "name_th", "name_en"]) if has_name else None

    has_id = any(c.lower() in [col.lower() for col in districts.columns] for c in ["district_id", "id", "dcode"])
    id_col = _normalize_column_name(districts, ["district_id", "id", "dcode"]) if has_id else None

    results: list[dict[str, Any]] = []
    success_count = 0
    failure_count = 0

    req_session = session or requests.Session()

    for idx, row in districts.iterrows():
        district_id = str(row[id_col]) if id_col else f"{idx + 1:03d}"
        district_name = str(row[name_col]) if name_col else f"District_{district_id}"

        try:
            latitude = float(row[lat_col])
            longitude = float(row[lon_col])
        except (ValueError, TypeError) as conv_err:
            logger.error("District %s has invalid coordinates: %s", district_name, conv_err)
            failure_count += 1
            results.append({
                "metadata": {
                    "district_id": district_id,
                    "district_name": district_name,
                    "latitude": row[lat_col],
                    "longitude": row[lon_col],
                    "start_date": start_date,
                    "end_date": end_date,
                    "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                    "status": "FAILED",
                    "error_type": "InvalidCoordinateType",
                    "error_message": str(conv_err),
                },
                "raw_response": None,
            })
            continue

        retrieval_time = datetime.now(timezone.utc).isoformat()

        try:
            raw_payload = fetch_weather(
                latitude=latitude,
                longitude=longitude,
                start_date=start_date,
                end_date=end_date,
                hourly=hourly,
                daily=daily,
                session=req_session,
            )
            success_count += 1
            results.append({
                "metadata": {
                    "district_id": district_id,
                    "district_name": district_name,
                    "latitude": latitude,
                    "longitude": longitude,
                    "start_date": start_date,
                    "end_date": end_date,
                    "retrieved_at_utc": retrieval_time,
                    "status": "SUCCESS",
                },
                "raw_response": raw_payload,
            })
            logger.info("Successfully fetched weather for district: %s (%s)", district_name, district_id)

        except WeatherAPIError as api_err:
            failure_count += 1
            logger.error(
                "Failed to fetch weather for district %s (%s): %s",
                district_name,
                district_id,
                api_err,
            )
            results.append({
                "metadata": {
                    "district_id": district_id,
                    "district_name": district_name,
                    "latitude": latitude,
                    "longitude": longitude,
                    "start_date": start_date,
                    "end_date": end_date,
                    "retrieved_at_utc": retrieval_time,
                    "status": "FAILED",
                    "error_type": api_err.__class__.__name__,
                    "error_message": str(api_err),
                    "status_code": api_err.status_code,
                },
                "raw_response": None,
            })

    logger.info(
        "Batch collection finished. Total=%d, Success=%d, Failed=%d",
        len(districts),
        success_count,
        failure_count,
    )
    return results
