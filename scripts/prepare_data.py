"""Clean the listings and re-implement the Tableau calculated fields.

Writes the listing, NIL and municipality tables to data/processed/.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

PRICE_CAP_METRICS = 2000  # price cap used by the Tableau metrics
M3 = "Municipality 3"
M3_NILS = [
    "BUENOS AIRES - VENEZIA",
    "CITTA' STUDI",
    "LAMBRATE",
    "PARCO FORLANINI - ORTICA",
    "PARCO LAMBRO - CIMIANO",
]


def load_listings() -> pd.DataFrame:
    df = pd.read_csv(RAW / "listings_milano_2025-09.csv.gz", low_memory=False)
    # prices are in EUR despite the "$" label
    df = df.rename(columns={"price in dollars per night": "price_eur", "ID": "id"})
    df = df.drop(columns=["price"])
    # fix a double-encoded NIL name
    df["neighbourhood_cleansed"] = df["neighbourhood_cleansed"].str.replace("CITTÃ€", "CITTA", regex=False)
    return df


def nil_to_municipality() -> pd.Series:
    """NIL to municipality lookup (88 NILs)."""
    dd = pd.read_csv(RAW / "driving_distances_by_nil.csv")
    return dd.set_index("NIL")["Municipality"]


def performance_tier(pi: float) -> str:
    if pi < 0.05:
        return "New / Unproven"
    if pi < 0.5:
        return "Solid"
    return "Star Performer"


def price_tier(p: float) -> str:
    if p < 100:
        return "< €100"
    if p < 150:
        return "€100-150"
    if p < 200:
        return "€150-200"
    return "> €200"


def add_derived_fields(df: pd.DataFrame) -> pd.DataFrame:
    muni = nil_to_municipality()
    df["municipality"] = df["neighbourhood_cleansed"].map(muni)

    pi = df["review_scores_rating"] * df["number_of_reviews_ltm"] / df["price_eur"]
    df["performance_index"] = pi.fillna(0.0)
    df["performance_tier"] = df["performance_index"].map(performance_tier)
    df["price_tier"] = df["price_eur"].map(price_tier)

    # revenue proxy: price x reviews per month x 12
    ok = (df["price_eur"] < PRICE_CAP_METRICS) & (df["reviews_per_month"] > 0)
    df["revenue_proxy_eur_year"] = np.where(ok, df["price_eur"] * df["reviews_per_month"] * 12, np.nan)
    df["price_eur_capped"] = df["price_eur"].where(df["price_eur"] < PRICE_CAP_METRICS)
    return df


def metric_table(df: pd.DataFrame, by: str) -> pd.DataFrame:
    """Dashboard metrics aggregated by `by`."""
    g = df.groupby(by)
    return pd.DataFrame(
        {
            "n_listings": g["id"].count(),
            "avg_rating_location": g["review_scores_location"].mean(),
            "reviews_per_month": g["reviews_per_month"].mean(),
            "avg_price_eur": g["price_eur_capped"].mean(),
            "median_price_eur": g["price_eur"].median(),
            "avg_revenue_eur_year": g["revenue_proxy_eur_year"].mean(),
            "share_entire_home": g["room_type"].apply(lambda s: (s == "Entire home/apt").mean()),
        }
    ).round(4)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = add_derived_fields(load_listings())
    unmapped = df["municipality"].isna().sum()
    print(f"listings: {len(df):,}  (unmapped to a municipality: {unmapped})")

    keep = [
        "id", "neighbourhood_cleansed", "municipality", "latitude", "longitude",
        "property_type", "room_type", "accommodates", "bedrooms", "bathrooms",
        "price_eur", "price_tier", "minimum_nights", "availability_365",
        "number_of_reviews", "number_of_reviews_ltm", "reviews_per_month",
        "review_scores_rating", "review_scores_location",
        "estimated_occupancy_l365d", "estimated_revenue_l365d",
        "host_total_listings_count", "host_is_superhost",
        "performance_index", "performance_tier", "revenue_proxy_eur_year", "tags",
    ]
    df[keep].to_csv(OUT / "listings_clean.csv", index=False)

    muni = metric_table(df, "municipality")
    muni.to_csv(OUT / "municipality_metrics.csv")

    nil = metric_table(df, "neighbourhood_cleansed")
    nil.index.name = "NIL"
    # population is joined on the NIL code
    geo = json.loads((RAW / "nil_milano.geojson").read_text())
    code_to_name = {f["properties"]["ID_NIL"]: f["properties"]["NIL"] for f in geo["features"]}
    pop = pd.read_csv(RAW / "population_by_nil_2011_2023.csv").dropna(subset=["NIL"])
    pop["NIL_name"] = pop["NIL"].astype(int).map(code_to_name)
    pop_nil = pop.pivot_table(index="NIL_name", columns="Anno", values="Totale", aggfunc="sum")
    nil = nil.join(pd.DataFrame({
        "population_2023": pop_nil[2023],
        "population_change_2011_2023_pct": (pop_nil[2023] / pop_nil[2011] - 1) * 100,
    }))
    nil = nil.join(pd.read_csv(RAW / "immobiliare_prices_by_nil.csv").set_index("NIL"))
    nil = nil.join(pd.read_csv(RAW / "driving_distances_by_nil.csv").set_index("NIL"))
    nil["listings_per_1000_residents"] = nil["n_listings"] / nil["population_2023"] * 1000
    nil.round(3).to_csv(OUT / "nil_metrics.csv")

    m3 = df[df["neighbourhood_cleansed"].isin(M3_NILS)]
    tiers = (
        m3.groupby(["neighbourhood_cleansed", "performance_tier"])["performance_index"]
        .agg(n_listings="count", avg_performance_index="mean")
        .round(4)
        .reset_index()
    )
    tiers.to_csv(OUT / "m3_performance_tiers.csv", index=False)

    print("\nMunicipality metrics:\n", muni.round(2).to_string())
    print("\nMunicipality 3 NILs:\n", nil.loc[M3_NILS, ["n_listings", "avg_price_eur", "median_price_eur",
          "avg_rating_location", "population_2023", "Sale_EUR_sqm", "listings_per_1000_residents"]].round(2).to_string())
    print("\nPerformance tiers (M3):\n", tiers.to_string(index=False))


if __name__ == "__main__":
    main()
