"""ML Clustering Module — Sprint 6. KMeans clustering, profiling, outlier detection, and PCA."""

import logging
import os
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ml.clustering")

DB_PATH = os.getenv("DB_PATH", "db/nifty100.db")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

FEATURE_COLS = [
    "roe",
    "roce",
    "roa",
    "net_profit_margin",
    "debt_to_equity",
    "asset_turnover",
    "fcf_yield",
    "current_ratio",
]


def _load_data(db_path: str) -> pd.DataFrame:
    """Load latest-year financial ratios joined with company info."""
    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        conn = sqlite3.connect(db_path)

    try:
        max_year = conn.execute(
            "SELECT MAX(year) FROM financial_ratios"
        ).fetchone()[0]
        if max_year is None:
            logger.error("financial_ratios table is empty")
            return pd.DataFrame()

        query = """
            SELECT fr.company_id, fr.year,
                   fr.roe, fr.roce, fr.roa, fr.net_profit_margin,
                   fr.debt_to_equity, fr.asset_turnover,
                   fr.fcf_yield, fr.current_ratio,
                   c.ticker, c.sector_name
            FROM financial_ratios fr
            JOIN companies c ON fr.company_id = c.company_id
            WHERE fr.year = ?
        """
        df = pd.read_sql_query(query, conn, params=(max_year,))
    finally:
        if conn:
            conn.close()

    if df.empty:
        logger.error("No data returned from query")
        return pd.DataFrame()

    logger.info(f"Loaded {len(df)} companies for year {max_year}")
    return df


def _impute_median(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """Fill missing feature values with per-column medians."""
    for col in features:
        if col not in df.columns:
            continue
        median_val = df[col].median()
        if pd.isna(median_val):
            logger.warning("Column %s has no non-null entries; filling with 0", col)
            median_val = 0.0
        missing = df[col].isna().sum()
        if missing:
            logger.info("Imputing %d missing values in %s (median=%.4f)", missing, col, median_val)
        df[col] = df[col].fillna(median_val)
    return df


def run_clustering(n_clusters: int = 8, db_path: str = DB_PATH) -> pd.DataFrame:
    """Load latest-year ratios, run KMeans clustering, return labeled DataFrame.

    Args:
        n_clusters: Number of KMeans clusters (default 8).
        db_path: Path to SQLite database.

    Returns:
        DataFrame with columns: company_id, ticker, sector, cluster, and all
        feature values (roe, roce, roa, net_profit_margin, debt_to_equity,
        asset_turnover, fcf_yield, current_ratio).
    """
    df = _load_data(db_path)
    if df.empty:
        return pd.DataFrame()

    features_available = [c for c in FEATURE_COLS if c in df.columns]
    if len(features_available) < 2:
        logger.error("Insufficient features available (%d)", len(features_available))
        return pd.DataFrame()

    df = _impute_median(df, features_available)

    X = df[features_available].values.astype(np.float64)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X_scaled)
    df["cluster"] = labels.astype(int)

    try:
        sil = silhouette_score(X_scaled, labels)
        logger.info("Silhouette score: %.4f", sil)
    except Exception:
        logger.warning("Could not compute silhouette score", exc_info=True)

    result_cols = ["company_id", "ticker", "sector_name", "cluster"] + features_available
    result = df[[c for c in result_cols if c in df.columns]].copy()
    result = result.rename(columns={"sector_name": "sector"})
    result["cluster"] = result["cluster"].astype(int)

    logger.info("Clustering complete: %d clusters for %d companies", n_clusters, len(result))
    return result


def profile_clusters(cluster_df: pd.DataFrame) -> pd.DataFrame:
    """Profile each cluster with mean feature values and defining characteristic.

    The defining characteristic of a cluster is the feature whose mean deviates
    most from the global mean (largest absolute difference).

    Args:
        cluster_df: DataFrame from run_clustering().

    Returns:
        DataFrame with columns: cluster, count, each feature mean,
        defining_feature, defining_deviation.
    """
    if cluster_df.empty:
        logger.warning("Empty cluster DataFrame — cannot profile")
        return pd.DataFrame()

    features = [c for c in FEATURE_COLS if c in cluster_df.columns]
    if not features:
        logger.warning("No feature columns found for profiling")
        return pd.DataFrame()

    global_means = cluster_df[features].mean()
    cluster_means = cluster_df.groupby("cluster")[features].mean()

    profiles = []
    for cluster_id in sorted(cluster_means.index):
        row = {
            "cluster": int(cluster_id),
            "count": int((cluster_df["cluster"] == cluster_id).sum()),
        }
        for f in features:
            row[f] = round(float(cluster_means.loc[cluster_id, f]), 4)

        deviations = {}
        for f in features:
            dev = abs(row[f] - global_means[f])
            deviations[f] = dev

        defining = max(deviations, key=deviations.get)
        row["defining_feature"] = defining
        row["defining_deviation"] = round(float(deviations[defining]), 4)
        profiles.append(row)

    profile_df = pd.DataFrame(profiles)
    logger.info("Profiled %d clusters", len(profile_df))
    return profile_df


