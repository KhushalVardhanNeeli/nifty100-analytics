"""NLP text analysis module for Nifty100 analyst reports.

Keyword extraction, sentiment analysis, readability scoring, company summary
generation, and export — using only sqlite3 and the Python standard library.
"""

import logging
import os
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POSITIVE_WORDS: List[str] = [
    "growth",
    "profit",
    "strong",
    "increase",
    "positive",
    "improving",
    "healthy",
    "good",
    "high",
    "leading",
    "delivered",
    "maintaining",
    "debt free",
    "expected to",
    "good quarter",
]

NEGATIVE_WORDS: List[str] = [
    "decline",
    "loss",
    "weak",
    "decrease",
    "negative",
    "deteriorating",
    "poor",
    "low",
    "risk",
    "concern",
    "trading at",
    "contingent",
    "low interest coverage",
]

# Compiled regex patterns keyed by financial keyword category.
FINANCIAL_PATTERNS: Dict[str, re.Pattern] = {
    "growth": re.compile(
        r"\b(?:growth|growing|expansion|cagr|revenue\s*growth|sales\s*growth|"
        r"earnings\s*growth|profit\s*growth|increase|increased|delivered)\b",
        re.IGNORECASE,
    ),
    "profitability": re.compile(
        r"\b(?:profit\w*|eps|net\s*income|net\s*profit|operating\s*profit|"
        r"earnings|ro[ce]e?|roic|prosper)\b",
        re.IGNORECASE,
    ),
    "debt": re.compile(
        r"\b(?:debt[ -]?(?:free|to[ -]?equity)?|borrowing|leverage|loan|"
        r"indebtedness|interest\s*coverage|net\s*debt|debt\s*free)\b",
        re.IGNORECASE,
    ),
    "valuation": re.compile(
        r"\b(?:valu\w+|pe\s*ratio|p/?[eb]|book\s*value|ev[ /]?ebitda|"
        r"price\s*to|trading\s*at|discount|premium|overvalued|undervalued)\b",
        re.IGNORECASE,
    ),
    "margins": re.compile(
        r"\b(?:margin|opm|npm|ebitda\s*margin|operating\s*margin|"
        r"net\s*margin|profit\s*margin)\b",
        re.IGNORECASE,
    ),
    "dividends": re.compile(
        r"\b(?:dividend\w*|yield|payout|dps|dividend\s*payout|dividend\s*yield)\b",
        re.IGNORECASE,
    ),
    "liquidity": re.compile(
        r"\b(?:liquidity|cash\s*flow|free\s*cash|fcf|operating\s*cash|"
        r"cash\s*position|cash\s*reserve|working\s*capital)\b",
        re.IGNORECASE,
    ),
    "returns": re.compile(
        r"\b(?:ro[ce]e?|roic|return\s*on|roa|roce)\b",
        re.IGNORECASE,
    ),
}

DEFAULT_DB_PATH = os.path.join("db", "nifty100.db")
DEFAULT_OUTPUT_DIR = os.path.join("output", "nlp_summaries")


# ---------------------------------------------------------------------------
# Database helper
# ---------------------------------------------------------------------------

def _get_conn(db_path: str) -> sqlite3.Connection:
    """Open a sqlite3 connection with Row factory for dict-like access."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _maybe_get_column(conn: sqlite3.Connection, column: str, table: str) -> bool:
    """Return True if *column* exists in *table*, else False."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


# ---------------------------------------------------------------------------
# 1. Keyword extraction
# ---------------------------------------------------------------------------

def extract_keywords(text: str) -> Dict[str, List[str]]:
    """Extract financial keywords from *text* grouped by category.

    Parameters
    ----------
    text : str
        Free-form review / analyst text.

    Returns
    -------
    dict
        Keys are category names (e.g. "growth", "profitability"); values are
        lists of matched substrings (de-duplicated, lower-cased).
    """
    if not text or not isinstance(text, str):
        return {}

    result: Dict[str, List[str]] = {}
    for category, pattern in FINANCIAL_PATTERNS.items():
        matches: List[str] = pattern.findall(text)
        unique = list(dict.fromkeys(m.lower() for m in matches))
        if unique:
            result[category] = unique
    return result


