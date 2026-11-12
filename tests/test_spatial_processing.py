"""Unit and integration tests for Person 2 spatial data processing module."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import MultiPolygon, Point, Polygon

from spatial.centroid import calculate_centroids, export_coordinates
from spatial.coordinate_validator import (
    SpatialValidationError,
    run_full_validation,
    validate_coordinates,
    validate_crs,
    validate_district_count,
    validate_representative_points,
)
from spatial.district_processor import (
    CANONICAL_BANGKOK_DISTRICTS,
    normalize_district_name,
    process_district_coordinates,
    standardize_districts,
)
from spatial.kml_reader import (
    _parse_kml_xml,
    inspect_kml,
    read_district_kml,
)

KML_TEST_PATH = Path("data/bangkok_districts.kml")


# =====================================================================
# Task P2-01: KML inspection tests
# =====================================================================

def test_inspect_kml_success() -> None:
    """Verify inspect_kml returns accurate metadata and 50 features."""
    assert KML_TEST_PATH.is_file(), "data/bangkok_districts.kml must exist"
    report = inspect_kml(KML_TEST_PATH)

    assert report["feature_count"] == 50
    assert report["default_crs"] == "EPSG:4326"
    assert "Polygon" in report["detected_geometry_types"] or "MultiGeometry" in report["detected_geometry_types"]
    assert len(report["sample_placemarks"]) > 0


def test_inspect_kml_missing_file() -> None:
    """Verify FileNotFoundError is raised when inspecting non-existent file."""
    with pytest.raises(FileNotFoundError, match="KML file not found"):
        inspect_kml("data/non_existent_file.kml")


# =====================================================================
# Task P2-02: Data extraction (kml_reader) tests
# =====================================================================

def test_read_district_kml_success() -> None:
    """Verify read_district_kml extracts 50 valid district boundaries in EPSG:4326."""
    gdf = read_district_kml(str(KML_TEST_PATH))

    assert isinstance(gdf, gpd.GeoDataFrame)
    assert len(gdf) == 50
    assert gdf.crs is not None
    assert "4326" in str(gdf.crs)
    assert all(geom is not None and not geom.is_empty for geom in gdf.geometry)


def test_read_district_kml_missing_file() -> None:
    """Verify FileNotFoundError is raised for invalid file path."""
    with pytest.raises(FileNotFoundError, match="District KML file not found"):
        read_district_kml("missing_districts.kml")


def test_fallback_kml_xml_parser(tmp_path: Path) -> None:
    """Verify fallback XML parser parses placemarks, ExtendedData, and Polygons."""
    sample_kml_content = """<?xml version="1.0" encoding="utf-8" ?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
      <Placemark>
        <name>Bang Rak</name>
        <ExtendedData>
          <Data name="dcode"><value>1004</value></Data>
          <Data name="dname_e"><value>Bang Rak</value></Data>
        </ExtendedData>
        <Polygon>
          <outerBoundaryIs>
            <LinearRing>
              <coordinates>
                100.52,13.72,0 100.53,13.72,0 100.53,13.73,0 100.52,13.73,0 100.52,13.72,0
              </coordinates>
            </LinearRing>
          </outerBoundaryIs>
        </Polygon>
      </Placemark>
    </Document>
    </kml>
    """
    kml_file = tmp_path / "custom.kml"
    kml_file.write_text(sample_kml_content, encoding="utf-8")

    gdf = _parse_kml_xml(kml_file)
    assert len(gdf) == 1
    assert gdf.iloc[0]["name"] == "Bang Rak"
    assert gdf.iloc[0]["dcode"] == "1004"
    assert isinstance(gdf.iloc[0].geometry, Polygon)


# =====================================================================
# Task P2-04: Name normalization tests
# =====================================================================

def test_normalize_district_names_canonical() -> None:
    """Ensure all 50 canonical Bangkok district names map cleanly to themselves."""
    for district in CANONICAL_BANGKOK_DISTRICTS:
        assert normalize_district_name(district) == district
        assert normalize_district_name(district.lower()) == district


def test_normalize_district_names_thai_and_prefixes() -> None:
    """Verify Thai district names, prefixes ('เขต'), and transliterations normalize."""
    # Thai script
    assert normalize_district_name("เขตบางรัก") == "Bang Rak"
    assert normalize_district_name("บางรัก") == "Bang Rak"
    assert normalize_district_name("เขตปทุมวัน") == "Pathum Wan"
    assert normalize_district_name("จตุจักร") == "Chatuchak"
    assert normalize_district_name("เขตพระนคร") == "Phra Nakhon"

    # English prefixes
    assert normalize_district_name("Khet Bang Rak") == "Bang Rak"
    assert normalize_district_name("Chatuchak District") == "Chatuchak"

    # Common transliteration anomalies & dataset typos
    assert normalize_district_name("Parthum Wan") == "Pathum Wan"
    assert normalize_district_name("Bang Kho laen") == "Bang Kho Laem"
    assert normalize_district_name("Bang Khun thain") == "Bang Khun Thian"
    assert normalize_district_name("Wang Thong Lang") == "Wang Thonglang"
    assert normalize_district_name("Klong Toey") == "Khlong Toei"
    assert normalize_district_name("Jatujak") == "Chatuchak"

    # District administrative codes
    assert normalize_district_name("1001") == "Phra Nakhon"
    assert normalize_district_name("1004") == "Bang Rak"
    assert normalize_district_name("1030") == "Chatuchak"


def test_normalize_district_name_invalid() -> None:
    """Verify error on empty / NaN name."""
    with pytest.raises(ValueError, match="Cannot normalize empty or null"):
        normalize_district_name(None)


def test_standardize_districts_dataframe() -> None:
    """Verify standardize_districts identifies name column and adds clean 'district' column."""
    df = gpd.GeoDataFrame({
        "dname_e": ["Bang Rak", "Parthum Wan", "Chatuchak"],
        "geometry": [Point(100.5, 13.7), Point(100.5, 13.7), Point(100.5, 13.8)],
    })
    standardized = standardize_districts(df)
    assert "district" in standardized.columns
    assert standardized["district"].tolist() == ["Bang Rak", "Pathum Wan", "Chatuchak"]


# =====================================================================
# Task P2-05: Centroid calculation & irregular district handling
# =====================================================================

def test_calculate_centroids_real_kml() -> None:
    """Verify centroids calculation generates valid latitude/longitude for all 50 districts."""
    gdf = read_district_kml(str(KML_TEST_PATH))
    standardized = standardize_districts(gdf)
    result = calculate_centroids(standardized)

    assert len(result) == 50
    assert "latitude" in result.columns
    assert "longitude" in result.columns

    # Verify latitude and longitude ranges
    assert (result["latitude"] >= 13.4).all() and (result["latitude"] <= 14.1).all()
    assert (result["longitude"] >= 100.2).all() and (result["longitude"] <= 101.0).all()

    # Geometry column should be Points in EPSG:4326
    assert all(isinstance(geom, Point) for geom in result.geometry)
    assert "4326" in str(result.crs)


def test_calculate_centroids_irregular_horseshoe_polygon() -> None:
    """Crucial Acceptance Criteria: When geometric centroid falls outside an irregular

    polygon (e.g. U-shaped / crescent), ensure calculate_centroids detects this and falls back
    to representative_point() inside the polygon.
    """
    # Create U-shaped / horseshoe polygon in Bangkok coordinates (around 100.5, 13.7)
    # A horseshoe whose center of mass is inside the empty cutout
    pts = [
        (100.50, 13.70),
        (100.53, 13.70),
        (100.53, 13.73),
        (100.52, 13.73),
        (100.52, 13.71),
        (100.51, 13.71),
        (100.51, 13.73),
        (100.50, 13.73),
        (100.50, 13.70),
    ]
    u_poly = Polygon(pts)
    gdf = gpd.GeoDataFrame(
        [{"district": "Irregular_District", "geometry": u_poly}],
        crs="EPSG:4326",
    )

    # In UTM Zone 47N, geometric centroid will fall into the cutout (not contained)
    gdf_utm = gdf.to_crs(32647)
    utm_poly = gdf_utm.iloc[0].geometry
    utm_centroid = utm_poly.centroid
    assert not utm_poly.contains(utm_centroid), "Geometric centroid must fall outside the U-shape"

    # calculate_centroids must automatically fall back to representative point inside
    res = calculate_centroids(gdf)
    res_point_utm = res.to_crs(32647).iloc[0].geometry

    # Must be strictly contained in the polygon boundary
    assert utm_poly.contains(res_point_utm) or utm_poly.covers(res_point_utm)
    assert res.iloc[0]["latitude"] > 0
    assert res.iloc[0]["longitude"] > 0


# =====================================================================
# Tasks P2-03 & P2-06: Coordinate validation tests
# =====================================================================

def test_validate_crs_success_and_failure() -> None:
    """Verify validate_crs enforces correct CRS."""
    gdf = gpd.GeoDataFrame({"geometry": [Point(0, 0)]}, crs="EPSG:4326")
    assert validate_crs(gdf, "EPSG:4326") is True

    # Missing CRS
    gdf_nocrs = gpd.GeoDataFrame({"geometry": [Point(0, 0)]})
    with pytest.raises(SpatialValidationError, match="no CRS defined"):
        validate_crs(gdf_nocrs)

    # Wrong CRS
    gdf_3857 = gpd.GeoDataFrame({"geometry": [Point(0, 0)]}, crs="EPSG:3857")
    with pytest.raises(SpatialValidationError, match="Expected CRS"):
        validate_crs(gdf_3857, "EPSG:4326")


def test_validate_coordinates_bounds_and_inverted() -> None:
    """Verify validate_coordinates rejects out of bounds, inverted, or null values."""
    # Good coordinates
    good_df = pd.DataFrame([{"latitude": 13.75, "longitude": 100.50}])
    assert validate_coordinates(good_df) is True

    # Out of bounds lat
    bad_lat = pd.DataFrame([{"latitude": 14.50, "longitude": 100.50}])
    with pytest.raises(SpatialValidationError, match="latitude values outside Bangkok bounds"):
        validate_coordinates(bad_lat)

    # Inverted coordinates (lat and lon swapped)
    inverted = pd.DataFrame([{"latitude": 100.50, "longitude": 13.75}])
    with pytest.raises(SpatialValidationError, match="inverted"):
        validate_coordinates(inverted)

    # Null coordinates
    null_coords = pd.DataFrame([{"latitude": None, "longitude": 100.50}])
    with pytest.raises(SpatialValidationError, match="null"):
        validate_coordinates(null_coords)


def test_validate_representative_points_inside_polygon() -> None:
    """Verify points outside boundary are caught."""
    poly = Polygon([(100.50, 13.70), (100.52, 13.70), (100.52, 13.72), (100.50, 13.72), (100.50, 13.70)])
    gdf_poly = gpd.GeoDataFrame([{"district": "TestDistrict", "geometry": poly}], crs="EPSG:4326")

    # Point inside
    inside_pts = gpd.GeoDataFrame([{"district": "TestDistrict", "geometry": Point(100.51, 13.71)}], crs="EPSG:4326")
    assert validate_representative_points(gdf_poly, inside_pts) is True

    # Point outside
    outside_pts = gpd.GeoDataFrame([{"district": "TestDistrict", "geometry": Point(100.55, 13.75)}], crs="EPSG:4326")
    with pytest.raises(SpatialValidationError, match="fall outside their district boundary"):
        validate_representative_points(gdf_poly, outside_pts)


def test_validate_district_count() -> None:
    """Verify 50 districts requirement."""
    df_50 = pd.DataFrame({"district": [f"D_{i}" for i in range(50)]})
    assert validate_district_count(df_50, expected_count=50) is True

    # 49 districts
    df_49 = pd.DataFrame({"district": [f"D_{i}" for i in range(49)]})
    with pytest.raises(SpatialValidationError, match="Expected 50 districts, but found 49"):
        validate_district_count(df_49, expected_count=50)

    # Duplicates
    df_dups = pd.DataFrame({"district": ["Same"] * 50})
    with pytest.raises(SpatialValidationError, match="unique districts"):
        validate_district_count(df_dups, expected_count=50)


# =====================================================================
# Task P2-07: Output preparation & End-to-end integration
# =====================================================================

def test_export_coordinates(tmp_path: Path) -> None:
    """Verify export_coordinates creates valid CSV with district, latitude, longitude."""
    sample_gdf = gpd.GeoDataFrame({
        "district": ["Bang Rak", "Chatuchak"],
        "latitude": [13.727025, 13.826520],
        "longitude": [100.524247, 100.565141],
        "geometry": [Point(100.524247, 13.727025), Point(100.565141, 13.826520)],
    }, crs="EPSG:4326")

    out_csv = tmp_path / "district_coordinates.csv"
    export_coordinates(sample_gdf, str(out_csv))

    assert out_csv.is_file()
    read_df = pd.read_csv(out_csv)
    assert list(read_df.columns) == ["district", "latitude", "longitude"]
    assert len(read_df) == 2
    assert read_df.iloc[0]["district"] == "Bang Rak"


def test_full_pipeline_run(tmp_path: Path) -> None:
    """Verify process_district_coordinates executes end-to-end and fulfills all acceptance criteria."""
    out_csv = tmp_path / "final_districts.csv"
    res_gdf = process_district_coordinates(
        kml_path=KML_TEST_PATH,
        output_path=out_csv,
        green_space_csv="data/green_space.csv",
    )

    assert len(res_gdf) == 50
    assert out_csv.is_file()

    df = pd.read_csv(out_csv)
    assert len(df) == 50
    assert list(df.columns) == ["district", "latitude", "longitude"]
    assert df["district"].nunique() == 50

    # Full validation
    validation = run_full_validation(read_district_kml(str(KML_TEST_PATH)), res_gdf)
    assert validation["status"] == "PASSED"
    assert all(status == "PASSED" for status in validation["checks"].values())
