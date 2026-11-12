"""Transformation module public API providing team-specification compatible facades."""

from __future__ import annotations

import pandas as pd

from bigtree.adapters.in_memory_storage import InMemoryStorageAdapter
from bigtree.domain.models import IntegratedDistrictRecord
from bigtree.domain.rules import DefaultCuratedQualityPolicy
from bigtree.use_cases.transform_and_validate import TransformAndValidateDatasetUseCase


def clean_weather_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and filter missing/invalid temperature observations."""
    clean_df = df.dropna(subset=["temperature_2m"]).copy()
    clean_df = clean_df[(clean_df["temperature_2m"] >= 10.0) & (clean_df["temperature_2m"] <= 55.0)]
    return clean_df


def match_districts(weather: pd.DataFrame, green_space: pd.DataFrame) -> pd.DataFrame:
    """Standardize and merge weather and green-space dataframes on district name."""
    w_copy = weather.copy()
    g_copy = green_space.copy()

    w_copy["_key"] = w_copy["district"].astype(str).str.strip().str.lower()
    g_copy["_key"] = g_copy["district"].astype(str).str.strip().str.lower()

    merged = pd.merge(w_copy, g_copy, on="_key", suffixes=("", "_green"))
    return merged.drop(columns=["_key"])


def validate_data(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate DataFrame against domain business rules, returning (curated_df, not_pass_df)."""
    records: list[IntegratedDistrictRecord] = []
    for _, row in df.iterrows():
        records.append(
            IntegratedDistrictRecord(
                district_name=str(row.get("district", "")),
                avg_temperature=float(row.get("avg_temperature", 0.0)),
                max_temperature=float(row.get("max_temperature", 0.0)),
                min_temperature=float(row.get("min_temperature", 0.0)),
                std_temperature=float(row.get("std_temperature", 0.0)),
                p90_temperature=float(row.get("p90_temperature", 0.0)),
                diurnal_temperature_range=float(row.get("diurnal_temperature_range", 0.0)),
                green_area_sqm=float(row.get("green_area_sqm", 0.0)),
                parks_count=int(row.get("parks_count", 0)),
                reading_count=int(row.get("reading_count", 24)),
            )
        )

    policy = DefaultCuratedQualityPolicy()
    curated, rejected = policy.partition(records)

    curated_df = pd.DataFrame([r.to_dict() for r in curated])
    rejected_df = pd.DataFrame([r.to_dict() for r in rejected]) if rejected else pd.DataFrame(columns=["district", "rejection_reasons"])
    return curated_df, rejected_df


__all__ = [
    "clean_weather_data",
    "match_districts",
    "validate_data",
    "TransformAndValidateDatasetUseCase",
]
