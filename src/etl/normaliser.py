"""Data normalisation helpers for the Nifty 100 ETL pipeline.

Handles ticker, year, numeric and sector-name normalisation so that raw
Excel/CSV values are cleaned into consistent, typed representations before
they are written to SQLite.
"""

import math
import re

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


def _is_nan(value):
    """Return True if value is NaN (float or other)."""
    try:
        return bool(value != value)
    except (ValueError, TypeError):
        return False


def normalize_ticker(value):
    """Normalise a ticker symbol: strip, uppercase, remove stray dots."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if _is_nan(value):
        return None
    if isinstance(value, bool):
        return None
    s = str(value).strip().upper()
    s = s.lstrip(".").rstrip(".")
    if not s:
        return None
    return s


def normalize_year(value):
    """Normalise a year value into an int in [1900, 2100], or None.

    Handles all known source variants:
      - "Dec 2012", "Mar 2014", "Year ending March 2021"
      - "Mar-13", "Mar-24" (2-digit fiscal year -> 20XX)
      - "FY2020", "FY 2020", "FY20"
      - 2020, 2020.0, "2020", "2020-21"
      - "TTM", None, NaN, "" -> None
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if _is_nan(value):
        return None

    if isinstance(value, (int, float)):
        year = int(value)
        return year if 1900 <= year <= 2100 else None

    s = str(value).strip()
    if not s:
        return None

    # Non-year markers used in the source data.
    if s.upper() in ("TTM", "NA", "N/A", "NAN", "NULL", "NONE", "-", "--", "—", "–"):
        return None

    # Full 4-digit year anywhere in the string.
    m = re.search(r"(19[0-9]{2}|20[0-9]{2}|2100)", s)
    if m:
        year = int(m.group(0))
        if 1900 <= year <= 2100:
            return year

    # 2-digit fiscal year with a month prefix, e.g. "Mar-13", "Mar 24".
    m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[-/\s]+(\d{2})\b", s, re.IGNORECASE)
    if m:
        yy = int(m.group(2))
        year = 2000 + yy if yy < 70 else 1900 + yy
        if 1900 <= year <= 2100:
            return year

    # "FY" prefix with 2-digit year, e.g. "FY20".
    m = re.search(r"^[Ff][Yy]\s*(\d{2})$", s)
    if m:
        yy = int(m.group(1))
        year = 2000 + yy if yy < 70 else 1900 + yy
        return year

    # Bare 2-digit year, e.g. "20".
    m = re.search(r"^(\d{2})$", s)
    if m:
        yy = int(m.group(1))
        year = 2000 + yy if yy < 70 else 1900 + yy
        return year

    return None


def normalize_numeric(value):
    """Normalise a numeric value to a float, treating common blanks as 0.0."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if _is_nan(value):
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
    """Normalise a sector name using SECTOR_NAME_MAP, falling back to title case."""
    if value is None:
        return None
    if _is_nan(value):
        return None
    s = str(value).strip()
    if not s:
        return None
    key = s.lower()
    if key in SECTOR_NAME_MAP:
        return SECTOR_NAME_MAP[key]
    return s.title()
