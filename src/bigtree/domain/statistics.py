"""Pure mathematical and statistical functions for academic hypothesis testing."""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from scipy import stats

from bigtree.domain.models import (
    IntegratedDistrictRecord,
    Q2GroupComparisonResult,
    Q3CorrelationResult,
)


def compute_diurnal_temperature_range(max_temp: float, min_temp: float) -> float:
    """Calculate Diurnal Temperature Range (DTR) = Daily Max - Daily Min."""
    return round(max_temp - min_temp, 2)


def compute_bivariate_correlation(
    green_spaces: Sequence[float],
    temperatures: Sequence[float],
) -> Q3CorrelationResult:
    """Compute Pearson and Spearman correlation, plus OLS regression metrics."""
    if len(green_spaces) < 3 or len(temperatures) < 3:
        raise ValueError("At least 3 data points required for correlation analysis.")

    x = np.array(green_spaces, dtype=float)
    y = np.array(temperatures, dtype=float)

    # 1. Pearson Linear Correlation
    pearson_r, pearson_p = stats.pearsonr(x, y)

    # 2. Spearman Monotonic Rank Correlation
    spearman_rho, spearman_p = stats.spearmanr(x, y)

    # 3. OLS Linear Regression (y = beta1 * x + beta0)
    slope, intercept, r_value, _, _ = stats.linregress(x, y)
    r_squared = float(r_value**2)

    # Cooling effect per 100,000 sqm of green area
    cooling_per_100k = float(slope * 100_000.0)

    disclaimer = (
        "ACADEMIC LIMITATION: Correlation does not establish direct causation. "
        "Urban surface temperature is modulated by unobserved covariates including "
        "building height/density, Chao Phraya river breezes, vehicular emissions, "
        "and temporal divergence between green space surveying and meteorological archives."
    )

    return Q3CorrelationResult(
        pearson_r=round(float(pearson_r), 4),
        pearson_p_value=round(float(pearson_p), 4),
        spearman_rho=round(float(spearman_rho), 4),
        spearman_p_value=round(float(spearman_p), 4),
        r_squared=round(r_squared, 4),
        regression_slope=float(slope),
        regression_intercept=round(float(intercept), 4),
        cooling_per_100k_sqm=round(cooling_per_100k, 4),
        academic_disclaimer=disclaimer,
    )


def compare_green_space_cohorts(
    records: Sequence[IntegratedDistrictRecord],
    tertile_split: bool = True,
) -> Q2GroupComparisonResult:
    """Compare temperatures between High and Low Green Space cohorts using parametric and non-parametric tests."""
    if len(records) < 4:
        raise ValueError("At least 4 records required for cohort comparison.")

    sorted_records = sorted(records, key=lambda r: r.green_area_sqm)
    n = len(sorted_records)

    if tertile_split and n >= 6:
        # Compare top 33% against bottom 33% for maximum contrast
        cutoff = math.ceil(n / 3)
        low_cohort = sorted_records[:cutoff]
        high_cohort = sorted_records[-cutoff:]
    else:
        # Standard median split
        mid = n // 2
        low_cohort = sorted_records[:mid]
        high_cohort = sorted_records[mid:]

    low_temps = [r.avg_temperature for r in low_cohort]
    high_temps = [r.avg_temperature for r in high_cohort]

    low_mean = float(np.mean(low_temps))
    high_mean = float(np.mean(high_temps))
    temp_diff = round(low_mean - high_mean, 2)  # Positive means green areas are cooler

    # Two-sample Independent t-test
    t_stat, p_val_t = stats.ttest_ind(low_temps, high_temps, equal_var=False)

    # Non-parametric Mann-Whitney U test (handles non-normal distribution)
    u_stat, p_val_u = stats.mannwhitneyu(low_temps, high_temps, alternative="two-sided")

    # Primary hypothesis significance evaluated at alpha = 0.05
    is_significant = bool(p_val_u < 0.05)

    summary = (
        f"Low Green Space ({len(low_cohort)} districts) mean: {low_mean:.2f}°C. "
        f"High Green Space ({len(high_cohort)} districts) mean: {high_mean:.2f}°C. "
        f"Observed difference: {temp_diff:+.2f}°C. "
        f"Mann-Whitney U={u_stat:.1f} (p={p_val_u:.4f}). "
        f"Statistically significant at alpha=0.05: {is_significant}."
    )

    return Q2GroupComparisonResult(
        high_green_count=len(high_cohort),
        low_green_count=len(low_cohort),
        high_green_mean_temp=round(high_mean, 2),
        low_green_mean_temp=round(low_mean, 2),
        temperature_difference=temp_diff,
        t_statistic=round(float(t_stat), 4) if not np.isnan(t_stat) else None,
        p_value=round(float(p_val_u), 4),
        mann_whitney_u=round(float(u_stat), 2),
        is_statistically_significant=is_significant,
        summary_text=summary,
    )
