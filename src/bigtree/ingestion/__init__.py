"""BigTree Ingestion Module.

Handles Open-Meteo Historical Weather API queries, batch collection
across Bangkok districts, and raw object storage in S3.
"""

from bigtree.ingestion.s3_uploader import upload_raw_data
from bigtree.ingestion.weather_client import (
    WeatherAPIError,
    WeatherRateLimitError,
    WeatherServerError,
    WeatherTimeoutError,
    WeatherValidationError,
    fetch_weather,
)
from bigtree.ingestion.weather_collector import collect_all_weather

__all__ = [
    "fetch_weather",
    "collect_all_weather",
    "upload_raw_data",
    "WeatherAPIError",
    "WeatherValidationError",
    "WeatherRateLimitError",
    "WeatherServerError",
    "WeatherTimeoutError",
]
