"""Coordinate validation and spatial boundary integrity verification module."""

from __future__ import annotations

import logging
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

logger = logging.getLogger(__name__)

# Standard bounding box for Bangkok Metropolitan Area
# Bangkok lat spans approx 13.48 to 13.96; lon spans approx 100.32 to 100.93
BANGKOK_LAT_MIN = 13.40
BANGKOK_LAT_MAX = 14.10
BANGKOK_LON_MIN = 100.20
BANGKOK_LON_MAX = 101.00

EXPECTED_DISTRICT_COUNT = 50


class SpatialValidationError(ValueError):
    """Custom exception raised when spatial validation checks fail."""
    pass


def validate_crs(gdf: gpd.GeoDataFrame, expected_crs: str = "EPSG:4326") -> bool:
    """Validate Coordinate Reference System of a GeoDataFrame (Task P2-03).

    Args:
        gdf: Input GeoDataFrame.
        expected_crs: The expected CRS identifier (default 'EPSG:4326').

    Returns:
        True if valid.

    Raises:
        SpatialValidationError: If CRS is missing or does not match expected_crs.
    """
    if gdf.crs is None:
        raise SpatialValidationError("GeoDataFrame has no CRS defined.")

    actual_crs = str(gdf.crs).strip().upper()
    expected = expected_crs.strip().upper()

    # Check for match (e.g. 'EPSG:4326' or 'OGC:CRS84' / epsg code 4326)
    is_match = (
        actual_crs == expected
        or actual_crs == expected.replace("EPSG:", "")
        or (expected == "EPSG:4326" and "4326" in actual_crs)
    )

    if not is_match:
        raise SpatialValidationError(f"Expected CRS '{expected_crs}', but got '{gdf.crs}'.")

    logger.debug("CRS validation passed: %s", gdf.crs)
    return True


def validate_coordinates(
    df_or_gdf: pd.DataFrame | gpd.GeoDataFrame,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    min_lat: float = BANGKOK_LAT_MIN,
    max_lat: float = BANGKOK_LAT_MAX,
    min_lon: float = BANGKOK_LON_MIN,
    max_lon: float = BANGKOK_LON_MAX,
) -> bool:
    """Validate that coordinates are within Bangkok boundaries and correctly ordered (Tasks P2-03 & P2-06).

    Args:
        df_or_gdf: DataFrame or GeoDataFrame containing coordinate columns.
        lat_col: Latitude column name (defaults to 'latitude').
        lon_col: Longitude column name (defaults to 'longitude').
        min_lat: Minimum latitude bound.
        max_lat: Maximum latitude bound.
        min_lon: Minimum longitude bound.
        max_lon: Maximum longitude bound.

    Returns:
        True if all coordinates are valid and appropriately located.

    Raises:
        SpatialValidationError: If coordinates are out of bounds, null, or inverted.
    """
    if lat_col not in df_or_gdf.columns or lon_col not in df_or_gdf.columns:
        raise SpatialValidationError(
            f"Coordinate columns '{lat_col}' and '{lon_col}' not found in columns: {list(df_or_gdf.columns)}"
        )

    # Check for NaN / nulls
    null_lats = df_or_gdf[lat_col].isna().sum()
    null_lons = df_or_gdf[lon_col].isna().sum()
    if null_lats > 0 or null_lons > 0:
        raise SpatialValidationError(f"Found {null_lats} null latitudes and {null_lons} null longitudes.")

    # Cast to numeric
    try:
        lats = pd.to_numeric(df_or_gdf[lat_col], errors="raise")
        lons = pd.to_numeric(df_or_gdf[lon_col], errors="raise")
    except Exception as err:
        raise SpatialValidationError(f"Coordinates could not be converted to float: {err}") from err

    # Check for inverted coordinates (common GIS bug where lat is 100+ and lon is 13+)
    if (lats > 50.0).any() and (lons < 30.0).any():
        raise SpatialValidationError("Latitude and Longitude appears to be inverted (lat > 50 and lon < 30).")

    # Check bounds
    invalid_lats = df_or_gdf[(lats < min_lat) | (lats > max_lat)]
    if not invalid_lats.empty:
        bad_sample = invalid_lats.iloc[0][[lat_col, lon_col]].to_dict()
        raise SpatialValidationError(
            f"{len(invalid_lats)} latitude values outside Bangkok bounds [{min_lat}, {max_lat}]. Sample: {bad_sample}"
        )

    invalid_lons = df_or_gdf[(lons < min_lon) | (lons > max_lon)]
    if not invalid_lons.empty:
        bad_sample = invalid_lons.iloc[0][[lat_col, lon_col]].to_dict()
        raise SpatialValidationError(
            f"{len(invalid_lons)} longitude values outside Bangkok bounds [{min_lon}, {max_lon}]. Sample: {bad_sample}"
        )

    logger.debug("Coordinate bounds validation passed for %d records.", len(df_or_gdf))
    return True


