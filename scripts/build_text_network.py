"""Rebuild the Gephi keyword network from the `tags` column.

NIL to keyword graph, edge weight = share of the NIL's listings using the keyword,
communities found with Louvain (fixed seed).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
FIG = ROOT / "reports" / "figures"

SEED = 42
NILS = ["BUENOS AIRES - VENEZIA", "CITTA' STUDI", "PARCO FORLANINI - ORTICA"]
MIN_SHARE = 0.08  # min share of a NIL's listings using the keyword
MIN_COUNT = 2
STOPWORDS = {"milan", "milano", "apartment", "just", "conditioning", "air", "room", "area", "located", "stay"}

PALETTE = ["#2a78d6", "#eb6834", "#1baf7a"]
INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#9a998f"


def clean_tokens(raw: pd.Series) -> list[set[str]]:
    per_listing = [
        {t.strip().lower() for t in str(x).split(",") if t.strip()} for x in raw.dropna()
    ]
    vocab = set().union(*per_listing)
    fixed = []
    for toks in per_listing:
        out = set()
        for t in toks:
            if t.endswith("ight") and t[:-4] in vocab:
                t = t[:-4]
            if t not in STOPWORDS and len(t) > 2:
                out.add(t)
        fixed.append(out)
    return fixed


def build_graph(listings: pd.DataFrame) -> nx.Graph:
    g = nx.Graph()
    for nil in NILS:
        toks = clean_tokens(listings.loc[listings["neighbourhood_cleansed"] == nil, "tags"])
        n = len(toks)
        counts = Counter(t for s in toks for t in s)
        label = nil.title().replace("'", "’").replace(" - ", "-")
        g.add_node(label, kind="nil", n_listings=n)
        for kw, c in sorted(counts.items()):  # sorted for reproducibility
            share = c / n
            if share >= MIN_SHARE and c >= MIN_COUNT:
                g.add_node(kw, kind="keyword")
                g.add_edge(label, kw, weight=round(share, 4))
    return g


def draw(g: nx.Graph, comm_of: dict[str, int]) -> None:
    pos = nx.spring_layout(g, weight="weight", seed=SEED, k=0.75, iterations=300)
    strength = dict(g.degree(weight="weight"))
    fig, ax = plt.subplots(figsize=(12, 9), dpi=200)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    for u, v, d in g.edges(data=True):
        hub = u if g.nodes[u]["kind"] == "nil" else v
        ax.plot(*zip(pos[u], pos[v]), color=PALETTE[comm_of[hub] % 3], alpha=0.25,
                lw=0.4 + 3 * d["weight"], zorder=1)
    for node, (x, y) in pos.items():
        color = PALETTE[comm_of[node] % 3]
        if g.nodes[node]["kind"] == "nil":
            ax.scatter(x, y, s=900, color=color, edgecolor="#fcfcfb", linewidth=2, zorder=3)
            ax.text(x, y - 0.075, node, ha="center", va="top", fontsize=11, fontweight="bold",
                    color=INK, zorder=5,
                    bbox=dict(boxstyle="round,pad=0.25", fc="#fcfcfb", ec="none", alpha=0.85))
        else:
            s = 20 + 900 * strength[node]
            ax.scatter(x, y, s=s, color=color, edgecolor="#fcfcfb", linewidth=1, alpha=0.9, zorder=2)
            ax.annotate(node, (x, y), xytext=(0, 7 + 12 * min(strength[node], 0.6)),
                        textcoords="offset points", ha="center", va="bottom",
                        fontsize=7 + 6 * min(strength[node], 0.6), color=INK_2, zorder=4)
    for nil_node in [n for n in g if g.nodes[n]["kind"] == "nil"]:
        ax.scatter([], [], s=80, color=PALETTE[comm_of[nil_node] % 3],
                   label=f"Community of {nil_node}")
    ax.legend(loc="lower left", frameon=False, fontsize=9, labelcolor=INK_2)
    ax.set_title("Keywords of Airbnb descriptions in three Municipality 3 NILs\n"
                 "node size = share of listings using the keyword · colour = Louvain community",
                 fontsize=12, color=INK, loc="left")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(FIG / "fig08_text_network.png", facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    listings = pd.read_csv(PROC / "listings_clean.csv", usecols=["neighbourhood_cleansed", "tags"])
    g = build_graph(listings)
    communities = nx.community.louvain_communities(g, weight="weight", seed=SEED)
    modularity = nx.community.modularity(g, communities, weight="weight")
    # stable colour per NIL
    hubs = [n for n in g if g.nodes[n]["kind"] == "nil"]
    order = sorted(range(len(communities)),
                   key=lambda i: min((hubs.index(h) for h in communities[i] if h in hubs), default=99))
    comm_of = {n: rank for rank, i in enumerate(order) for n in communities[i]}

    pd.DataFrame([(u, v, d["weight"]) for u, v, d in g.edges(data=True)],
                 columns=["source", "target", "weight"]).to_csv(PROC / "text_network_edges.csv", index=False)
    strength = dict(g.degree(weight="weight"))
    nodes = pd.DataFrame({
        "id": list(g.nodes),
        "kind": [g.nodes[n]["kind"] for n in g],
        "community": [comm_of[n] for n in g],
        "weighted_degree": [round(strength[n], 4) for n in g],
        "degree": [g.degree(n) for n in g],
    }).sort_values(["community", "weighted_degree"], ascending=[True, False])
    nodes.to_csv(PROC / "text_network_nodes.csv", index=False)

    draw(g, comm_of)
    sizes = nodes.groupby("community").size().to_dict()
    shared = sum(1 for n in g if g.nodes[n]["kind"] == "keyword" and g.degree(n) > 1)
    print(f"nodes={g.number_of_nodes()} edges={g.number_of_edges()} communities={len(communities)} "
          f"modularity={modularity:.3f} sizes={sizes} keywords shared by >1 NIL={shared}")
    for c, sub in nodes[nodes.kind == "keyword"].groupby("community"):
        print(c, ", ".join(sub.head(12).id))


if __name__ == "__main__":
    main()
