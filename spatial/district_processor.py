"""District name standardization, normalization, and processing module."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from spatial.centroid import calculate_centroids, export_coordinates
from spatial.kml_reader import read_district_kml

logger = logging.getLogger(__name__)

# Complete canonical mapping for Bangkok's 50 administrative districts
# Maps Thai names, English variations, common transliterations, and administrative codes
CANONICAL_BANGKOK_DISTRICTS: list[str] = [
    "Bang Bon",
    "Bang Kapi",
    "Bang Khae",
    "Bang Khen",
    "Bang Kho Laem",
    "Bang Khun Thian",
    "Bang Na",
    "Bang Phlat",
    "Bang Rak",
    "Bang Sue",
    "Bangkok Noi",
    "Bangkok Yai",
    "Bueng Kum",
    "Chatuchak",
    "Chom Thong",
    "Din Daeng",
    "Don Mueang",
    "Dusit",
    "Huai Khwang",
    "Khan Na Yao",
    "Khlong Sam Wa",
    "Khlong San",
    "Khlong Toei",
    "Lak Si",
    "Lat Krabang",
    "Lat Phrao",
    "Min Buri",
    "Nong Chok",
    "Nong Khaem",
    "Pathum Wan",
    "Phasi Charoen",
    "Phaya Thai",
    "Phra Khanong",
    "Phra Nakhon",
    "Pom Prap Sattru Phai",
    "Prawet",
    "Rat Burana",
    "Ratchathewi",
    "Sai Mai",
    "Samphanthawong",
    "Saphan Sung",
    "Sathon",
    "Suan Luang",
    "Taling Chan",
    "Thawi Watthana",
    "Thon Buri",
    "Thung Khru",
    "Wang Thonglang",
    "Watthana",
    "Yan Nawa",
]

# Normalization lookup table
DISTRICT_LOOKUP: dict[str, str] = {
    # 1001: Phra Nakhon
    "1001": "Phra Nakhon", "1": "Phra Nakhon", "001": "Phra Nakhon",
    "พระนคร": "Phra Nakhon", "เขตพระนคร": "Phra Nakhon",
    "phra nakhon": "Phra Nakhon", "phranakhon": "Phra Nakhon", "phra nakorn": "Phra Nakhon", "pranakorn": "Phra Nakhon",

    # 1002: Dusit
    "1002": "Dusit", "2": "Dusit", "002": "Dusit",
    "ดุสิต": "Dusit", "เขตดุสิต": "Dusit",
    "dusit": "Dusit",

    # 1003: Nong Chok
    "1003": "Nong Chok", "3": "Nong Chok", "003": "Nong Chok",
    "หนองจอก": "Nong Chok", "เขตหนองจอก": "Nong Chok",
    "nong chok": "Nong Chok", "nongchok": "Nong Chok",

    # 1004: Bang Rak
    "1004": "Bang Rak", "4": "Bang Rak", "004": "Bang Rak",
    "บางรัก": "Bang Rak", "เขตบางรัก": "Bang Rak",
    "bang rak": "Bang Rak", "bangrak": "Bang Rak",

    # 1005: Bang Khen
    "1005": "Bang Khen", "5": "Bang Khen", "005": "Bang Khen",
    "บางเขน": "Bang Khen", "เขตบางเขน": "Bang Khen",
    "bang khen": "Bang Khen", "bangkhen": "Bang Khen",

    # 1006: Bang Kapi
    "1006": "Bang Kapi", "6": "Bang Kapi", "006": "Bang Kapi",
    "บางกะปิ": "Bang Kapi", "เขตบางกะปิ": "Bang Kapi",
    "bang kapi": "Bang Kapi", "bangkapi": "Bang Kapi",

    # 1007: Pathum Wan
    "1007": "Pathum Wan", "7": "Pathum Wan", "007": "Pathum Wan",
    "ปทุมวัน": "Pathum Wan", "เขตปทุมวัน": "Pathum Wan",
    "pathum wan": "Pathum Wan", "pathumwan": "Pathum Wan", "patumwan": "Pathum Wan",
    "parthum wan": "Pathum Wan", "parthumwan": "Pathum Wan",

    # 1008: Pom Prap Sattru Phai
    "1008": "Pom Prap Sattru Phai", "8": "Pom Prap Sattru Phai", "008": "Pom Prap Sattru Phai",
    "ป้อมปราบศัตรูพ่าย": "Pom Prap Sattru Phai", "เขตป้อมปราบศัตรูพ่าย": "Pom Prap Sattru Phai",
    "pom prap sattru phai": "Pom Prap Sattru Phai", "pomprap sattru phai": "Pom Prap Sattru Phai",
    "pomprapsattruphai": "Pom Prap Sattru Phai", "pom prap": "Pom Prap Sattru Phai", "pomprap": "Pom Prap Sattru Phai",

    # 1009: Phra Khanong
    "1009": "Phra Khanong", "9": "Phra Khanong", "009": "Phra Khanong",
    "พระโขนง": "Phra Khanong", "เขตพระโขนง": "Phra Khanong",
    "phra khanong": "Phra Khanong", "phrakhanong": "Phra Khanong",

    # 1010: Min Buri
    "1010": "Min Buri", "10": "Min Buri", "010": "Min Buri",
    "มีนบุรี": "Min Buri", "เขตมีนบุรี": "Min Buri",
    "min buri": "Min Buri", "minburi": "Min Buri",

    # 1011: Lat Krabang
    "1011": "Lat Krabang", "11": "Lat Krabang", "011": "Lat Krabang",
    "ลาดกระบัง": "Lat Krabang", "เขตลาดกระบัง": "Lat Krabang",
    "lat krabang": "Lat Krabang", "latkrabang": "Lat Krabang", "ladkrabang": "Lat Krabang", "lad krabang": "Lat Krabang",

    # 1012: Yan Nawa
    "1012": "Yan Nawa", "12": "Yan Nawa", "012": "Yan Nawa",
    "ยานนาวา": "Yan Nawa", "เขตยานนาวา": "Yan Nawa",
    "yan nawa": "Yan Nawa", "yannawa": "Yan Nawa",

    # 1013: Samphanthawong
    "1013": "Samphanthawong", "13": "Samphanthawong", "013": "Samphanthawong",
    "สัมพันธวงศ์": "Samphanthawong", "เขตสัมพันธวงศ์": "Samphanthawong",
    "samphanthawong": "Samphanthawong", "sampanthawong": "Samphanthawong",

    # 1014: Phaya Thai
    "1014": "Phaya Thai", "14": "Phaya Thai", "014": "Phaya Thai",
    "พญาไท": "Phaya Thai", "เขตพญาไท": "Phaya Thai",
    "phaya thai": "Phaya Thai", "phayathai": "Phaya Thai",

    # 1015: Thon Buri
    "1015": "Thon Buri", "15": "Thon Buri", "015": "Thon Buri",
    "ธนบุรี": "Thon Buri", "เขตธนบุรี": "Thon Buri",
    "thon buri": "Thon Buri", "thonburi": "Thon Buri",

    # 1016: Bangkok Yai
    "1016": "Bangkok Yai", "16": "Bangkok Yai", "016": "Bangkok Yai",
    "บางกอกใหญ่": "Bangkok Yai", "เขตบางกอกใหญ่": "Bangkok Yai",
    "bangkok yai": "Bangkok Yai", "bangkokyai": "Bangkok Yai",

    # 1017: Huai Khwang
    "1017": "Huai Khwang", "17": "Huai Khwang", "017": "Huai Khwang",
    "ห้วยขวาง": "Huai Khwang", "เขตห้วยขวาง": "Huai Khwang",
    "huai khwang": "Huai Khwang", "huaikhwang": "Huai Khwang", "huay kwang": "Huai Khwang", "huaykwang": "Huai Khwang",

    # 1018: Khlong San
    "1018": "Khlong San", "18": "Khlong San", "018": "Khlong San",
    "คลองสาน": "Khlong San", "เขตคลองสาน": "Khlong San",
    "khlong san": "Khlong San", "khlongsan": "Khlong San", "klong san": "Khlong San",

    # 1019: Taling Chan
    "1019": "Taling Chan", "19": "Taling Chan", "019": "Taling Chan",
    "ตลิ่งชัน": "Taling Chan", "เขตตลิ่งชัน": "Taling Chan",
    "taling chan": "Taling Chan", "talingchan": "Taling Chan",

    # 1020: Bangkok Noi
    "1020": "Bangkok Noi", "20": "Bangkok Noi", "020": "Bangkok Noi",
    "บางกอกน้อย": "Bangkok Noi", "เขตบางกอกน้อย": "Bangkok Noi",
    "bangkok noi": "Bangkok Noi", "bangkoknoi": "Bangkok Noi",

    # 1021: Bang Khun Thian
    "1021": "Bang Khun Thian", "21": "Bang Khun Thian", "021": "Bang Khun Thian",
    "บางขุนเทียน": "Bang Khun Thian", "เขตบางขุนเทียน": "Bang Khun Thian",
    "bang khun thian": "Bang Khun Thian", "bangkhunthian": "Bang Khun Thian", "bang khun thien": "Bang Khun Thian",
    "bang khun thain": "Bang Khun Thian", "bangkhunthain": "Bang Khun Thian",

    # 1022: Phasi Charoen
    "1022": "Phasi Charoen", "22": "Phasi Charoen", "022": "Phasi Charoen",
    "ภาษีเจริญ": "Phasi Charoen", "เขตภาษีเจริญ": "Phasi Charoen",
    "phasi charoen": "Phasi Charoen", "phasicharoen": "Phasi Charoen", "pasicharoen": "Phasi Charoen",

    # 1023: Nong Khaem
    "1023": "Nong Khaem", "23": "Nong Khaem", "023": "Nong Khaem",
    "หนองแขม": "Nong Khaem", "เขตหนองแขม": "Nong Khaem",
    "nong khaem": "Nong Khaem", "nongkhaem": "Nong Khaem",

    # 1024: Rat Burana
    "1024": "Rat Burana", "24": "Rat Burana", "024": "Rat Burana",
    "ราษฎร์บูรณะ": "Rat Burana", "เขตราษฎร์บูรณะ": "Rat Burana",
    "rat burana": "Rat Burana", "ratburana": "Rat Burana", "rajburana": "Rat Burana",

    # 1025: Bang Phlat
    "1025": "Bang Phlat", "25": "Bang Phlat", "025": "Bang Phlat",
    "บางพลัด": "Bang Phlat", "เขตบางพลัด": "Bang Phlat",
    "bang phlat": "Bang Phlat", "bangphlat": "Bang Phlat", "bang plat": "Bang Phlat",

    # 1026: Din Daeng
    "1026": "Din Daeng", "26": "Din Daeng", "026": "Din Daeng",
    "ดินแดง": "Din Daeng", "เขตดินแดง": "Din Daeng",
    "din daeng": "Din Daeng", "dindaeng": "Din Daeng",

    # 1027: Bueng Kum
    "1027": "Bueng Kum", "27": "Bueng Kum", "027": "Bueng Kum",
    "บึงกุ่ม": "Bueng Kum", "เขตบึงกุ่ม": "Bueng Kum",
    "bueng kum": "Bueng Kum", "buengkum": "Bueng Kum", "bung kum": "Bueng Kum",

    # 1028: Sathon
    "1028": "Sathon", "28": "Sathon", "028": "Sathon",
    "สาทร": "Sathon", "เขตสาทร": "Sathon",
    "sathon": "Sathon", "sathorn": "Sathon",

    # 1029: Bang Sue
    "1029": "Bang Sue", "29": "Bang Sue", "029": "Bang Sue",
    "บางซื่อ": "Bang Sue", "เขตบางซื่อ": "Bang Sue",
    "bang sue": "Bang Sue", "bangsue": "Bang Sue",

    # 1030: Chatuchak
    "1030": "Chatuchak", "30": "Chatuchak", "030": "Chatuchak",
    "จตุจักร": "Chatuchak", "เขตจตุจักร": "Chatuchak",
    "chatuchak": "Chatuchak", "jatujak": "Chatuchak", "chatujak": "Chatuchak",

    # 1031: Bang Kho Laem
    "1031": "Bang Kho Laem", "31": "Bang Kho Laem", "031": "Bang Kho Laem",
    "บางคอแหลม": "Bang Kho Laem", "เขตบางคอแหลม": "Bang Kho Laem",
    "bang kho laem": "Bang Kho Laem", "bangkholaem": "Bang Kho Laem",
    "bang kho laen": "Bang Kho Laem", "bangkholaen": "Bang Kho Laem",

    # 1032: Prawet
    "1032": "Prawet", "32": "Prawet", "032": "Prawet",
    "ประเวศ": "Prawet", "เขตประเวศ": "Prawet",
    "prawet": "Prawet",

    # 1033: Khlong Toei
    "1033": "Khlong Toei", "33": "Khlong Toei", "033": "Khlong Toei",
    "คลองเตย": "Khlong Toei", "เขตคลองเตย": "Khlong Toei",
    "khlong toei": "Khlong Toei", "khlongtoei": "Khlong Toei", "klong toey": "Khlong Toei", "klongtoey": "Khlong Toei", "khlong toey": "Khlong Toei",

    # 1034: Suan Luang
    "1034": "Suan Luang", "34": "Suan Luang", "034": "Suan Luang",
    "สวนหลวง": "Suan Luang", "เขตสวนหลวง": "Suan Luang",
    "suan luang": "Suan Luang", "suanluang": "Suan Luang",

    # 1035: Chom Thong
    "1035": "Chom Thong", "35": "Chom Thong", "035": "Chom Thong",
    "จอมทอง": "Chom Thong", "เขตจอมทอง": "Chom Thong",
    "chom thong": "Chom Thong", "chomthong": "Chom Thong",

    # 1036: Don Mueang
    "1036": "Don Mueang", "36": "Don Mueang", "036": "Don Mueang",
    "ดอนเมือง": "Don Mueang", "เขตดอนเมือง": "Don Mueang",
    "don mueang": "Don Mueang", "donmueang": "Don Mueang", "don muang": "Don Mueang", "donmuang": "Don Mueang",

    # 1037: Ratchathewi
    "1037": "Ratchathewi", "37": "Ratchathewi", "037": "Ratchathewi",
    "ราชเทวี": "Ratchathewi", "เขตราชเทวี": "Ratchathewi",
    "ratchathewi": "Ratchathewi", "rajthevi": "Ratchathewi", "rajthevee": "Ratchathewi",

    # 1038: Lat Phrao
    "1038": "Lat Phrao", "38": "Lat Phrao", "038": "Lat Phrao",
    "ลาดพร้าว": "Lat Phrao", "เขตลาดพร้าว": "Lat Phrao",
    "lat phrao": "Lat Phrao", "latprao": "Lat Phrao", "ladprao": "Lat Phrao", "lad phrao": "Lat Phrao",

    # 1039: Watthana
    "1039": "Watthana", "39": "Watthana", "039": "Watthana",
    "วัฒนา": "Watthana", "เขตวัฒนา": "Watthana",
    "watthana": "Watthana", "vadhana": "Watthana",

    # 1040: Bang Khae
    "1040": "Bang Khae", "40": "Bang Khae", "040": "Bang Khae",
    "บางแค": "Bang Khae", "เขตบางแค": "Bang Khae",
    "bang khae": "Bang Khae", "bangkhae": "Bang Khae",

    # 1041: Lak Si
    "1041": "Lak Si", "41": "Lak Si", "041": "Lak Si",
    "หลักสี่": "Lak Si", "เขตหลักสี่": "Lak Si",
    "lak si": "Lak Si", "laksi": "Lak Si",

    # 1042: Sai Mai
    "1042": "Sai Mai", "42": "Sai Mai", "042": "Sai Mai",
    "สายไหม": "Sai Mai", "เขตสายไหม": "Sai Mai",
    "sai mai": "Sai Mai", "saimai": "Sai Mai",

    # 1043: Khan Na Yao
    "1043": "Khan Na Yao", "43": "Khan Na Yao", "043": "Khan Na Yao",
    "คันนายาว": "Khan Na Yao", "เขตคันนายาว": "Khan Na Yao",
    "khan na yao": "Khan Na Yao", "khannayao": "Khan Na Yao",

    # 1044: Saphan Sung
    "1044": "Saphan Sung", "44": "Saphan Sung", "044": "Saphan Sung",
    "สะพานสูง": "Saphan Sung", "เขตสะพานสูง": "Saphan Sung",
    "saphan sung": "Saphan Sung", "saphansung": "Saphan Sung",

    # 1045: Wang Thonglang
    "1045": "Wang Thonglang", "45": "Wang Thonglang", "045": "Wang Thonglang",
    "วังทองหลาง": "Wang Thonglang", "เขตวังทองหลาง": "Wang Thonglang",
    "wang thonglang": "Wang Thonglang", "wang thong lang": "Wang Thonglang", "wangthonglang": "Wang Thonglang",

    # 1046: Khlong Sam Wa
    "1046": "Khlong Sam Wa", "46": "Khlong Sam Wa", "046": "Khlong Sam Wa",
    "คลองสามวา": "Khlong Sam Wa", "เขตคลองสามวา": "Khlong Sam Wa",
    "khlong sam wa": "Khlong Sam Wa", "khlongsamwa": "Khlong Sam Wa", "klong sam wa": "Khlong Sam Wa",

    # 1047: Bang Na
    "1047": "Bang Na", "47": "Bang Na", "047": "Bang Na",
    "บางนา": "Bang Na", "เขตบางนา": "Bang Na",
    "bang na": "Bang Na", "bangna": "Bang Na",

    # 1048: Thawi Watthana
    "1048": "Thawi Watthana", "48": "Thawi Watthana", "048": "Thawi Watthana",
    "ทวีวัฒนา": "Thawi Watthana", "เขตทวีวัฒนา": "Thawi Watthana",
    "thawi watthana": "Thawi Watthana", "thawiwatthana": "Thawi Watthana", "tawee wattana": "Thawi Watthana",

    # 1049: Thung Khru
    "1049": "Thung Khru", "49": "Thung Khru", "049": "Thung Khru",
    "ทุ่งครุ": "Thung Khru", "เขตทุ่งครุ": "Thung Khru",
    "thung khru": "Thung Khru", "thungkhru": "Thung Khru",

    # 1050: Bang Bon
    "1050": "Bang Bon", "50": "Bang Bon", "050": "Bang Bon",
    "บางบอน": "Bang Bon", "เขตบางบอน": "Bang Bon",
    "bang bon": "Bang Bon", "bangbon": "Bang Bon",
}


def normalize_district_name(raw_name: Any) -> str:
    """Normalize raw district name or code into standardized English name (Task P2-04).

    Compatible with green-space datasets, Person 1 weather coordinates, and BMA standards.

    Args:
        raw_name: Input string, int, or code representing the district.

    Returns:
        Standardized canonical English district name (e.g., 'Bang Rak').
    """
    if raw_name is None or pd.isna(raw_name):
        raise ValueError("Cannot normalize empty or null district name.")

    name_str = str(raw_name).strip()

    # Exact or lowercase lookup
    lower_str = name_str.lower()
    if lower_str in DISTRICT_LOOKUP:
        return DISTRICT_LOOKUP[lower_str]

    # Clean Thai prefixes like 'เขต'
    cleaned = re.sub(r"^(เขต|แขวง)\s*", "", name_str).strip()
    if cleaned.lower() in DISTRICT_LOOKUP:
        return DISTRICT_LOOKUP[cleaned.lower()]

    # Clean English prefixes/suffixes like 'Khet', 'District of', 'District'
    cleaned = re.sub(r"^(khet|district of)\s+", "", name_str, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+district$", "", cleaned, flags=re.IGNORECASE).strip()
    if cleaned.lower() in DISTRICT_LOOKUP:
        return DISTRICT_LOOKUP[cleaned.lower()]

    # Normalize whitespace and hyphens
    condensed = re.sub(r"[\s\-_]+", " ", cleaned).lower()
    if condensed in DISTRICT_LOOKUP:
        return DISTRICT_LOOKUP[condensed]

    no_spaces = re.sub(r"[\s\-_]+", "", cleaned).lower()
    if no_spaces in DISTRICT_LOOKUP:
        return DISTRICT_LOOKUP[no_spaces]

    # Fallback: Capitalize words
    title_cased = cleaned.title()
    logger.warning("Unrecognized district name '%s'; defaulting to title-cased '%s'", raw_name, title_cased)
    return title_cased


def standardize_districts(
    gdf: gpd.GeoDataFrame,
    name_col: str | None = None,
    output_col: str = "district",
) -> gpd.GeoDataFrame:
    """Standardize district names across GeoDataFrame (Task P2-04).

    Standardizes names to match the green-space CSV dataset.
    Identifies candidate columns ('dname_e', 'dname', 'district', 'name', 'dcode')
    and creates a clean 'district' column.

    Args:
        gdf: GeoDataFrame containing district boundaries and attributes.
        name_col: Specific column to normalize from. If None, auto-detected.
        output_col: Name of column to write normalized names to (default 'district').

    Returns:
        GeoDataFrame with standardized district names.
    """
    if gdf.empty:
        raise ValueError("Cannot standardize an empty GeoDataFrame.")

    result = gdf.copy()

    # Detect name column if not explicitly given
    col_to_use = name_col
    if col_to_use is None:
        candidates = ["dname_e", "district", "district_name", "dname", "name", "dcode", "Name"]
        for cand in candidates:
            if cand in result.columns:
                col_to_use = cand
                break
        if col_to_use is None:
            raise KeyError(f"Could not find district name column among {list(result.columns)}")

    logger.info("Normalizing district names using source column '%s'", col_to_use)
    result[output_col] = result[col_to_use].apply(normalize_district_name)

    # Check for duplicate district names
    duplicates = result[output_col][result[output_col].duplicated()].tolist()
    if duplicates:
        logger.warning("Duplicate standardized district names detected: %s", duplicates)

    return result


def process_district_coordinates(
    kml_path: str | Path,
    output_path: str | Path = "data/district_coordinates.csv",
    green_space_csv: str | Path | None = None,
) -> gpd.GeoDataFrame:
    """Execute end-to-end spatial data processing pipeline (Tasks P2-01 to P2-07).

    Steps:
    1. Reads district boundaries from KML.
    2. Extracts district attributes and validates boundary geometries.
    3. Standardizes district names to match green-space dataset standards.
    4. Computes representative points using projected metric CRS (EPSG:32647).
    5. Validates representative points fall inside district boundaries.
    6. Exports clean district coordinate CSV table.

    Args:
        kml_path: Path to input KML boundary file.
        output_path: Destination path for exported coordinate CSV.
        green_space_csv: Optional path to green-space CSV to verify compatibility against.

    Returns:
        Processed GeoDataFrame with 50 districts and coordinates.
    """
    logger.info("Starting district coordinate processing from %s", kml_path)

    # P2-01 & P2-02: Read KML boundaries
    districts_gdf = read_district_kml(str(kml_path))

    # P2-04: Name normalization
    standardized_gdf = standardize_districts(districts_gdf)

    # P2-05: Centroid / Representative point calculation in UTM Zone 47N
    coords_gdf = calculate_centroids(standardized_gdf)

    # P2-07: Export coordinates
    export_coordinates(coords_gdf, str(output_path))

    # Optional cross-validation with green-space CSV
    if green_space_csv:
        gs_path = Path(green_space_csv)
        if gs_path.is_file():
            gs_df = pd.read_csv(gs_path)
            # Find district column in green space
            gs_col = "district" if "district" in gs_df.columns else gs_df.columns[0]
            gs_districts = set(gs_df[gs_col].dropna().unique())
            our_districts = set(coords_gdf["district"].unique())
            missing_in_gs = our_districts - gs_districts
            missing_in_ours = gs_districts - our_districts
            if missing_in_gs or missing_in_ours:
                logger.warning(
                    "District mismatch with green space CSV: missing in GS: %s, missing in ours: %s",
                    missing_in_gs,
                    missing_in_ours,
                )
            else:
                logger.info("All %d districts perfectly match green space CSV!", len(our_districts))

    logger.info("Spatial data processing completed successfully.")
    return coords_gdf
