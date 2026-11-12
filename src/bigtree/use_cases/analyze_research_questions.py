"""Use case for Person 4: Statistical Research Analysis & Visualization (Q1-Q3)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")  # Headless rendering for cloud & CI
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from bigtree.domain.models import IntegratedDistrictRecord
from bigtree.domain.statistics import (
    compare_green_space_cohorts,
    compute_bivariate_correlation,
)
from bigtree.ports.storage import StoragePort

logger = logging.getLogger(__name__)


class AnalyzeResearchQuestionsUseCase:
    """Executes the statistical research analysis answering Q1, Q2, and Q3 from the proposal."""

    def __init__(self, storage: StoragePort) -> None:
        self.storage = storage

    def execute(
        self,
        curated_data_uri: str,
        output_metrics_uri: str,
        visualizations_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        start_time = datetime.now(timezone.utc)
        logger.info("Starting research analysis on curated data: %s", curated_data_uri)

        df = self.storage.read_csv(curated_data_uri)
        if df.empty or len(df) < 3:
            raise ValueError(f"Curated dataset at {curated_data_uri} has insufficient rows ({len(df)}) for statistical analysis.")

        records = [
            IntegratedDistrictRecord(
                district_name=str(row["district"]),
                avg_temperature=float(row["avg_temperature"]),
                max_temperature=float(row["max_temperature"]),
                min_temperature=float(row["min_temperature"]),
                std_temperature=float(row.get("std_temperature", 0.0)),
                p90_temperature=float(row.get("p90_temperature", row["max_temperature"])),
                diurnal_temperature_range=float(row.get("diurnal_temperature_range", row["max_temperature"] - row["min_temperature"])),
                green_area_sqm=float(row["green_area_sqm"]),
                parks_count=int(row.get("parks_count", 0)),
                reading_count=int(row.get("reading_count", 24)),
            )
            for _, row in df.iterrows()
        ]

        # ---------------------------------------------------------------------
        # Q1 Analysis: Temperature Trajectory & City-wide Variation
        # ---------------------------------------------------------------------
        bangkok_mean = round(float(df["avg_temperature"].mean()), 2)
        bangkok_max = round(float(df["max_temperature"].max()), 2)
        bangkok_min = round(float(df["min_temperature"].min()), 2)
        dtr_series = (
            df["diurnal_temperature_range"]
            if "diurnal_temperature_range" in df.columns
            else (df["max_temperature"] - df["min_temperature"])
        )
        mean_dtr = round(float(dtr_series.mean()), 2)
        temp_std = round(float(df["avg_temperature"].std()), 2)

        q1_summary = {
            "research_question": "Q1: How does temperature change over time across Bangkok districts?",
            "bangkok_overall_mean_temp_celsius": bangkok_mean,
            "bangkok_overall_max_temp_celsius": bangkok_max,
            "bangkok_overall_min_temp_celsius": bangkok_min,
            "mean_diurnal_temperature_range_celsius": mean_dtr,
            "district_temperature_std_dev": temp_std,
            "findings": (
                f"Bangkok districts experienced an overall average temperature of {bangkok_mean}°C "
                f"with peak temperatures reaching {bangkok_max}°C. The average diurnal temperature range "
                f"was {mean_dtr}°C, with an inter-district thermal dispersion of ±{temp_std}°C."
            ),
        }

        # ---------------------------------------------------------------------
        # Q2 Analysis: Group Comparison (High vs. Low Green Space)
        # ---------------------------------------------------------------------
        q2_stats = compare_green_space_cohorts(records, tertile_split=True)
        q2_summary = {
            "research_question": "Q2: Do high and low green-space districts have different temperatures?",
            "high_green_districts_count": q2_stats.high_green_count,
            "low_green_districts_count": q2_stats.low_green_count,
            "high_green_mean_temp_celsius": q2_stats.high_green_mean_temp,
            "low_green_mean_temp_celsius": q2_stats.low_green_mean_temp,
            "temperature_delta_celsius": q2_stats.temperature_difference,
            "t_statistic": q2_stats.t_statistic,
            "mann_whitney_u": q2_stats.mann_whitney_u,
            "p_value": q2_stats.p_value,
            "is_statistically_significant": q2_stats.is_statistically_significant,
            "findings": q2_stats.summary_text,
        }

        # ---------------------------------------------------------------------
        # Q3 Analysis: Correlation & Regression Analysis
        # ---------------------------------------------------------------------
        green_areas = [r.green_area_sqm for r in records]
        temperatures = [r.avg_temperature for r in records]
        q3_stats = compute_bivariate_correlation(green_areas, temperatures)

        q3_summary = {
            "research_question": "Q3: How strong is the relationship between green space and temperature?",
            "pearson_r": q3_stats.pearson_r,
            "pearson_p_value": q3_stats.pearson_p_value,
            "spearman_rho": q3_stats.spearman_rho,
            "spearman_p_value": q3_stats.spearman_p_value,
            "r_squared": q3_stats.r_squared,
            "regression_slope": q3_stats.regression_slope,
            "regression_intercept": q3_stats.regression_intercept,
            "cooling_effect_per_100k_sqm_celsius": q3_stats.cooling_per_100k_sqm,
            "academic_disclaimer": q3_stats.academic_disclaimer,
            "findings": (
                f"Pearson correlation r={q3_stats.pearson_r} (p={q3_stats.pearson_p_value}), "
                f"Spearman rho={q3_stats.spearman_rho} (p={q3_stats.spearman_p_value}). "
                f"OLS linear model indicates R^2={q3_stats.r_squared}, implying green area accounts for "
                f"{q3_stats.r_squared * 100:.1f}% of variance in district average temperatures."
            ),
        }

        # ---------------------------------------------------------------------
        # Visualizations Generation (if output directory provided)
        # ---------------------------------------------------------------------
        generated_charts: list[str] = []
        if visualizations_dir:
            viz_path = Path(visualizations_dir)
            viz_path.mkdir(parents=True, exist_ok=True)

            sns.set_theme(style="whitegrid")

            # Chart 1: Q1 Temperature Distributions
            fig1, ax1 = plt.subplots(figsize=(10, 5))
            sns.histplot(df["avg_temperature"], kde=True, color="#e74c3c", ax=ax1, bins=12)
            ax1.set_title("Q1: Bangkok District Temperature Distribution (°C)", fontsize=13, weight="bold")
            ax1.set_xlabel("Average Temperature (°C)")
            ax1.set_ylabel("District Count")
            chart1_path = str(viz_path / "q1_temperature_distribution.png")
            fig1.savefig(chart1_path, dpi=150, bbox_inches="tight")
            plt.close(fig1)
            generated_charts.append(chart1_path)

            # Chart 2: Q2 Cohort Comparison Boxplot
            sorted_df = df.sort_values(by="green_area_sqm").copy()
            cutoff = max(1, len(sorted_df) // 3)
            sorted_df["cohort"] = "Middle Tier"
            sorted_df.iloc[:cutoff, sorted_df.columns.get_loc("cohort")] = "Low Green Space"
            sorted_df.iloc[-cutoff:, sorted_df.columns.get_loc("cohort")] = "High Green Space"
            filtered_df = sorted_df[sorted_df["cohort"] != "Middle Tier"]

            fig2, ax2 = plt.subplots(figsize=(8, 6))
            sns.boxplot(data=filtered_df, x="cohort", y="avg_temperature", palette=["#e67e22", "#27ae60"], ax=ax2)
            sns.stripplot(data=filtered_df, x="cohort", y="avg_temperature", color="black", alpha=0.5, jitter=0.2, ax=ax2)
            ax2.set_title("Q2: Temperature Comparison by Green Space Tier", fontsize=13, weight="bold")
            ax2.set_xlabel("Green Space Cohort")
            ax2.set_ylabel("Average Temperature (°C)")
            chart2_path = str(viz_path / "q2_cohort_comparison.png")
            fig2.savefig(chart2_path, dpi=150, bbox_inches="tight")
            plt.close(fig2)
            generated_charts.append(chart2_path)

            # Chart 3: Q3 Correlation Scatter & Regression Line
            fig3, ax3 = plt.subplots(figsize=(9, 6))
            sns.regplot(
                data=df,
                x="green_area_sqm",
                y="avg_temperature",
                scatter_kws={"color": "#2980b9", "alpha": 0.7, "s": 50},
                line_kws={"color": "#c0392b", "linewidth": 2},
                ax=ax3,
            )
            ax3.set_title(
                f"Q3: Green Space Area vs. Temperature (r={q3_stats.pearson_r}, R²={q3_stats.r_squared})",
                fontsize=13,
                weight="bold",
            )
            ax3.set_xlabel("Green Area (sq. meters)")
            ax3.set_ylabel("Average Temperature (°C)")
            chart3_path = str(viz_path / "q3_correlation_scatter.png")
            fig3.savefig(chart3_path, dpi=150, bbox_inches="tight")
            plt.close(fig3)
            generated_charts.append(chart3_path)

        end_time = datetime.now(timezone.utc)
        results = {
            "pipeline_stage": "Statistical Research Analysis (Person 4)",
            "analyzed_at_utc": start_time.isoformat(),
            "execution_duration_seconds": (end_time - start_time).total_seconds(),
            "curated_records_analyzed": len(records),
            "q1_temporal_analysis": q1_summary,
            "q2_group_comparison": q2_summary,
            "q3_correlation_analysis": q3_summary,
            "generated_visualizations": generated_charts,
        }

        saved_uri = self.storage.write_json(output_metrics_uri, results)
        results["output_metrics_uri"] = saved_uri
        logger.info("Research analysis successfully written to %s", saved_uri)
        return results