def extract_company_keywords(
    company_id: int, db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Dict[str, List[str]]]:
    """Extract keywords from all pros and cons rows for one company.

    Parameters
    ----------
    company_id : int
        Target company.
    db_path : str
        Path to the SQLite database.

    Returns
    -------
    dict
        ``{"pros": {...}, "cons": {...}}`` where each inner dict is the output
        of :func:`extract_keywords`.
    """
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT pros, cons FROM prosandcons WHERE company_id = ?",
            [company_id],
        ).fetchall()

        combined_pros = " ".join(r["pros"] or "" for r in rows)
        combined_cons = " ".join(r["cons"] or "" for r in rows)

        return {
            "pros": extract_keywords(combined_pros),
            "cons": extract_keywords(combined_cons),
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 2. Sentiment analysis
# ---------------------------------------------------------------------------

def _count_matches(text: str, word_list: List[str]) -> int:
    """Count case-insensitive occurrences of phrases from *word_list* in *text*.

    Each phrase in *word_list* is treated as a fixed-string substring search.
    Longer phrases are matched first to avoid double-counting (e.g. "debt free"
    before "debt").
    """
    if not text or not isinstance(text, str):
        return 0
    lower = text.lower()
    count = 0
    # Order by length descending so multi-word phrases take priority.
    for phrase in sorted(word_list, key=len, reverse=True):
        count += lower.count(phrase.lower())
    return count


def analyze_sentiment(text: str) -> Dict[str, Any]:
    """Score *text* using simple keyword-based sentiment analysis.

    Parameters
    ----------
    text : str
        Input text (e.g. a single pro or con sentence).

    Returns
    -------
    dict
        Keys: ``positive_count``, ``negative_count``, ``sentiment_score``
        (net positive), ``label`` (positive/neutral/negative).
    """
    if not text or not isinstance(text, str):
        return {
            "positive_count": 0,
            "negative_count": 0,
            "sentiment_score": 0,
            "label": "neutral",
        }

    pos = _count_matches(text, POSITIVE_WORDS)
    neg = _count_matches(text, NEGATIVE_WORDS)
    score = pos - neg

    if score > 0:
        label = "positive"
    elif score < 0:
        label = "negative"
    else:
        label = "neutral"

    return {
        "positive_count": pos,
        "negative_count": neg,
        "sentiment_score": score,
        "label": label,
    }


def analyze_company_sentiment(
    company_id: int, db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """Run sentiment analysis on all pros and cons for a company.

    Parameters
    ----------
    company_id : int
        Target company.
    db_path : str
        Path to the SQLite database.

    Returns
    -------
    dict
        Keys: ``pros_sentiments`` (list of individual pro results),
        ``cons_sentiments`` (list of individual con results),
        ``overall_score``, ``overall_label``.
    """
    conn = _get_conn(db_path)
    try:
        rows = conn.execute(
            "SELECT pros, cons FROM prosandcons WHERE company_id = ?",
            [company_id],
        ).fetchall()

        pros_results: List[Dict[str, Any]] = []
        cons_results: List[Dict[str, Any]] = []
        total_pos = 0
        total_neg = 0

        for r in rows:
            if r["pros"]:
                sr = analyze_sentiment(r["pros"])
                sr["text"] = r["pros"]
                pros_results.append(sr)
                total_pos += sr["positive_count"]
                total_neg += sr["negative_count"]
            if r["cons"]:
                sr = analyze_sentiment(r["cons"])
                sr["text"] = r["cons"]
                cons_results.append(sr)
                # Cons text is already negative by nature, count matches as-is
                total_pos += sr["positive_count"]
                total_neg += sr["negative_count"]

        overall_score = total_pos - total_neg
        if overall_score > 0:
            overall_label = "positive"
        elif overall_score < 0:
            overall_label = "negative"
        else:
            overall_label = "neutral"

        return {
            "pros_sentiments": pros_results,
            "cons_sentiments": cons_results,
            "total_positive_count": total_pos,
            "total_negative_count": total_neg,
            "overall_score": overall_score,
            "overall_label": overall_label,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 3. Readability
# ---------------------------------------------------------------------------

def compute_readability(text: str) -> Dict[str, Any]:
    """Compute simple readability metrics for *text*.

    Parameters
    ----------
    text : str
        Arbitrary text (pros, cons, description, etc.).

    Returns
    -------
    dict
        ``sentence_count``, ``word_count``, ``char_count``,
        ``avg_sentence_length``, ``avg_word_length``,
        ``readability_label`` (simple/standard/complex).
    """
    if not text or not isinstance(text, str):
        return {
            "sentence_count": 0,
            "word_count": 0,
            "char_count": 0,
            "avg_sentence_length": 0.0,
            "avg_word_length": 0.0,
            "readability_label": "n/a",
        }

    # Split into sentences on ., !, ? followed by whitespace or end-of-string
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        sentences = [text.strip()]

    word_count = 0
    char_count = len(text)
    for s in sentences:
        words = s.split()
        word_count += len(words)

    sentence_count = len(sentences)
    avg_sentence_length = word_count / sentence_count if sentence_count else 0.0
    avg_word_length = char_count / word_count if word_count else 0.0

    if avg_sentence_length <= 12:
        readability_label = "simple"
    elif avg_sentence_length <= 20:
        readability_label = "standard"
    else:
        readability_label = "complex"

    return {
        "sentence_count": sentence_count,
        "word_count": word_count,
        "char_count": char_count,
        "avg_sentence_length": round(avg_sentence_length, 1),
        "avg_word_length": round(avg_word_length, 1),
        "readability_label": readability_label,
    }


# ---------------------------------------------------------------------------
# 4. Company summary generation
# ---------------------------------------------------------------------------

def _get_about_company(conn: sqlite3.Connection, company_id: int) -> Optional[str]:
    """Attempt to fetch an about-company description from the database.

    Checks the ``companies`` table for an ``about_company`` column first,
    then falls back to an ``analysis`` row with ``metric_name = 'about_company'``.
    Returns ``None`` when nothing is found.
    """
    if _maybe_get_column(conn, "about_company", "companies"):
        row = conn.execute(
            "SELECT about_company FROM companies WHERE company_id = ?",
            [company_id],
        ).fetchone()
        if row and row["about_company"]:
            return str(row["about_company"])

    try:
        row = conn.execute(
            "SELECT description FROM analysis "
            "WHERE company_id = ? AND metric_name = 'about_company'",
            [company_id],
        ).fetchone()
    except sqlite3.OperationalError:
        row = None

    if row and row["description"]:
        return str(row["description"])

    return None


def _format_crore(value: Optional[float]) -> str:
    """Format a crore-denominated number for display."""
    if value is None:
        return "N/A"
    abs_val = abs(value)
    if abs_val >= 1_00_000:
        return f"Rs.{value / 1_00_000:,.1f} Lakh Cr."
    elif abs_val >= 10_000:
        return f"Rs.{value / 1_000:,.0f}K Cr."
    elif abs_val >= 1_000:
        return f"Rs.{value / 1_000:,.1f}K Cr."
    else:
        return f"Rs.{value:,.0f} Cr."


def _ratio_str(value: Optional[float], fmt: str = ".2f") -> str:
    """Return ratio as formatted string or 'N/A'."""
    if value is None:
        return "N/A"
    return f"{value:{fmt}}"


def generate_company_summary(
    company_id: int, db_path: str = DEFAULT_DB_PATH
) -> str:
    """Build a human-readable NLP summary for a single company.

    Combines company metadata, top positive points, top concerns, key
    financial ratios, and an about-company blurb (when available).

    Parameters
    ----------
    company_id : int
        Target company.
    db_path : str
        Path to the SQLite database.

    Returns
    -------
    str
        Multi-line text summary.
    """
    conn = _get_conn(db_path)
    try:
        # ── Company metadata ───────────────────────────────────────────
        company = conn.execute(
            "SELECT ticker, company_name, sector_name, market_cap "
            "FROM companies WHERE company_id = ?",
            [company_id],
        ).fetchone()

        if not company:
            logger.warning("Company %s not found", company_id)
            return f"[ERROR] Company ID {company_id} not found in database."

        ticker = company["ticker"]
        name = company["company_name"]
        sector = company["sector_name"] or "Unknown"
        mcap = company["market_cap"]

        # ── Pros and cons ─────────────────────────────────────────────
        pros_rows = conn.execute(
            "SELECT pros, cons FROM prosandcons WHERE company_id = ?",
            [company_id],
        ).fetchall()

        all_pros: List[str] = [r["pros"] for r in pros_rows if r["pros"]]
        all_cons: List[str] = [r["cons"] for r in pros_rows if r["cons"]]

        # ── Key ratios (latest year) ──────────────────────────────────
        ratios = conn.execute(
            "SELECT roe, debt_to_equity, net_profit_margin, roce, "
            "fcf_yield, interest_coverage "
            "FROM financial_ratios "
            "WHERE company_id = ? "
            "ORDER BY year DESC LIMIT 1",
            [company_id],
        ).fetchone()

        roe = ratios["roe"] if ratios else None
        de = ratios["debt_to_equity"] if ratios else None
        npm = ratios["net_profit_margin"] if ratios else None
        roce_val = ratios["roce"] if ratios else None
        fcf_y = ratios["fcf_yield"] if ratios else None
        icr = ratios["interest_coverage"] if ratios else None

        # ── Latest year ───────────────────────────────────────────────
        yr_row = conn.execute(
            "SELECT MAX(year) as yr FROM financial_ratios WHERE company_id = ?",
            [company_id],
        ).fetchone()
        latest_year = yr_row["yr"] if yr_row else None

        # ── About company ─────────────────────────────────────────────
        about = _get_about_company(conn, company_id)

        # ── Build summary ─────────────────────────────────────────────
        lines: List[str] = []
        lines.append("=" * 72)
        lines.append(f"  NLP COMPANY SUMMARY: {ticker} — {name}")
        lines.append("=" * 72)
        lines.append(f"  Sector          : {sector}")
        lines.append(f"  Market Cap      : {_format_crore(mcap)}")
        lines.append(f"  Latest Ratios   : {f'FY{latest_year}' if latest_year else 'N/A'}")
        lines.append(f"  ROE             : {_ratio_str(roe)}%")
        lines.append(f"  ROCE            : {_ratio_str(roce_val)}%")
        lines.append(f"  Net Profit Marg.: {_ratio_str(npm)}%")
        lines.append(f"  Debt / Equity   : {_ratio_str(de)}")
        lines.append(f"  Interest Cover  : {_ratio_str(icr, '.1f')}")
        lines.append(f"  FCF Yield       : {_ratio_str(fcf_y)}%")
        lines.append("-" * 72)

        # ── Top positive points ───────────────────────────────────────
        lines.append(f"  POSITIVE POINTS ({len(all_pros)} items)")
        lines.append("-" * 72)
        if all_pros:
            for i, pro in enumerate(all_pros[:10], 1):
                lines.append(f"   {i:2d}. {pro}")
        else:
            lines.append("   (no pros data available)")

        # ── Top concerns ──────────────────────────────────────────────
        lines.append("")
        lines.append("-" * 72)
        lines.append(f"  CONCERNS / RISKS ({len(all_cons)} items)")
        lines.append("-" * 72)
        if all_cons:
            for i, con in enumerate(all_cons[:10], 1):
                lines.append(f"   {i:2d}. {con}")
        else:
            lines.append("   (no cons data available)")

        # ── About company ─────────────────────────────────────────────
        if about:
            lines.append("")
            lines.append("-" * 72)
            lines.append("  ABOUT THE COMPANY")
            lines.append("-" * 72)
            lines.append(f"  {about}")

        lines.append("")
        lines.append("=" * 72)

        return "\n".join(lines)

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 5. Export
# ---------------------------------------------------------------------------

def export_nlp_summary(
    company_id: int,
    db_path: str = DEFAULT_DB_PATH,
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> str:
    """Generate an NLP summary for *company_id* and write it to a text file.

    Parameters
    ----------
    company_id : int
        Target company.
    db_path : str
        Path to the SQLite database.
    output_dir : str
        Directory where the summary file is written.

    Returns
    -------
    str
        Absolute path to the generated text file.
    """
    conn = _get_conn(db_path)
    try:
        info = conn.execute(
            "SELECT ticker FROM companies WHERE company_id = ?",
            [company_id],
        ).fetchone()
    finally:
        conn.close()

    ticker = info["ticker"] if info else f"company_{company_id}"

    summary = generate_company_summary(company_id, db_path)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    filename = f"{ticker}_nlp_summary.txt"
    file_path = out_path / filename

    file_path.write_text(summary, encoding="utf-8")

    logger.info("NLP summary exported to %s", file_path)
    return str(file_path.resolve())
