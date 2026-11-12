"""Centroid and representative point calculation module for district boundaries."""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

logger = logging.getLogger(__name__)

# Standard projected coordinate reference system for Thailand / Bangkok: UTM Zone 47N
DEFAULT_PROJECTED_CRS = "EPSG:32647"
GEOGRAPHIC_CRS = "EPSG:4326"


def calculate_centroids(
    districts: gpd.GeoDataFrame,
    projected_crs: str = DEFAULT_PROJECTED_CRS,
    target_crs: str = GEOGRAPHIC_CRS,
) -> gpd.GeoDataFrame:
    """Calculate one representative coordinate point per district (Task P2-05).

    Methodology:
    1. Coordinate calculations use an appropriate projected metric CRS (EPSG:32647,
       UTM Zone 47N for Bangkok/Thailand) rather than blindly averaging longitude and latitude.
    2. Calculates geometric centroids in the projected coordinate space.
    3. Verifies whether the geometric centroid falls strictly within the polygon boundary.
    4. If the centroid falls outside (e.g., in concave, crescent, C-shaped, or fragmented
       multi-polygon districts), dynamically falls back to Shapely's `representative_point()`,
       which is mathematically guaranteed to fall strictly inside the district boundary.
    5. Transforms representative coordinates back to EPSG:4326 (WGS 84) to extract
       standard decimal latitude and longitude.

    Args:
        districts: GeoDataFrame containing district polygon geometries.
        projected_crs: Projected metric CRS for spatial calculations (defaults to EPSG:32647).
        target_crs: Target geographic CRS for output coordinates (defaults to EPSG:4326).

    Returns:
        GeoDataFrame with updated point geometry and 'latitude' / 'longitude' columns.
    """
    if districts.empty:
        raise ValueError("Cannot calculate centroids for an empty GeoDataFrame.")

    if districts.geometry is None:
        raise ValueError("GeoDataFrame must contain a valid geometry column.")

    result_gdf = districts.copy()

    # Ensure source CRS is defined
    if result_gdf.crs is None:
        logger.warning("Source GeoDataFrame has no CRS defined; defaulting to %s", GEOGRAPHIC_CRS)
        result_gdf.set_crs(GEOGRAPHIC_CRS, inplace=True)

    # Step 1: Reproject to metric projected CRS (UTM Zone 47N)
    districts_projected = result_gdf.to_crs(projected_crs)

    rep_points_proj: list[Point] = []
    fallback_count = 0

    # Step 2 & 3: Compute centroid and check against polygon boundary
    for idx, geom in districts_projected.geometry.items():
        if geom is None or geom.is_empty:
            raise ValueError(f"Feature at index {idx} has an empty or null geometry.")

        geometric_centroid = geom.centroid

        # Check if centroid is inside polygon
        if geom.contains(geometric_centroid) or geom.covers(geometric_centroid):
            rep_points_proj.append(geometric_centroid)
        else:
            # Centroid fell outside irregular/concave boundary; use representative point inside
            rep_point = geom.representative_point()
            rep_points_proj.append(rep_point)
            fallback_count += 1
            district_name = result_gdf.loc[idx].get("district") or result_gdf.loc[idx].get("dname_e") or str(idx)
            logger.info(
                "District '%s' centroid fell outside boundary. Replaced with interior representative point.",
                district_name,
            )

    # Step 4: Construct projected Point GeoSeries
    projected_points_series = gpd.GeoSeries(rep_points_proj, crs=projected_crs, index=result_gdf.index)

    # Step 5: Reproject back to geographic CRS (EPSG:4326)
    geographic_points_series = projected_points_series.to_crs(target_crs)

    # Step 6: Extract decimal degrees latitude and longitude
    result_gdf["longitude"] = geographic_points_series.x.round(6)
    result_gdf["latitude"] = geographic_points_series.y.round(6)

    # Update geometry to the representative point in target_crs
    result_gdf["geometry"] = geographic_points_series
    result_gdf.set_crs(target_crs, inplace=True, allow_override=True)

    logger.info(
        "Calculated representative points for %d districts using projected CRS %s (Fallbacks outside boundary: %d).",
        len(result_gdf),
        projected_crs,
        fallback_count,
    )
    return result_gdf


def export_coordinates(
    districts: gpd.GeoDataFrame,
    output_path: str,
    district_col: str = "district",
    lat_col: str = "latitude",
    lon_col: str = "longitude",
) -> None:
    """Export the district coordinate table to CSV (Task P2-07).

    Args:
        districts: GeoDataFrame containing standardized district names and coordinates.
        output_path: Target CSV destination path.
        district_col: Column containing district names (defaults to 'district').
        lat_col: Column containing latitude (defaults to 'latitude').
        lon_col: Column containing longitude (defaults to 'longitude').
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Check for district column or fallback candidates
    actual_district_col = district_col
    if actual_district_col not in districts.columns:
        candidates = ["district_name", "dname_e", "dname", "name"]
        for c in candidates:
            if c in districts.columns:
                actual_district_col = c
                break
        else:
            raise KeyError(f"Could not find district name column '{district_col}' in {list(districts.columns)}")

    if lat_col not in districts.columns or lon_col not in districts.columns:
        raise KeyError(f"Columns '{lat_col}' and '{lon_col}' must be present in DataFrame.")

    export_df = pd.DataFrame({
        "district": districts[actual_district_col],
        "latitude": districts[lat_col],
        "longitude": districts[lon_col],
    })

    # Sort alphabetically by district name for deterministic output
    export_df = export_df.sort_values(by="district").reset_index(drop=True)

    export_df.to_csv(path, index=False, encoding="utf-8")
    logger.info("Exported %d district coordinates to %s", len(export_df), path)
