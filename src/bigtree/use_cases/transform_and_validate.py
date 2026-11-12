"""Use case for Person 3: Data Transformation and Quality Validation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from bigtree.domain.models import IntegratedDistrictRecord
from bigtree.domain.rules import DefaultCuratedQualityPolicy
from bigtree.domain.statistics import compute_diurnal_temperature_range
from bigtree.ports.storage import StoragePort

logger = logging.getLogger(__name__)


def _normalize_name(name: str) -> str:
    """Normalize district names for consistent cross-dataset matching."""
    cleaned = str(name).strip().lower()
    for prefix in ["khet ", "district ", "เขต"]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    return cleaned.replace(" ", "").replace("-", "")


class TransformAndValidateDatasetUseCase:
    """Orchestrates loading raw inputs, calculating aggregates, applying business rules,

    and partitioning records into Curated and Not-Pass datasets.
    """

    def __init__(
        self,
        storage: StoragePort,
        quality_policy: DefaultCuratedQualityPolicy | None = None,
    ) -> None:
        self.storage = storage
        self.quality_policy = quality_policy or DefaultCuratedQualityPolicy()

    def execute(
        self,
        raw_weather_files: list[str],
        green_space_csv_uri: str,
        coordinates_csv_uri: str,
        curated_output_uri: str,
        rejected_output_uri: str,
        manifest_output_uri: str | None = None,
    ) -> dict[str, Any]:
        start_time = datetime.now(timezone.utc)
        logger.info("Executing TransformAndValidateDatasetUseCase with %d weather files.", len(raw_weather_files))

        # 1. Load and aggregate raw weather JSONs
        weather_summaries: dict[str, dict[str, Any]] = {}
        for f_uri in raw_weather_files:
            try:
                payload = self.storage.read_json(f_uri)
            except Exception as err:
                logger.warning("Failed to read raw weather file %s: %s", f_uri, err)
                continue

            metadata = payload.get("metadata", {})
            raw_response = payload.get("raw_response")
            district_name = metadata.get("district_name")

            if not raw_response or not district_name:
                continue

            hourly_data = raw_response.get("hourly", {})
            temperatures = hourly_data.get("temperature_2m", [])
            valid_temps = [float(t) for t in temperatures if t is not None and not np.isnan(float(t))]

            if not valid_temps:
                continue

            arr = np.array(valid_temps, dtype=float)
            avg_t = float(np.mean(arr))
            max_t = float(np.max(arr))
            min_t = float(np.min(arr))
            std_t = float(np.std(arr))
            p90_t = float(np.percentile(arr, 90))
            dtr = compute_diurnal_temperature_range(max_t, min_t)

            norm_key = _normalize_name(district_name)
            weather_summaries[norm_key] = {
                "original_district_name": district_name,
                "avg_temperature": avg_t,
                "max_temperature": max_t,
                "min_temperature": min_t,
                "std_temperature": std_t,
                "p90_temperature": p90_t,
                "diurnal_temperature_range": dtr,
                "reading_count": len(valid_temps),
            }

        # 2. Load green space data and coordinates
        green_df = self.storage.read_csv(green_space_csv_uri)
        coords_df = self.storage.read_csv(coordinates_csv_uri)

        # Build green space lookup
        green_lookup: dict[str, tuple[float, int]] = {}
        for _, row in green_df.iterrows():
            d_name = str(row.get("district", row.get("district_name", "")))
            norm_key = _normalize_name(d_name)
            area = float(row.get("green_area_sqm", row.get("green_area", 0.0)))
            parks = int(row.get("parks_count", row.get("parks", 0)))
            green_lookup[norm_key] = (area, parks)

        # 3. Integrate into candidate records
        candidate_records: list[IntegratedDistrictRecord] = []
        for _, row in coords_df.iterrows():
            d_name = str(row.get("district", row.get("district_name", "")))
            norm_key = _normalize_name(d_name)

            weather_data = weather_summaries.get(norm_key)
            green_data = green_lookup.get(norm_key)

            if weather_data and green_data:
                area, parks = green_data
                candidate_records.append(
                    IntegratedDistrictRecord(
                        district_name=d_name,
                        avg_temperature=weather_data["avg_temperature"],
                        max_temperature=weather_data["max_temperature"],
                        min_temperature=weather_data["min_temperature"],
                        std_temperature=weather_data["std_temperature"],
                        p90_temperature=weather_data["p90_temperature"],
                        diurnal_temperature_range=weather_data["diurnal_temperature_range"],
                        green_area_sqm=area,
                        parks_count=parks,
                        reading_count=weather_data["reading_count"],
                    )
                )

        # 4. Apply Business Rules to Partition into Curated vs. Not Pass
        curated_records, rejected_records = self.quality_policy.partition(candidate_records)

        # 5. Persist Curated and Rejected datasets
        curated_df = pd.DataFrame([r.to_dict() for r in curated_records])
        rejected_df = pd.DataFrame([r.to_dict() for r in rejected_records]) if rejected_records else pd.DataFrame(columns=["district", "rejection_reasons"])

        curated_dest = self.storage.write_csv(curated_output_uri, curated_df)
        rejected_dest = self.storage.write_csv(rejected_output_uri, rejected_df)

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        manifest = {
            "pipeline_stage": "Transformation & Data Quality Validation",
            "executed_at_utc": start_time.isoformat(),
            "duration_seconds": duration,
            "inputs": {
                "weather_files_count": len(raw_weather_files),
                "green_space_uri": green_space_csv_uri,
                "coordinates_uri": coordinates_csv_uri,
            },
            "summary": {
                "total_candidates": len(candidate_records),
                "curated_records_count": len(curated_records),
                "rejected_records_count": len(rejected_records),
            },
            "outputs": {
                "curated_uri": curated_dest,
                "rejected_uri": rejected_dest,
            },
        }

        if manifest_output_uri:
            manifest_dest = self.storage.write_json(manifest_output_uri, manifest)
            manifest["manifest_saved_uri"] = manifest_dest

        logger.info(
            "Transformation finished: Curated=%d, Rejected=%d in %.2fs.",
            len(curated_records),
            len(rejected_records),
            duration,
        )
        return manifest
