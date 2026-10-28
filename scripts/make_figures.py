"""Static versions of the Tableau views (run prepare_data.py first)."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import squarify
from matplotlib.collections import PatchCollection
from matplotlib.patches import Polygon

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
FIG = ROOT / "reports" / "figures"

# palette: fixed categorical order, single-hue blue ramp
SURFACE = "#fcfcfb"
INK, INK_2, MUTED, GRID = "#0b0b0b", "#52514e", "#9a998f", "#e4e3df"
CAT = ["#2a78d6", "#eb6834", "#1baf7a"]
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
HIGHLIGHT, CONTEXT = "#2a78d6", "#c9c8c1"

M3_NILS = ["BUENOS AIRES - VENEZIA", "CITTA' STUDI", "LAMBRATE",
           "PARCO FORLANINI - ORTICA", "PARCO LAMBRO - CIMIANO"]
TOP3 = ["BUENOS AIRES - VENEZIA", "CITTA' STUDI", "PARCO LAMBRO - CIMIANO"]

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
    "axes.titlecolor": INK, "axes.titlesize": 11, "axes.titlelocation": "left",
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 9,
    "axes.grid": False, "grid.color": GRID, "grid.linewidth": 0.6,
})


def nice(nil: str) -> str:
    return nil.title().replace("'", "’").replace(" - ", "-")


def save(fig, name: str) -> None:
    fig.savefig(FIG / name, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


def load_polygons() -> dict[str, np.ndarray]:
    geo = json.loads((RAW / "nil_milano.geojson").read_text())
    return {f["properties"]["NIL"]: np.array(f["geometry"]["coordinates"][0]) for f in geo["features"]}


def draw_nils(ax, polys, colors: dict[str, str], edge="#fcfcfb", lw=0.4) -> None:
    patches, fc = [], []
    for nil, xy in polys.items():
        patches.append(Polygon(xy, closed=True))
        fc.append(colors.get(nil, "#efeeea"))
    ax.add_collection(PatchCollection(patches, facecolor=fc, edgecolor=edge, linewidth=lw))
    ax.set_aspect(1 / np.cos(np.radians(45.47)))
    ax.autoscale_view()
    ax.axis("off")


def fig01_map(listings, muni_metrics, polys, nil_muni) -> None:
    vals = muni_metrics["avg_rating_location"]
    lo, hi = vals.min(), vals.max()
    def color(v):
        i = int(round((v - lo) / (hi - lo) * (len(BLUE_RAMP) - 1)))
        return BLUE_RAMP[i]
    colors = {nil: color(vals[m]) for nil, m in nil_muni.items() if m in vals}
    fig, ax = plt.subplots(figsize=(7.5, 6.5))
    draw_nils(ax, polys, colors)
    m3 = [polys[n] for n in M3_NILS]
    ax.add_collection(PatchCollection([Polygon(p) for p in m3], facecolor="none",
                                      edgecolor=INK, linewidth=1.6))
    # municipality labels at listing centroids
    cent = listings.groupby("municipality")[["longitude", "latitude"]].median()
    for m, (x, y) in cent.iterrows():
        ax.text(x, y, f"M{m.split()[-1]}\n{vals[m]:.2f}", ha="center", va="center", fontsize=8,
                color=INK if vals[m] < lo + 0.6 * (hi - lo) else "#ffffff", fontweight="bold")
    sm = plt.cm.ScalarMappable(cmap=plt.matplotlib.colors.ListedColormap(BLUE_RAMP),
                               norm=plt.Normalize(lo, hi))
    cb = fig.colorbar(sm, ax=ax, shrink=0.55, pad=0.01)
    cb.set_label("Avg location review score (1 to 5)")
    cb.outline.set_visible(False)
    ax.set_title("Average location rating by municipality (Municipality 3 outlined)")
    save(fig, "fig01_municipality_map.png")


def fig02_metrics(muni) -> None:
    metrics = [("avg_rating_location", "Avg location rating", "{:.2f}"),
               ("reviews_per_month", "Reviews per month", "{:.2f}"),
               ("avg_price_eur", "Avg price per night (€)", "{:.0f}"),
               ("avg_revenue_eur_year", "Avg revenue proxy (€/year)", "{:,.0f}")]
    fig, axes = plt.subplots(2, 2, figsize=(10, 6.5))
    for ax, (col, title, fmt) in zip(axes.flat, metrics):
        s = muni[col].sort_values()
        labels = [f"M{i.split()[-1]}" for i in s.index]
        colors = [HIGHLIGHT if i == "Municipality 3" else CONTEXT for i in s.index]
        ax.barh(labels, s.values, color=colors, height=0.68)
        lo = s.min() * 0.97 if col == "avg_rating_location" else 0
        ax.set_xlim(lo, 5.0 if col == "avg_rating_location" else s.max() * 1.12)
        for y, v in enumerate(s.values):
            ax.text(v, y, " " + fmt.format(v), va="center", fontsize=7.5, color=INK_2)
        ax.set_title(title)
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.xaxis.grid(True)
        ax.set_axisbelow(True)
    fig.suptitle("Dashboard metrics by municipality (Municipality 3 in blue)", x=0.01, ha="left",
                 fontsize=12, color=INK)
    fig.tight_layout()
    save(fig, "fig02_municipality_metrics.png")


def fig03_context(nil) -> None:
    pop = pd.read_csv(RAW / "population_by_nil_2011_2023.csv").dropna(subset=["NIL"])
    geo = json.loads((RAW / "nil_milano.geojson").read_text())
    code_to_name = {f["properties"]["ID_NIL"]: f["properties"]["NIL"] for f in geo["features"]}
    pop["NIL_name"] = pop["NIL"].astype(int).map(code_to_name)
    d = nil.loc[M3_NILS]
    names = [nice(n) for n in M3_NILS]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    axes[1].sharey(axes[0])
    for ax, col, title, fmt in [
        (axes[0], "listings_per_1000_residents", "Airbnb listings per 1,000 residents", "{:.1f}"),
        (axes[1], "Sale_EUR_sqm", "Residential sale price (€/m², Immobiliare.it)", "{:,.0f}"),
    ]:
        ax.barh(names[::-1], d[col].values[::-1], color=HIGHLIGHT, height=0.62)
        for y, v in enumerate(d[col].values[::-1]):
            ax.text(v, y, " " + fmt.format(v), va="center", fontsize=8, color=INK_2)
        ax.set_xlim(0, d[col].max() * 1.22)
        ax.set_title(title)
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
    ax = axes[2]
    p = pop[pop.NIL_name.isin(M3_NILS)].pivot_table(index="NIL_name", columns="Anno", values="Totale")
    chg = ((p[2023] / p[2011] - 1) * 100).loc[M3_NILS]
    colors = [HIGHLIGHT if v >= 0 else "#eb6834" for v in chg.values[::-1]]
    ax.barh(names[::-1], chg.values[::-1], color=colors, height=0.62)
    for y, (v, n2023) in enumerate(zip(chg.values[::-1], p.loc[M3_NILS[::-1], 2023].values)):
        ax.text(max(v, 0), y, f" {v:+.1f}%  ({n2023:,.0f} res.)", va="center", fontsize=8, color=INK_2)
    ax.axvline(0, color=MUTED, lw=0.8)
    ax.set_xlim(min(chg.min() * 1.5, -5), chg.max() * 1.9)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_title("Resident population change, 2011 to 2023")
    fig.tight_layout()
    save(fig, "fig03_m3_context.png")


def fig04_tiers(tiers) -> None:
    order = ["New / Unproven", "Solid", "Star Performer"]
    t = tiers.pivot(index="neighbourhood_cleansed", columns="performance_tier", values="n_listings")[order]
    t = t.loc[M3_NILS]
    share = t.div(t.sum(axis=1), axis=0)
    ramp = ["#9ec5f4", "#3987e5", "#184f95"]   # ordinal: tiers are ordered
    fig, ax = plt.subplots(figsize=(9, 3.6))
    left = np.zeros(len(share))
    names = [f"{nice(n)}  (n={t.loc[n].sum():,})" for n in share.index]
    for c, tier in zip(ramp, order):
        ax.barh(names, share[tier], left=left, color=c, height=0.62, edgecolor=SURFACE, linewidth=2,
                label=tier)
        for y, (l, v) in enumerate(zip(left, share[tier])):
            if v > 0.07:
                ax.text(l + v / 2, y, f"{v:.0%}", ha="center", va="center", fontsize=8,
                        color="#ffffff" if tier != "New / Unproven" else INK)
        left += share[tier].values
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(plt.matplotlib.ticker.PercentFormatter(1))
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(ncol=3, loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, fontsize=8)
    ax.set_title("Share of listings by Performance Tier, Municipality 3 NILs", pad=26)
    save(fig, "fig04_performance_tiers.png")


def fig05_treemap(listings) -> None:
    d = listings[listings.neighbourhood_cleansed.isin(TOP3)]
    rev = d.groupby(["neighbourhood_cleansed", "property_type"])["estimated_revenue_l365d"].sum()
    W, H = 100, 60
    totals = [rev[n].nlargest(3).sum() for n in TOP3]
    outer = squarify.squarify(squarify.normalize_sizes(totals, W, H), 0, 0, W, H)
    fig, ax = plt.subplots(figsize=(11, 6.2))
    unlabelled = []
    for k, (o, nil) in enumerate(zip(outer, TOP3)):
        top = rev[nil].nlargest(3)
        inner = squarify.squarify(squarify.normalize_sizes(top.values, o["dx"], o["dy"]),
                                  o["x"], o["y"], o["dx"], o["dy"])
        for r, (ptype, val) in zip(inner, top.items()):
            ax.add_patch(plt.Rectangle((r["x"], r["y"]), r["dx"], r["dy"], facecolor=CAT[k],
                                       edgecolor=SURFACE, linewidth=1.5))
            if r["dx"] > 9 and r["dy"] > 7:
                ax.text(r["x"] + 0.8, r["y"] + r["dy"] - 1.0, f"{ptype}\n€{val / 1e6:.2f}M",
                        va="top", ha="left", fontsize=8 if r["dx"] > 18 else 6.8, color="#ffffff")
            else:
                unlabelled.append((nil, ptype, val))
        ax.add_patch(plt.Rectangle((o["x"], o["y"]), o["dx"], o["dy"], facecolor="none",
                                   edgecolor=SURFACE, linewidth=4))
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")
    for c, n in zip(CAT, TOP3):
        ax.scatter([], [], marker="s", s=60, color=c,
                   label=f"{nice(n)} (€{rev[n].nlargest(3).sum() / 1e6:.1f}M)")
    ax.legend(ncol=3, loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, fontsize=8)
    ax.set_title("Estimated revenue, last 365 days: top-3 property types in the top-3 NILs", pad=24)
    items = [f"{nice(n).split('-')[0]} · {t} €{v / 1e6:.2f}M" for n, t, v in unlabelled]
    note = "Unlabelled cells: " + "; ".join(items[:3]) + (";\n" + "; ".join(items[3:]) if len(items) > 3 else "")
    fig.text(0.125, 0.04, note, fontsize=7, color=INK_2, va="top")
    save(fig, "fig05_revenue_treemap.png")


def fig06_boxplot(listings) -> None:
    milan_median = listings.price_eur.median()
    d = listings[listings.neighbourhood_cleansed.isin(TOP3) & (listings.price_eur <= 500)]
    data = [d.loc[d.neighbourhood_cleansed == n, "price_eur"].values for n in TOP3]
    rng = np.random.default_rng(42)
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for i, (vals, c) in enumerate(zip(data, CAT)):
        ax.scatter(i + rng.uniform(-0.18, 0.18, len(vals)), vals, s=8, color=c, alpha=0.28,
                   linewidths=0, zorder=1)
    bp = ax.boxplot(data, positions=range(3), widths=0.5, whis=1.5, showfliers=False,
                    patch_artist=True, zorder=2,
                    medianprops=dict(color=INK, lw=2), whiskerprops=dict(color=INK_2),
                    capprops=dict(color=INK_2), boxprops=dict(edgecolor=INK_2))
    for patch in bp["boxes"]:
        patch.set_facecolor((1, 1, 1, 0.55))
    ax.axhline(milan_median, color=MUTED, ls="--", lw=1)
    ax.text(-0.48, milan_median + 6, f"Milan median €{milan_median:.0f}", color=INK_2, fontsize=8,
            ha="left")
    for i, vals in enumerate(data):
        ax.text(i, -32, f"median €{np.median(vals):.0f} · n={len(vals):,}", ha="center", fontsize=8,
                color=INK_2)
    ax.set_xticks(range(3), [nice(n) for n in TOP3])
    ax.set_ylim(-45, 510)
    ax.set_ylabel("Price per night (€)")
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    ax.set_title("Nightly price distribution, top-3 NILs of Municipality 3 (listings ≤ €500)")
    save(fig, "fig06_price_boxplot.png")


def fig07_connections(polys) -> None:
    routes = pd.read_csv(RAW / "road_routes_m3.csv")
    dd = pd.read_csv(RAW / "driving_distances_by_nil.csv").set_index("NIL").loc[M3_NILS]
    dests = ["To Duomo (City Center)", "To Linate Airport", "To Malpensa Airport"]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(12, 5.2), gridspec_kw={"width_ratios": [1.15, 1]})
    draw_nils(ax, polys, {n: "#d9e8fb" for n in M3_NILS}, edge="#ffffff", lw=0.5)
    origin = "CITTA' STUDI"
    for c, dest in zip(CAT, dests):
        r = routes[(routes.Origin == origin) & (routes.Route1 == dest)].sort_values("Point Order")
        ax.plot(r.Longitude, r.Latitude, color=c, lw=2.2, solid_capstyle="round", label=dest[3:])
        ax.scatter(r.Longitude.iloc[-1], r.Latitude.iloc[-1], s=40, color=c, edgecolor=SURFACE, zorder=3)
    ax.set_xlim(8.70, 9.33)
    ax.set_ylim(45.40, 45.65)
    ax.legend(loc="lower left", frameon=False, fontsize=8)
    ax.set_title(f"Road routes from {nice(origin)} (Municipality 3 shaded)")
    cols = ["Duomo (City Center) (min)", "Linate Airport (min)", "Malpensa Airport (min)"]
    y = np.arange(len(M3_NILS))
    h = 0.26
    for k, (c, col) in enumerate(zip(CAT, cols)):
        ax2.barh(y + (k - 1) * h, dd[col].values, height=h - 0.03, color=c, label=col.replace(" (min)", ""))
        for yy, v in zip(y + (k - 1) * h, dd[col].values):
            ax2.text(v, yy, f" {v:.0f}", va="center", fontsize=7, color=INK_2)
    ax2.set_yticks(y, [nice(n) for n in M3_NILS])
    ax2.invert_yaxis()
    ax2.set_xlabel("Drive time (minutes)")
    ax2.spines["left"].set_visible(False)
    ax2.tick_params(axis="y", length=0)
    ax2.set_xlim(0, dd[cols].values.max() * 1.12)
    ax2.legend(ncol=3, loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, fontsize=7.5)
    ax2.set_title("Drive time from each Municipality 3 NIL", pad=22)
    fig.tight_layout()
    save(fig, "fig07_connections.png")


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    listings = pd.read_csv(PROC / "listings_clean.csv")
    muni = pd.read_csv(PROC / "municipality_metrics.csv", index_col=0)
    nil = pd.read_csv(PROC / "nil_metrics.csv", index_col=0)
    tiers = pd.read_csv(PROC / "m3_performance_tiers.csv")
    polys = load_polygons()
    nil_muni = pd.read_csv(RAW / "driving_distances_by_nil.csv").set_index("NIL")["Municipality"].to_dict()

    fig01_map(listings, muni, polys, nil_muni)
    fig02_metrics(muni)
    fig03_context(nil)
    fig04_tiers(tiers)
    fig05_treemap(listings)
    fig06_boxplot(listings)
    fig07_connections(polys)


if __name__ == "__main__":
    main()
