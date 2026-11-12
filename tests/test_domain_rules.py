"""Pure unit tests for domain business rules and statistical formulas.

100% offline, zero network I/O, zero external API dependencies.
"""

from __future__ import annotations

import pytest

from bigtree.domain.models import IntegratedDistrictRecord
from bigtree.domain.rules import (
    DataCompletenessRule,
    DefaultCuratedQualityPolicy,
    GreenSpaceIndicatorRule,
    TemperaturePlausibilityRule,
)
from bigtree.domain.statistics import (
    compare_green_space_cohorts,
    compute_bivariate_correlation,
    compute_diurnal_temperature_range,
)


def _make_record(
    district_name: str = "Bang Rak",
    avg_t: float = 31.0,
    max_t: float = 36.0,
    min_t: float = 26.0,
    green_area: float = 50000.0,
    parks_count: int = 4,
    reading_count: int = 720,
) -> IntegratedDistrictRecord:
    return IntegratedDistrictRecord(
        district_name=district_name,
        avg_temperature=avg_t,
        max_temperature=max_t,
        min_temperature=min_t,
        std_temperature=2.5,
        p90_temperature=34.0,
        diurnal_temperature_range=max_t - min_t,
        green_area_sqm=green_area,
        parks_count=parks_count,
        reading_count=reading_count,
    )


def test_temperature_plausibility_valid() -> None:
    rule = TemperaturePlausibilityRule()
    valid_rec = _make_record(avg_t=32.0, max_t=38.0, min_t=27.0)
    assert rule.evaluate(valid_rec) == []


def test_temperature_plausibility_extreme_hot() -> None:
    rule = TemperaturePlausibilityRule()
    hot_rec = _make_record(avg_t=52.0, max_t=55.0, min_t=48.0)
    violations = rule.evaluate(hot_rec)
    assert len(violations) >= 1
    assert any("outside plausible bounds" in v for v in violations)


def test_temperature_plausibility_inverted_min_max() -> None:
    rule = TemperaturePlausibilityRule()
    inverted_rec = _make_record(avg_t=30.0, max_t=25.0, min_t=35.0)
    violations = rule.evaluate(inverted_rec)
    assert any("cannot exceed max" in v for v in violations)


def test_green_space_indicator_negative_bounds() -> None:
    rule = GreenSpaceIndicatorRule()
    bad_rec = _make_record(green_area=-500.0, parks_count=-1)
    violations = rule.evaluate(bad_rec)
    assert len(violations) == 2
    assert "Green area" in violations[0]
    assert "Parks count" in violations[1]


def test_data_completeness_insufficient_samples() -> None:
    rule = DataCompletenessRule(min_readings=24)
    sparse_rec = _make_record(reading_count=5)
    violations = rule.evaluate(sparse_rec)
    assert len(violations) == 1
    assert "Insufficient observation count" in violations[0]


def test_composite_quality_policy_partition() -> None:
    policy = DefaultCuratedQualityPolicy()

    good_1 = _make_record(district_name="Phra Nakhon", avg_t=30.0)
    good_2 = _make_record(district_name="Dusit", avg_t=29.5)
    bad_hot = _make_record(district_name="Volcano_District", avg_t=60.0, max_t=65.0)
    bad_empty = _make_record(district_name="", avg_t=30.0)

    curated, rejected = policy.partition([good_1, good_2, bad_hot, bad_empty])

    assert len(curated) == 2
    assert len(rejected) == 2
    assert [r.district_name for r in curated] == ["Phra Nakhon", "Dusit"]
    assert any("outside plausible bounds" in r.rejection_reasons[0] for r in rejected if r.district_name == "Volcano_District")
    assert any("missing or blank" in r.rejection_reasons[0] for r in rejected if r.district_name == "")


def test_compute_diurnal_temperature_range() -> None:
    dtr = compute_diurnal_temperature_range(max_temp=37.5, min_temp=25.0)
    assert dtr == 12.5


def test_compare_green_space_cohorts() -> None:
    records = [
        _make_record("D1_Low", avg_t=34.0, green_area=10000.0),
        _make_record("D2_Low", avg_t=33.5, green_area=15000.0),
        _make_record("D3_Mid", avg_t=32.0, green_area=50000.0),
        _make_record("D4_Mid", avg_t=31.5, green_area=60000.0),
        _make_record("D5_High", avg_t=29.0, green_area=200000.0),
        _make_record("D6_High", avg_t=28.5, green_area=250000.0),
    ]

    result = compare_green_space_cohorts(records, tertile_split=True)
    assert result.high_green_count == 2
    assert result.low_green_count == 2
    assert result.low_green_mean_temp > result.high_green_mean_temp
    assert result.temperature_difference > 0  # Green areas are cooler
    assert result.mann_whitney_u is not None


def test_compute_bivariate_correlation() -> None:
    # Synthetic negative correlation (more green space -> cooler temperature)
    greens = [10000.0, 20000.0, 30000.0, 40000.0, 50000.0, 60000.0]
    temps = [35.0, 34.1, 33.0, 32.2, 31.0, 29.8]

    result = compute_bivariate_correlation(greens, temps)
    assert result.pearson_r < -0.9  # Strong negative correlation
    assert result.spearman_rho < -0.9
    assert result.r_squared > 0.8
    assert result.regression_slope < 0.0  # Negative slope
    assert "ACADEMIC LIMITATION" in result.academic_disclaimer
