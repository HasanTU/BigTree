"""KML ingestion and spatial boundary extraction module."""

from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.validation import make_valid

logger = logging.getLogger(__name__)


def inspect_kml(file_path: str | Path) -> dict[str, Any]:
    """Inspect KML district boundary file structure and metadata (Task P2-01).

    Args:
        file_path: Path to the KML file.

    Returns:
        dict containing feature count, detected attributes, geometry types, and sample entries.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"KML file not found: {file_path}")

    # Inspect using XML parser to read internal tags and schema
    tree = ET.parse(path)
    root = tree.getroot()

    # Determine namespace if present
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    placemarks = root.findall(f".//{ns}Placemark")
    simple_fields = root.findall(f".//{ns}SimpleField")
    field_names = [f.attrib.get("name") for f in simple_fields if "name" in f.attrib]

    # Collect sample placemark attributes and geometry tags
    sample_attributes: list[dict[str, Any]] = []
    geom_types: set[str] = set()

    for pm in placemarks[:5]:
        attrs: dict[str, Any] = {}
        name_tag = pm.find(f"{ns}name")
        if name_tag is not None and name_tag.text:
            attrs["name"] = name_tag.text.strip()

        # Check ExtendedData / SimpleData
        for sd in pm.findall(f".//{ns}SimpleData"):
            key = sd.attrib.get("name")
            if key:
                attrs[key] = sd.text.strip() if sd.text else ""

        # Check ExtendedData / Data
        for data_elem in pm.findall(f".//{ns}Data"):
            key = data_elem.attrib.get("name")
            val_elem = data_elem.find(f"{ns}value")
            if key and val_elem is not None and val_elem.text:
                attrs[key] = val_elem.text.strip()

        if pm.find(f".//{ns}Polygon") is not None:
            geom_types.add("Polygon")
        if pm.find(f".//{ns}MultiGeometry") is not None:
            geom_types.add("MultiGeometry")
        if pm.find(f".//{ns}Point") is not None:
            geom_types.add("Point")

        sample_attributes.append(attrs)

    report = {
        "file_path": str(path),
        "file_size_bytes": path.stat().st_size,
        "feature_count": len(placemarks),
        "schema_fields": field_names,
        "detected_geometry_types": sorted(list(geom_types)),
        "default_crs": "EPSG:4326",
        "sample_placemarks": sample_attributes,
    }
    logger.info("KML Inspection summary for %s: %d features found", path.name, len(placemarks))
    return report


def _parse_coord_string(coord_text: str) -> list[tuple[float, float]]:
    """Parse coordinate string from KML LinearRing (lon,lat[,alt])."""
    coords: list[tuple[float, float]] = []
    # Coordinates in KML can be separated by spaces, newlines, or tabs
    for token in coord_text.strip().split():
        parts = token.strip().split(",")
        if len(parts) >= 2:
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                coords.append((lon, lat))
            except ValueError:
                continue
    return coords


def _parse_polygon_element(poly_elem: ET.Element, ns: str) -> Polygon | None:
    """Parse a KML <Polygon> element into a Shapely Polygon."""
    outer_coords_elem = poly_elem.find(f".//{ns}outerBoundaryIs//{ns}coordinates")
    if outer_coords_elem is None or not outer_coords_elem.text:
        return None

    outer_coords = _parse_coord_string(outer_coords_elem.text)
    if len(outer_coords) < 3:
        return None

    # Holes (inner boundaries)
    inner_rings: list[list[tuple[float, float]]] = []
    for inner in poly_elem.findall(f".//{ns}innerBoundaryIs"):
        inner_coords_elem = inner.find(f".//{ns}coordinates")
        if inner_coords_elem is not None and inner_coords_elem.text:
            ring = _parse_coord_string(inner_coords_elem.text)
            if len(ring) >= 3:
                inner_rings.append(ring)

    poly = Polygon(shell=outer_coords, holes=inner_rings if inner_rings else None)
    if not poly.is_valid:
        poly = make_valid(poly)
    return poly


def _parse_kml_xml(file_path: Path) -> gpd.GeoDataFrame:
    """Fallback XML parser for KML files when GDAL/Fiona drivers are unavailable."""
    tree = ET.parse(file_path)
    root = tree.getroot()

    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    placemarks = root.findall(f".//{ns}Placemark")
    records: list[dict[str, Any]] = []

    for idx, pm in enumerate(placemarks):
        record: dict[str, Any] = {}

        # Name & description
        name_elem = pm.find(f"{ns}name")
        if name_elem is not None and name_elem.text:
            record["name"] = name_elem.text.strip()

        desc_elem = pm.find(f"{ns}description")
        if desc_elem is not None and desc_elem.text:
            record["description"] = desc_elem.text.strip()

        # ExtendedData: SimpleData
        for sd in pm.findall(f".//{ns}SimpleData"):
            key = sd.attrib.get("name")
            if key and sd.text:
                record[key] = sd.text.strip()

        # ExtendedData: Data
        for d in pm.findall(f".//{ns}Data"):
            key = d.attrib.get("name")
            val = d.find(f"{ns}value")
            if key and val is not None and val.text:
                record[key] = val.text.strip()

        # Extract Geometry
        geom = None
        # Check MultiGeometry
        multi_geom = pm.find(f".//{ns}MultiGeometry")
        if multi_geom is not None:
            polygons: list[Polygon] = []
            for p_elem in multi_geom.findall(f".//{ns}Polygon"):
                p = _parse_polygon_element(p_elem, ns)
                if p is not None:
                    if isinstance(p, Polygon):
                        polygons.append(p)
                    elif isinstance(p, MultiPolygon):
                        polygons.extend(list(p.geoms))
            if polygons:
                geom = MultiPolygon(polygons)
        else:
            poly_elem = pm.find(f".//{ns}Polygon")
            if poly_elem is not None:
                geom = _parse_polygon_element(poly_elem, ns)
            else:
                point_elem = pm.find(f".//{ns}Point//{ns}coordinates")
                if point_elem is not None and point_elem.text:
                    pts = _parse_coord_string(point_elem.text)
                    if pts:
                        geom = Point(pts[0])

        if geom is None:
            logger.warning("Placemark %d has no parsable geometry", idx)
            continue

        record["geometry"] = geom
        records.append(record)

    if not records:
        raise ValueError(f"No valid Placemark features with geometry found in {file_path}")

    gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")
    return gdf


def read_district_kml(file_path: str) -> gpd.GeoDataFrame:
    """Read a Bangkok district boundary KML file into a GeoDataFrame (Tasks P2-01 & P2-02).

    Tries pyogrio / fiona first; seamlessly falls back to pure Python XML parsing
    if KML GDAL drivers are not supported or configured on the host system.

    Args:
        file_path: Path string to the .kml boundary file.

    Returns:
        gpd.GeoDataFrame with extracted district attributes and polygon geometries in EPSG:4326.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"District KML file not found: {file_path}")

    gdf: gpd.GeoDataFrame | None = None

    # Try pyogrio engine first
    try:
        gdf = gpd.read_file(path, engine="pyogrio")
    except Exception as pyogrio_err:
        logger.debug("pyogrio read_file failed for %s: %s", path, pyogrio_err)

    # Try fiona with KML driver enabled
    if gdf is None:
        try:
            import fiona
            if "KML" not in fiona.supported_drivers:
                fiona.drvsupport.supported_drivers["KML"] = "rw"
                fiona.drvsupport.supported_drivers["LIBKML"] = "rw"
            gdf = gpd.read_file(path, engine="fiona")
        except Exception as fiona_err:
            logger.debug("fiona read_file failed for %s: %s", path, fiona_err)

    # Fallback to pure XML parsing
    if gdf is None:
        logger.info("Using XML fallback parser for KML file: %s", path)
        gdf = _parse_kml_xml(path)

    # Ensure CRS is set
    if gdf.crs is None:
        gdf.set_crs("EPSG:4326", inplace=True)
    elif str(gdf.crs).upper() != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")

    # Ensure all geometries are valid
    gdf["geometry"] = gdf["geometry"].apply(lambda g: make_valid(g) if g is not None and not g.is_valid else g)

    # Drop empty geometries if any
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].copy()

    logger.info("Successfully loaded %d district boundaries from %s", len(gdf), path.name)
    return gdf
