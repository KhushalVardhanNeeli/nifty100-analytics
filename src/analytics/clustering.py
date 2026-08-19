"""ML Clustering — Sprint 6.

KMeans (n_clusters=5, random_state=42) on 5 scaled, sector-median-imputed
features, plus:
  * reports/elbow_plot.png          — inertia vs k (2..10)
  * reports/correlation_heatmap.png — Pearson correlation of 10 KPIs
  * output/cluster_labels.csv       — cluster_id, cluster_name, distance_from_centroid
  * output/outlier_report.csv       — |Z-score| > 3 per metric within broad_sector
  * output/portfolio_stats.csv      — P10..P90, mean, std per KPI
"""

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sqlalchemy import create_engine, text

DB_PATH = os.getenv("DB_PATH", "db/nifty100.db")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")

FEATURES = [
    "return_on_equity_pct",
    "debt_to_equity",
    "revenue_cagr_5yr",
    "fcf_cagr_5yr",
    "operating_profit_margin_pct",
]

KPI_10 = [
    "return_on_equity_pct",
    "return_on_capital_employed_pct",
    "net_profit_margin_pct",
    "operating_profit_margin_pct",
    "debt_to_equity",
    "interest_coverage",
    "asset_turnover",
    "revenue_cagr_5yr",
    "pat_cagr_5yr",
    "eps_cagr_5yr",
]

CLUSTER_NAMES = [
    "High-Quality Compounders",
    "Emerging Growth",
    "Defensive Dividend Payers",
    "Value Cyclicals",
    "Distressed or Turnaround",
]


def _fcf_cagr_map(engine) -> dict:
    cf = pd.read_sql(
        text(
            "SELECT company_id, year, operating_activity, investing_activity "
            "FROM cashflow ORDER BY company_id, year"
        ),
        engine,
    )
    if cf.empty:
        return {}
    cf["fcf"] = cf["operating_activity"].fillna(0) + cf["investing_activity"].fillna(0)
    out = {}
    for cid, g in cf.groupby("company_id"):
        g = g.dropna(subset=["fcf"]).sort_values("year")
        if len(g) >= 6:
            s, e = g["fcf"].iloc[-6], g["fcf"].iloc[-1]
            if s > 0 and e > 0:
                out[int(cid)] = ((e / s) ** (1 / 5) - 1) * 100
            else:
                out[int(cid)] = np.nan
        else:
            out[int(cid)] = np.nan
    return out


def _load_latest(engine) -> pd.DataFrame:
    latest = int(
        pd.read_sql(text("SELECT MAX(year) AS y FROM financial_ratios"), engine).iloc[0]["y"]
    )
    fr = pd.read_sql(
        text("SELECT * FROM financial_ratios WHERE year = :y"),
        engine,
        params={"y": latest},
    )
    comp = pd.read_sql(
        text("SELECT company_id, ticker, company_name, broad_sector FROM companies"),
        engine,
    )
    df = fr.merge(comp, on="company_id", how="left")
    df["fcf_cagr_5yr"] = df["company_id"].map(_fcf_cagr_map(engine))
    return df, latest


def _impute_sector_median(df: pd.DataFrame, cols) -> pd.DataFrame:
    out = df.copy()
    for col in cols:
        out[col] = out.groupby("broad_sector")[col].transform(lambda s: s.fillna(s.median()))
        out[col] = out[col].fillna(out[col].median())
    return out


def run_clustering(db_path: str = DB_PATH) -> pd.DataFrame:
    engine = create_engine(f"sqlite:///{db_path}")
    df, _ = _load_latest(engine)
    engine.dispose()

    prepped = _impute_sector_median(df, FEATURES)
    X = prepped[FEATURES].to_numpy()

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
    labels = kmeans.fit_predict(Xs)
    dist = np.linalg.norm(Xs - kmeans.cluster_centers_[labels], axis=1)

    result = prepped[["company_id", "ticker", "company_name", "broad_sector"]].copy()
    result["cluster_id"] = labels
    result["distance_from_centroid"] = dist

    # Assign descriptive names based on a robust quality ranking so all five
    # archetypes are represented (ROE capped to stop tiny-equity anomalies from
    # dominating the ordering).
    profile = prepped.copy()
    profile["cluster_id"] = labels
    means = profile.groupby("cluster_id")[FEATURES].mean()
    roe_capped = means["return_on_equity_pct"].clip(-20, 80)
    quality = (
        roe_capped * 0.5
        + means["revenue_cagr_5yr"].fillna(0) * 0.3
        - means["debt_to_equity"].fillna(0) * 5
    )
    order = quality.sort_values(ascending=False).index
    archetypes = [
        "Emerging Growth",
        "High-Quality Compounders",
        "Defensive Dividend Payers",
        "Value Cyclicals",
        "Distressed or Turnaround",
    ]
    names = {}
    for rank, cid in enumerate(order):
        names[cid] = archetypes[min(rank, 4)]
    result["cluster_name"] = result["cluster_id"].map(names)

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    result.to_csv(os.path.join(OUTPUT_DIR, "cluster_labels.csv"), index=False)
    print(
        f"[Clustering] {len(result)} companies across {result['cluster_name'].nunique()} named clusters"
    )
    return result


