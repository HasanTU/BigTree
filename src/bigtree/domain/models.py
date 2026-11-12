"""Domain entities and value objects for the Dubaimai data pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DistrictCoordinates:
    """Geographic representative coordinates for a district."""

    district_name: str
    latitude: float
    longitude: float
    district_id: str | None = None


@dataclass(frozen=True)
class GreenSpaceRecord:
    """Green space indicators for a district."""

    district_name: str
    green_area_sqm: float
    parks_count: int


@dataclass(frozen=True)
class WeatherAggregates:
    """Aggregated temperature statistics derived from hourly raw observations."""

    district_name: str
    avg_temperature: float
    max_temperature: float
    min_temperature: float
    std_temperature: float
    p90_temperature: float
    reading_count: int
    diurnal_temperature_range: float


@dataclass(frozen=True)
class QualityCheckResult:
    """Outcome of business rule validation for a single district record."""

    is_valid: bool
    rejection_reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class IntegratedDistrictRecord:
    """Merged record combining weather aggregates and green space indicators."""

    district_name: str
    avg_temperature: float
    max_temperature: float
    min_temperature: float
    std_temperature: float
    p90_temperature: float
    diurnal_temperature_range: float
    green_area_sqm: float
    parks_count: int
    reading_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "district": self.district_name,
            "avg_temperature": round(self.avg_temperature, 2),
            "max_temperature": round(self.max_temperature, 2),
            "min_temperature": round(self.min_temperature, 2),
            "std_temperature": round(self.std_temperature, 2),
            "p90_temperature": round(self.p90_temperature, 2),
            "diurnal_temperature_range": round(self.diurnal_temperature_range, 2),
            "green_area_sqm": round(self.green_area_sqm, 2),
            "parks_count": self.parks_count,
            "reading_count": self.reading_count,
        }


@dataclass(frozen=True)
class RejectedDistrictRecord:
    """Record that failed one or more business quality rules."""

    district_name: str
    rejection_reasons: tuple[str, ...]
    raw_data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "district": self.district_name,
            "rejection_reasons": "; ".join(self.rejection_reasons),
            **{f"raw_{k}": v for k, v in self.raw_data.items()},
        }


@dataclass(frozen=True)
class Q1TemporalAnalysisResult:
    """Answers Q1: How does temperature change over time?"""

    time_period: str
    bangkok_mean_temp: float
    bangkok_max_temp: float
    bangkok_min_temp: float
    mean_diurnal_range: float
    peak_heat_hour: int
    coolest_hour: int
    hourly_averages: dict[int, float]


@dataclass(frozen=True)
class Q2GroupComparisonResult:
    """Answers Q2: Do high and low green-space districts have different temperatures?"""

    high_green_count: int
    low_green_count: int
    high_green_mean_temp: float
    low_green_mean_temp: float
    temperature_difference: float
    t_statistic: float | None
    p_value: float
    mann_whitney_u: float
    is_statistically_significant: bool
    summary_text: str


@dataclass(frozen=True)
class Q3CorrelationResult:
    """Answers Q3: How strong is the relationship between green space and temperature?"""

    pearson_r: float
    pearson_p_value: float
    spearman_rho: float
    spearman_p_value: float
    r_squared: float
    regression_slope: float
    regression_intercept: float
    cooling_per_100k_sqm: float
    academic_disclaimer: str
