"""Open-Meteo Historical Weather API client with robust error handling and retries."""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DEFAULT_TIMEZONE = "Asia/Bangkok"


class WeatherAPIError(Exception):
    """Base exception for all weather API related failures."""

    def __init__(self, message: str, status_code: int | None = None, response_body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class WeatherValidationError(WeatherAPIError):
    """Raised when client parameters (coordinates, date range) are invalid."""


class WeatherRateLimitError(WeatherAPIError):
    """Raised when Open-Meteo rate limit (HTTP 429) is exceeded."""


class WeatherTimeoutError(WeatherAPIError):
    """Raised when network request times out after multiple attempts."""


class WeatherServerError(WeatherAPIError):
    """Raised when Open-Meteo returns a 5xx server-side error."""


def _validate_inputs(latitude: float, longitude: float, start_date: str, end_date: str) -> None:
    """Validate coordinate bounds and date range syntax upfront."""
    if not (-90.0 <= latitude <= 90.0):
        raise WeatherValidationError(f"Latitude must be within [-90.0, 90.0]. Received: {latitude}")
    if not (-180.0 <= longitude <= 180.0):
        raise WeatherValidationError(f"Longitude must be within [-180.0, 180.0]. Received: {longitude}")

    date_format = "%Y-%m-%d"
    try:
        dt_start = datetime.strptime(start_date, date_format)
    except ValueError as exc:
        raise WeatherValidationError(f"Invalid start_date '{start_date}'. Must be YYYY-MM-DD.") from exc

    try:
        dt_end = datetime.strptime(end_date, date_format)
    except ValueError as exc:
        raise WeatherValidationError(f"Invalid end_date '{end_date}'. Must be YYYY-MM-DD.") from exc

    if dt_start > dt_end:
        raise WeatherValidationError(
            f"start_date '{start_date}' cannot be later than end_date '{end_date}'."
        )


def fetch_weather(
    latitude: float,
    longitude: float,
    start_date: str,
    end_date: str,
    hourly: str = "temperature_2m",
    daily: str | None = None,
    timezone: str = DEFAULT_TIMEZONE,
    max_retries: int = 3,
    base_backoff_seconds: float = 1.0,
    timeout: tuple[float, float] = (5.0, 15.0),
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Fetch historical weather data from Open-Meteo with retries and rate-limit handling.

    Args:
        latitude: Geographic latitude in decimal degrees.
        longitude: Geographic longitude in decimal degrees.
        start_date: Start date string formatted as YYYY-MM-DD.
        end_date: End date string formatted as YYYY-MM-DD.
        hourly: Comma-separated hourly variables (defaults to 'temperature_2m').
        daily: Optional comma-separated daily aggregations.
        timezone: Timezone string (defaults to 'Asia/Bangkok').
        max_retries: Max retry attempts for transient errors (429, 5xx, timeouts).
        base_backoff_seconds: Initial backoff delay for exponential backoff.
        timeout: Tuple of (connect_timeout, read_timeout) in seconds.
        session: Optional pre-configured requests.Session.

    Returns:
        dict containing the raw JSON response payload from Open-Meteo.

    Raises:
        WeatherValidationError: Invalid coordinates or date range.
        WeatherRateLimitError: Rate limit hit and exhausted all retries.
        WeatherTimeoutError: Connection or read timeout exhausted retries.
        WeatherServerError: 5xx server errors exhausted retries.
        WeatherAPIError: Unhandled API or network errors.
    """
    _validate_inputs(latitude=latitude, longitude=longitude, start_date=start_date, end_date=end_date)

    params: dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "hourly": hourly,
        "timezone": timezone,
    }
    if daily:
        params["daily"] = daily

    requester = session or requests

    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            logger.debug(
                "Requesting Open-Meteo archive (attempt %d/%d) for lat=%f, lon=%f",
                attempt + 1,
                max_retries + 1,
                latitude,
                longitude,
            )
            response = requester.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=timeout)

            # Handle 200 OK
            if response.status_code == 200:
                try:
                    payload = response.json()
                    return payload
                except ValueError as json_exc:
                    raise WeatherAPIError(
                        "Received non-JSON response from Open-Meteo",
                        status_code=200,
                        response_body=response.text[:200],
                    ) from json_exc

            # Inspect error payload if provided
            try:
                error_body = response.json()
                reason = error_body.get("reason", response.text)
            except Exception:
                error_body = None
                reason = response.text

            # Handle 400 Bad Request (permanent validation error from API)
            if response.status_code == 400:
                raise WeatherValidationError(
                    f"Open-Meteo 400 Bad Request: {reason}",
                    status_code=400,
                    response_body=error_body,
                )

            # Handle 429 Rate Limit Exceeded
            if response.status_code == 429:
                reset_header = response.headers.get("X-RateLimit-Reset")
                sleep_time = base_backoff_seconds * (2**attempt) + random.uniform(0.1, 0.5)
                if reset_header:
                    try:
                        reset_timestamp = float(reset_header)
                        wait_seconds = max(0.0, reset_timestamp - time.time())
                        if 0 < wait_seconds < 60:
                            sleep_time = wait_seconds
                    except ValueError:
                        pass

                logger.warning(
                    "Open-Meteo 429 Rate Limit reached: '%s'. Retrying in %.2fs (attempt %d/%d)",
                    reason,
                    sleep_time,
                    attempt + 1,
                    max_retries + 1,
                )
                if attempt == max_retries:
                    raise WeatherRateLimitError(
                        f"Open-Meteo rate limit exceeded: {reason}",
                        status_code=429,
                        response_body=error_body,
                    )
                time.sleep(sleep_time)
                continue

            # Handle 5xx Server Outages
            if response.status_code >= 500:
                sleep_time = base_backoff_seconds * (2**attempt) + random.uniform(0.1, 0.5)
                logger.warning(
                    "Open-Meteo 5xx error (%d): '%s'. Retrying in %.2fs (attempt %d/%d)",
                    response.status_code,
                    reason,
                    sleep_time,
                    attempt + 1,
                    max_retries + 1,
                )
                if attempt == max_retries:
                    raise WeatherServerError(
                        f"Open-Meteo server error {response.status_code}: {reason}",
                        status_code=response.status_code,
                        response_body=error_body,
                    )
                time.sleep(sleep_time)
                continue

            # Other unexpected 4xx status codes
            raise WeatherAPIError(
                f"Open-Meteo HTTP {response.status_code} Error: {reason}",
                status_code=response.status_code,
                response_body=error_body,
            )

        except requests.exceptions.Timeout as timeout_exc:
            last_error = timeout_exc
            sleep_time = base_backoff_seconds * (2**attempt) + random.uniform(0.1, 0.5)
            logger.warning(
                "Open-Meteo request timeout. Retrying in %.2fs (attempt %d/%d)",
                sleep_time,
                attempt + 1,
                max_retries + 1,
            )
            if attempt == max_retries:
                raise WeatherTimeoutError(
                    f"Open-Meteo request timed out after {max_retries + 1} attempts"
                ) from timeout_exc
            time.sleep(sleep_time)

        except requests.exceptions.ConnectionError as conn_exc:
            last_error = conn_exc
            sleep_time = base_backoff_seconds * (2**attempt) + random.uniform(0.1, 0.5)
            logger.warning(
                "Open-Meteo connection error. Retrying in %.2fs (attempt %d/%d)",
                sleep_time,
                attempt + 1,
                max_retries + 1,
            )
            if attempt == max_retries:
                raise WeatherAPIError(
                    f"Failed to connect to Open-Meteo: {conn_exc}"
                ) from conn_exc
            time.sleep(sleep_time)

    raise WeatherAPIError(f"Unexpected failure fetching weather data: {last_error}")
