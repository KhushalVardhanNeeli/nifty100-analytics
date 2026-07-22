import re
import math

SECTOR_NAME_MAP = {
    "it": "Information Technology",
    "information technology": "Information Technology",
    "technology": "Information Technology",
    "fmcg": "Consumer Goods",
    "consumer goods": "Consumer Goods",
    "bfsi": "Financial Services",
    "financial services": "Financial Services",
    "banking": "Financial Services",
    "auto": "Automotive",
    "automotive": "Automotive",
    "automobile": "Automotive",
    "pharma": "Pharmaceuticals",
    "pharmaceuticals": "Pharmaceuticals",
    "pharmaceutical": "Pharmaceuticals",
    "healthcare": "Pharmaceuticals",
    "psu": "Public Sector",
    "public sector": "Public Sector",
    "oil & gas": "Oil and Gas",
    "oil and gas": "Oil and Gas",
    "power": "Energy",
    "energy": "Energy",
    "telecom": "Telecommunications",
    "telecommunications": "Telecommunications",
    "telecommunication": "Telecommunications",
    "metals": "Metals and Mining",
    "metals and mining": "Metals and Mining",
    "mining": "Metals and Mining",
    "cement": "Cement",
    "construction": "Construction",
    "infrastructure": "Infrastructure",
    "realty": "Real Estate",
    "real estate": "Real Estate",
    "media": "Media and Entertainment",
    "media and entertainment": "Media and Entertainment",
    "chemicals": "Chemicals",
    "fertilisers": "Fertilisers",
    "textiles": "Textiles",
}


def normalize_ticker(value):
    if value is None:
        return None
    try:
        if (isinstance(value, float) and math.isnan(value)) or value != value:
            return None
    except (ValueError, TypeError):
        pass
    if isinstance(value, float) and math.isnan(value):
        return None
    s = str(value).strip().upper()
    s = s.lstrip(".").rstrip(".")
    if not s:
        return None
    return s


def normalize_year(value):
    if value is None:
        return None
    try:
        if (isinstance(value, float) and math.isnan(value)) or value != value:
            return None
    except (ValueError, TypeError):
        pass
    if isinstance(value, (int, float)):
        if math.isnan(value):
            return None
        year = int(value)
        return year if 1900 <= year <= 2100 else None
    if isinstance(value, str):
        match = re.search(r"(19[0-9]{2}|20[0-9]{2}|2100)", value)
        if match:
            year = int(match.group(0))
            return year if 1900 <= year <= 2100 else None
        try:
            year = int(value.strip())
            return year if 1900 <= year <= 2100 else None
        except (ValueError, TypeError):
            return None
    return None


def normalize_numeric(value):
    if value is None:
        return None
    try:
        if (isinstance(value, float) and math.isnan(value)) or value != value:
            return None
    except (ValueError, TypeError):
        pass
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        s = value.strip()
        if s in ("", "-", "--", "—", "–", "NA", "N/A", "na", "n/a", "null", "NULL", "Nil", "nil"):
            return 0.0
        if s.endswith("%"):
            s = s[:-1].strip()
            try:
                return float(s.replace(",", "")) / 100.0
            except (ValueError, TypeError):
                return None
        try:
            return float(s.replace(",", ""))
        except (ValueError, TypeError):
            return None
    if isinstance(value, (int, float)):
        if math.isnan(value):
            return None
        return float(value)
    return None


def normalize_sector_name(value):
    if value is None:
        return None
    try:
        if (isinstance(value, float) and math.isnan(value)) or value != value:
            return None
    except (ValueError, TypeError):
        pass
    if isinstance(value, float) and math.isnan(value):
        return None
    s = str(value).strip()
    if not s:
        return None
    key = s.lower()
    if key in SECTOR_NAME_MAP:
        return SECTOR_NAME_MAP[key]
    return s.title()
