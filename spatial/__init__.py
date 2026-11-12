"""Spatial preprocessing module for Bangkok district boundaries and coordinates."""

from spatial.centroid import calculate_centroids
from spatial.coordinate_validator import (
    run_full_validation,
    validate_coordinates,
    validate_crs,
    validate_district_count,
    validate_representative_points,
)
from spatial.district_processor import (
    export_coordinates,
    normalize_district_name,
    process_district_coordinates,
    standardize_districts,
)
from spatial.kml_reader import inspect_kml, read_district_kml

__all__ = [
    "read_district_kml",
    "inspect_kml",
    "calculate_centroids",
    "export_coordinates",
    "standardize_districts",
    "normalize_district_name",
    "process_district_coordinates",
    "validate_crs",
    "validate_coordinates",
    "validate_representative_points",
    "validate_district_count",
    "run_full_validation",
]