def detect_outliers(db_path: str = DB_PATH) -> list[tuple]:
    """Detect companies with |z-score| > 3 on any numeric feature.

    Uses population standard deviation (ddof=0) for z-score calculation.

    Returns:
        List of (company_id, ticker, feature, z_score, value) tuples.
    """
    df = _load_data(db_path)
    if df.empty:
        return []

    features = [c for c in FEATURE_COLS if c in df.columns]
    df = _impute_median(df, features)

    outliers = []
    for col in features:
        col_data = df[col].dropna()
        if len(col_data) < 3:
            continue

        mean_val = float(col_data.mean())
        std_val = float(col_data.std(ddof=0))
        if std_val == 0:
            continue

        z_scores = (df[col] - mean_val) / std_val
        outlier_mask = z_scores.abs() > 3

        for idx in df.index[outlier_mask]:
            outliers.append((
                int(df.loc[idx, "company_id"]),
                df.loc[idx, "ticker"],
                col,
                round(float(z_scores.loc[idx]), 4),
                round(float(df.loc[idx, col]), 4),
            ))

    logger.info("Detected %d outlier instances (|z| > 3)", len(outliers))
    return outliers


def pca_data(db_path: str = DB_PATH) -> pd.DataFrame:
    """Run PCA with 2 components and return data for plotting.

    Returns:
        DataFrame with columns: pc1, pc2, ticker, sector.
    """
    df = _load_data(db_path)
    if df.empty:
        return pd.DataFrame()

    features = [c for c in FEATURE_COLS if c in df.columns]
    df = _impute_median(df, features)

    X = df[features].values.astype(np.float64)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    pca = PCA(n_components=2, random_state=42)
    components = pca.fit_transform(X_scaled)

    result = pd.DataFrame({
        "pc1": components[:, 0],
        "pc2": components[:, 1],
        "ticker": df["ticker"].values,
        "sector": df["sector_name"].values,
    })

    evr = pca.explained_variance_ratio_
    logger.info("PCA complete — PC1: %.1f%%, PC2: %.1f%% variance", evr[0] * 100, evr[1] * 100)
    return result


def export_clusters(
    cluster_df: pd.DataFrame,
    profile_df: pd.DataFrame,
    outliers: list[tuple],
    output_dir: str = OUTPUT_DIR,
) -> None:
    """Export cluster assignments, cluster profiles, and outlier list to CSV.

    Args:
        cluster_df: DataFrame from run_clustering().
        profile_df: DataFrame from profile_clusters().
        outliers: List from detect_outliers().
        output_dir: Directory for output files (default 'output/').
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if not cluster_df.empty:
        path = os.path.join(output_dir, "cluster_assignments.csv")
        cluster_df.to_csv(path, index=False)
        logger.info("Exported cluster assignments to %s", path)

    if not profile_df.empty:
        path = os.path.join(output_dir, "cluster_profiles.csv")
        profile_df.to_csv(path, index=False)
        logger.info("Exported cluster profiles to %s", path)

    if outliers:
        path = os.path.join(output_dir, "outliers.csv")
        out_df = pd.DataFrame(outliers, columns=["company_id", "ticker", "feature", "z_score", "value"])
        out_df.to_csv(path, index=False)
        logger.info("Exported outliers to %s", path)


def run_analysis(n_clusters: int = 8, db_path: str = DB_PATH, output_dir: str = OUTPUT_DIR) -> dict:
    """Run full clustering pipeline and return summary dictionary.

    Args:
        n_clusters: Number of clusters for KMeans.
        db_path: Path to SQLite database.
        output_dir: Directory for output CSV files.

    Returns:
        Dictionary with keys: companies, clusters, outliers, cluster_sizes.
    """
    logger.info("=" * 60)
    logger.info("ML Clustering Analysis — Starting")
    logger.info("=" * 60)

    cluster_df = run_clustering(n_clusters=n_clusters, db_path=db_path)
    if cluster_df.empty:
        logger.error("Clustering failed — check database and feature availability")
        return {}

    profile_df = profile_clusters(cluster_df)
    outliers = detect_outliers(db_path=db_path)
    _pca_data = pca_data(db_path=db_path)
    export_clusters(cluster_df, profile_df, outliers, output_dir=output_dir)

    cluster_counts = cluster_df["cluster"].value_counts().sort_index()

    summary = {
        "companies": len(cluster_df),
        "clusters": n_clusters,
        "outliers": len(outliers),
        "cluster_sizes": cluster_counts.to_dict(),
    }

    logger.info("=" * 60)
    logger.info("Cluster Analysis Summary")
    logger.info("  Companies analyzed : %d", summary["companies"])
    logger.info("  Clusters           : %d", summary["clusters"])
    logger.info("  Outliers detected  : %d", summary["outliers"])
    logger.info("  Cluster sizes:")
    for cid in sorted(cluster_counts.index):
        logger.info("    Cluster %d: %d companies", cid, cluster_counts[cid])
    logger.info("")

    if not profile_df.empty:
        logger.info("  Defining characteristics:")
        for _, row in profile_df.iterrows():
            logger.info(
                "    Cluster %d (%d cos): %s",
                int(row["cluster"]),
                int(row["count"]),
                row["defining_feature"],
            )

    logger.info("=" * 60)
    return summary


if __name__ == "__main__":
    try:
        run_analysis()
    except Exception:
        logger.exception("Unhandled exception in clustering pipeline")
        raise SystemExit(1)
