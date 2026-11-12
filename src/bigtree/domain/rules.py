"""Pure business rules and validation policies for data quality."""

from __future__ import annotations

from typing import Protocol

from bigtree.domain.models import (
    IntegratedDistrictRecord,
    QualityCheckResult,
    RejectedDistrictRecord,
)


class DataQualityRule(Protocol):
    """Abstract contract for an isolated business quality rule."""

    def evaluate(self, record: IntegratedDistrictRecord) -> list[str]:
        """Evaluate record and return a list of violation messages (empty if valid)."""
        ...


class TemperaturePlausibilityRule:
    """Enforces climatological bounds for Bangkok ambient air temperature."""

    def __init__(
        self,
        min_allowable_celsius: float = 15.0,
        max_allowable_celsius: float = 50.0,
    ) -> None:
        self.min_allowable = min_allowable_celsius
        self.max_allowable = max_allowable_celsius

    def evaluate(self, record: IntegratedDistrictRecord) -> list[str]:
        violations: list[str] = []
        if not (self.min_allowable <= record.avg_temperature <= self.max_allowable):
            violations.append(
                f"Average temperature {record.avg_temperature:.1f}°C is outside plausible bounds "
                f"[{self.min_allowable}°C, {self.max_allowable}°C]"
            )
        if not (self.min_allowable <= record.max_temperature <= self.max_allowable):
            violations.append(
                f"Max temperature {record.max_temperature:.1f}°C is outside plausible bounds "
                f"[{self.min_allowable}°C, {self.max_allowable}°C]"
            )
        if record.min_temperature > record.max_temperature:
            violations.append(
                f"Min temperature {record.min_temperature:.1f}°C cannot exceed max {record.max_temperature:.1f}°C"
            )
        return violations


class GreenSpaceIndicatorRule:
    """Enforces non-negative physical bounds on green space indicators."""

    def evaluate(self, record: IntegratedDistrictRecord) -> list[str]:
        violations: list[str] = []
        if record.green_area_sqm < 0:
            violations.append(f"Green area ({record.green_area_sqm}) cannot be negative")
        if record.parks_count < 0:
            violations.append(f"Parks count ({record.parks_count}) cannot be negative")
        return violations


class DataCompletenessRule:
    """Enforces minimum observation sample size for statistical validity."""

    def __init__(self, min_readings: int = 24) -> None:
        self.min_readings = min_readings

    def evaluate(self, record: IntegratedDistrictRecord) -> list[str]:
        violations: list[str] = []
        if record.reading_count < self.min_readings:
            violations.append(
                f"Insufficient observation count: {record.reading_count} < required {self.min_readings}"
            )
        return violations


class DistrictNameIntegrityRule:
    """Enforces valid district naming."""

    def evaluate(self, record: IntegratedDistrictRecord) -> list[str]:
        violations: list[str] = []
        if not record.district_name or record.district_name.strip() == "":
            violations.append("District identifier is missing or blank")
        return violations


class DefaultCuratedQualityPolicy:
    """Composite policy combining all core business data quality rules."""

    def __init__(
        self,
        rules: list[DataQualityRule] | None = None,
    ) -> None:
        self.rules: list[DataQualityRule] = rules or [
            DistrictNameIntegrityRule(),
            TemperaturePlausibilityRule(),
            GreenSpaceIndicatorRule(),
            DataCompletenessRule(),
        ]

    def check(self, record: IntegratedDistrictRecord) -> QualityCheckResult:
        all_violations: list[str] = []
        for rule in self.rules:
            all_violations.extend(rule.evaluate(record))
        return QualityCheckResult(
            is_valid=len(all_violations) == 0,
            rejection_reasons=tuple(all_violations),
        )

    def partition(
        self,
        records: list[IntegratedDistrictRecord],
    ) -> tuple[list[IntegratedDistrictRecord], list[RejectedDistrictRecord]]:
        """Separate candidate records into Curated Data and Not Pass Data."""
        curated: list[IntegratedDistrictRecord] = []
        rejected: list[RejectedDistrictRecord] = []

        for rec in records:
            result = self.check(rec)
            if result.is_valid:
                curated.append(rec)
            else:
                rejected.append(
                    RejectedDistrictRecord(
                        district_name=rec.district_name,
                        rejection_reasons=result.rejection_reasons,
                        raw_data=rec.to_dict(),
                    )
                )

        return curated, rejected