def validate_representative_points(
    districts_boundaries: gpd.GeoDataFrame,
    representative_points: gpd.GeoDataFrame | None = None,
    point_lat_col: str = "latitude",
    point_lon_col: str = "longitude",
) -> bool:
    """Verify that each representative point falls strictly inside or covers its boundary (Task P2-06).

    Args:
        districts_boundaries: GeoDataFrame containing district polygon geometries.
        representative_points: Optional separate GeoDataFrame of points. If None,
            extracted from latitude/longitude or geometry of districts_boundaries.
        point_lat_col: Latitude column name if points GeoDataFrame is not provided.
        point_lon_col: Longitude column name if points GeoDataFrame is not provided.

    Returns:
        True if all representative points lie within their corresponding district boundary.

    Raises:
        SpatialValidationError: If any point falls outside its polygon.
    """
    outside_districts: list[dict[str, Any]] = []

    # If representative_points is not given, derive from input
    if representative_points is None:
        pts = districts_boundaries
    else:
        pts = representative_points

    for idx in districts_boundaries.index:
        boundary_geom = districts_boundaries.loc[idx].geometry

        # Resolve point
        if idx in pts.index:
            pt_row = pts.loc[idx]
            if isinstance(pt_row.geometry, Point):
                pt_geom = pt_row.geometry
            else:
                pt_geom = Point(float(pt_row[point_lon_col]), float(pt_row[point_lat_col]))
        else:
            raise SpatialValidationError(f"Index {idx} not found in representative points GeoDataFrame.")

        # In case geometries are in different CRS, align them
        if districts_boundaries.crs != pts.crs and pts.crs is not None:
            boundary_geom = districts_boundaries.to_crs(pts.crs).loc[idx].geometry

        # Check containment or coverage or intersection (covers/intersects handles points on boundary)
        is_inside = boundary_geom.contains(pt_geom) or boundary_geom.covers(pt_geom) or boundary_geom.intersects(pt_geom)
        if not is_inside:
            dname = (
                districts_boundaries.loc[idx].get("district")
                or districts_boundaries.loc[idx].get("dname_e")
                or str(idx)
            )
            outside_districts.append({
                "district": dname,
                "point_x": pt_geom.x,
                "point_y": pt_geom.y,
            })

    if outside_districts:
        raise SpatialValidationError(
            f"{len(outside_districts)} representative points fall outside their district boundary: {outside_districts}"
        )

    logger.debug("Representative points boundary integrity check passed for %d districts.", len(districts_boundaries))
    return True


def validate_district_count(
    df_or_gdf: pd.DataFrame | gpd.GeoDataFrame,
    expected_count: int = EXPECTED_DISTRICT_COUNT,
    district_col: str = "district",
) -> bool:
    """Verify that all 50 districts are present with no duplicates (Acceptance Criteria).

    Args:
        df_or_gdf: DataFrame or GeoDataFrame.
        expected_count: Expected number of districts (defaults to 50).
        district_col: District name column (defaults to 'district').

    Returns:
        True if valid.

    Raises:
        SpatialValidationError: If count does not match or duplicates exist.
    """
    col = district_col
    if col not in df_or_gdf.columns:
        candidates = ["district_name", "dname_e", "name"]
        for c in candidates:
            if c in df_or_gdf.columns:
                col = c
                break
        else:
            raise SpatialValidationError(f"District column '{district_col}' not found.")

    count = len(df_or_gdf)
    if count != expected_count:
        raise SpatialValidationError(
            f"Expected {expected_count} districts, but found {count}."
        )

    unique_count = df_or_gdf[col].nunique()
    if unique_count != expected_count:
        duplicates = df_or_gdf[col][df_or_gdf[col].duplicated()].tolist()
        raise SpatialValidationError(
            f"Expected {expected_count} unique districts, but found {unique_count}. Duplicates: {duplicates}"
        )

    logger.debug("District count validation passed: %d unique districts present.", count)
    return True


def run_full_validation(
    districts_boundaries: gpd.GeoDataFrame,
    representative_points: gpd.GeoDataFrame | None = None,
) -> dict[str, Any]:
    """Run full spatial validation suite across boundaries and representative points (Tasks P2-03 & P2-06).

    Returns:
        dict with boolean status and detailed check outcomes.
    """
    report: dict[str, Any] = {"status": "PASSED", "checks": {}}

    try:
        validate_crs(districts_boundaries)
        report["checks"]["crs"] = "PASSED"
    except SpatialValidationError as e:
        report["status"] = "FAILED"
        report["checks"]["crs"] = str(e)

    try:
        pts = representative_points if representative_points is not None else districts_boundaries
        validate_coordinates(pts)
        report["checks"]["coordinates_bounds"] = "PASSED"
    except SpatialValidationError as e:
        report["status"] = "FAILED"
        report["checks"]["coordinates_bounds"] = str(e)

    try:
        pts = representative_points if representative_points is not None else districts_boundaries
        validate_representative_points(districts_boundaries, pts)
        report["checks"]["points_inside_boundary"] = "PASSED"
    except SpatialValidationError as e:
        report["status"] = "FAILED"
        report["checks"]["points_inside_boundary"] = str(e)

    try:
        pts = representative_points if representative_points is not None else districts_boundaries
        validate_district_count(pts, expected_count=50)
        report["checks"]["district_count_50"] = "PASSED"
    except SpatialValidationError as e:
        report["status"] = "FAILED"
        report["checks"]["district_count_50"] = str(e)

    logger.info("Full validation completed with status: %s", report["status"])
    return report