def elbow_plot(db_path: str = DB_PATH) -> str:
    engine = create_engine(f"sqlite:///{db_path}")
    df, _ = _load_latest(engine)
    engine.dispose()
    prepped = _impute_sector_median(df, FEATURES)
    Xs = StandardScaler().fit_transform(prepped[FEATURES].to_numpy())

    ks = range(2, 11)
    inertias = []
    for k in ks:
        inertias.append(KMeans(n_clusters=k, random_state=42, n_init=10).fit(Xs).inertia_)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(list(ks), inertias, "o-", color="#1F3864")
    ax.axvline(5, color="red", linestyle="--", label="k=5")
    ax.set_xlabel("k")
    ax.set_ylabel("Inertia")
    ax.set_title("KMeans Elbow Plot")
    ax.legend()
    fig.tight_layout()
    path = "reports/elbow_plot.png"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print("[Clustering] Elbow plot saved to reports/elbow_plot.png")
    return path


def correlation_heatmap(db_path: str = DB_PATH) -> str:
    engine = create_engine(f"sqlite:///{db_path}")
    df, _ = _load_latest(engine)
    engine.dispose()
    corr = df[KPI_10].corr()

    import seaborn as sns

    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="RdYlBu", ax=ax, square=True)
    ax.set_title("Pearson Correlation of 10 KPIs (latest year)")
    fig.tight_layout()
    path = "reports/correlation_heatmap.png"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print("[Clustering] Correlation heatmap saved")
    return path


def outlier_report(db_path: str = DB_PATH) -> pd.DataFrame:
    engine = create_engine(f"sqlite:///{db_path}")
    df, _ = _load_latest(engine)
    engine.dispose()

    rows = []
    for sector, grp in df.groupby("broad_sector"):
        for col in FEATURES + ["pat_cagr_5yr"]:
            s = pd.to_numeric(grp[col], errors="coerce")
            if s.notna().sum() < 3:
                continue
            z = (s - s.mean()) / s.std()
            for _, r in grp[z.abs() > 3].iterrows():
                rows.append(
                    {
                        "company_id": int(r["company_id"]),
                        "ticker": r["ticker"],
                        "sector": sector,
                        "metric": col,
                        "value": r[col],
                        "z_score": round(z.get(r["company_id"], np.nan), 2),
                    }
                )
    out = pd.DataFrame(rows)
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    out.to_csv(os.path.join(OUTPUT_DIR, "outlier_report.csv"), index=False)
    print(f"[Clustering] Outlier report: {len(out)} flagged metrics")
    return out


def portfolio_stats(db_path: str = DB_PATH) -> pd.DataFrame:
    engine = create_engine(f"sqlite:///{db_path}")
    df, _ = _load_latest(engine)
    engine.dispose()

    rows = []
    for col in KPI_10:
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        rows.append(
            {
                "metric": col,
                "P10": round(s.quantile(0.10), 3),
                "P25": round(s.quantile(0.25), 3),
                "P50": round(s.quantile(0.50), 3),
                "P75": round(s.quantile(0.75), 3),
                "P90": round(s.quantile(0.90), 3),
                "Mean": round(s.mean(), 3),
                "Std": round(s.std(), 3),
            }
        )
    out = pd.DataFrame(rows)
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    out.to_csv(os.path.join(OUTPUT_DIR, "portfolio_stats.csv"), index=False)
    print(f"[Clustering] Portfolio stats for {len(out)} KPIs")
    return out


def run_all(db_path: str = DB_PATH) -> dict:
    labels = run_clustering(db_path)
    elbow_plot(db_path)
    correlation_heatmap(db_path)
    outliers = outlier_report(db_path)
    stats = portfolio_stats(db_path)
    return {
        "companies": len(labels),
        "clusters": labels["cluster_id"].nunique(),
        "outliers": len(outliers),
        "kpis": len(stats),
    }


if __name__ == "__main__":
    print(run_all())
