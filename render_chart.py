#!/usr/bin/env python3
"""
Dashboard renderer for the Renewal Risk & ARR-at-Risk Rollup.
Obludzyner & Co. | https://obludzyner.com

OPTIONAL. rollup.py has zero dependencies and computes the real numbers.
This script turns that JSON output into the polished dashboard PNG shown
in the README. It requires matplotlib:

    pip install matplotlib
    python3 rollup.py --csv accounts.csv --json > result.json
    python3 render_chart.py result.json examples/sample_dashboard.png
"""

import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# -- design tokens (obludzyner.com / dataviz skill reference palette) --------
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
SURFACE = "#fcfcfb"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

BLUE = "#2a78d6"
GRAY = "#c3c2b7"
GOOD = "#0ca30c"
WARNING = "#fab219"
CRITICAL = "#d03b3b"

BAND_COLOR = {"Red": CRITICAL, "Yellow": WARNING, "Green": GOOD}

plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["text.color"] = INK


def rounded_hbar(ax, y, value, max_value, color, height=0.56, x0=0):
    length = max(value - x0, max_value * 0.006) if max_value else 0.01
    ax.add_patch(FancyBboxPatch(
        (x0, y - height / 2), length, height,
        boxstyle=f"round,pad=0,rounding_size={height/2}",
        linewidth=0, facecolor=color, mutation_aspect=1,
    ))


def fmt_money(v):
    return f"${v:,.0f}"


def bar_panel(ax, title, rows, value_fmt=fmt_money):
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", color=INK, pad=14)
    max_value = max((v for _, v, _ in rows), default=1) * 1.32 or 1
    left_pad = max_value * 0.62
    ys = list(range(len(rows)))[::-1]
    for y, (label, value, color) in zip(ys, rows):
        rounded_hbar(ax, y, value, max_value, color)
        ax.text(-max_value * 0.03, y, label, ha="right", va="center",
                 fontsize=11, color=INK_SECONDARY)
        ax.text(value + max_value * 0.02, y, value_fmt(value), ha="left", va="center",
                 fontsize=11, fontweight="bold", color=INK)
    ax.set_xlim(-left_pad, max_value)
    ax.set_ylim(-0.7, max(len(rows), 1) - 0.3)
    ax.set_yticks([])
    ax.set_xticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.axvline(0, color=BASELINE, linewidth=1)


def render(result, out_path):
    p = result["portfolio"]
    by_band = result["by_health_band"]
    by_csm = result["by_csm"]
    top = result["top_accounts_at_risk"][:6]

    fig = plt.figure(figsize=(8.6, 10.6), dpi=200)
    fig.patch.set_facecolor(SURFACE)

    gs = fig.add_gridspec(
        5, 1, left=0.08, right=0.94, top=0.965, bottom=0.03,
        height_ratios=[1.15, 0.85, max(0.75, 0.30 * len(by_csm)), max(0.75, 0.30 * len(top) + 0.4), 0.3],
        hspace=0.4,
    )

    fig.text(0.08, 0.985, "OBLUDZYNER & CO.  -  OPEN-SOURCE RENEWAL RISK ROLLUP",
              fontsize=9.5, color=INK_MUTED, fontweight="bold", ha="left")

    # -- hero ------------------------------------------------------------
    ax_hero = fig.add_subplot(gs[0])
    ax_hero.axis("off")
    ax_hero.text(0, 0.86, "ARR AT RISK (RISK-WEIGHTED)", fontsize=11, color=INK_MUTED,
                  fontweight="bold", transform=ax_hero.transAxes)
    ax_hero.text(0, 0.42, fmt_money(p["total_arr_at_risk"]), fontsize=48, color=INK,
                  fontweight="bold", transform=ax_hero.transAxes, va="center")
    ax_hero.text(0, 0.14,
                  f"{p['pct_arr_at_risk']:.1f}% of ${p['total_arr']:,} across {p['accounts']} accounts",
                  fontsize=13, color=INK_SECONDARY, transform=ax_hero.transAxes)

    # -- health band cards -------------------------------------------------
    ax_band = fig.add_subplot(gs[1])
    ax_band.axis("off")
    cards = [("Red", "CRITICAL"), ("Yellow", "WATCH"), ("Green", "HEALTHY")]
    card_w = 0.30
    gap = 0.05
    for i, (band, tag) in enumerate(cards):
        v = by_band.get(band, {"count": 0, "arr": 0})
        x0 = i * (card_w + gap)
        color = BAND_COLOR[band]
        ax_band.add_patch(FancyBboxPatch((x0, 0.0), card_w, 1.0, boxstyle="round,pad=0.01,rounding_size=0.05",
                                           linewidth=0, facecolor="#f4f3ef", transform=ax_band.transAxes))
        ax_band.add_patch(FancyBboxPatch((x0, 0.86), 0.05, 0.10, boxstyle="round,pad=0,rounding_size=0.02",
                                           linewidth=0, facecolor=color, transform=ax_band.transAxes))
        ax_band.text(x0 + 0.09, 0.90, f"{band.upper()}  -  {tag}", fontsize=9, color=INK_MUTED,
                      fontweight="bold", transform=ax_band.transAxes, va="center")
        ax_band.text(x0 + 0.03, 0.55, f"{v['count']} accts", fontsize=15, color=INK,
                      fontweight="bold", transform=ax_band.transAxes)
        ax_band.text(x0 + 0.03, 0.22, fmt_money(v["arr"]), fontsize=12, color=INK_SECONDARY,
                      transform=ax_band.transAxes)

    # -- CSM panel ---------------------------------------------------------
    ax_csm = fig.add_subplot(gs[2])
    rows = [(csm, v["arr_at_risk"], BLUE) for csm, v in by_csm.items()]
    bar_panel(ax_csm, "ARR at risk by CSM", rows)

    # -- top accounts table -------------------------------------------------
    ax_tbl = fig.add_subplot(gs[3])
    ax_tbl.axis("off")
    ax_tbl.set_title("Top accounts at risk", loc="left", fontsize=13, fontweight="bold", color=INK, pad=14)
    headers = ["Account", "CSM", "Health", "Renews", "ARR at risk"]
    col_x = [0.0, 0.34, 0.55, 0.70, 1.0]
    row_h = 1.0 / (len(top) + 1)
    y0 = 1.0 - row_h * 0.4
    for cx, h in zip(col_x, headers):
        ha = "right" if h == "ARR at risk" else "left"
        ax_tbl.text(cx, y0, h, fontsize=9.5, color=INK_MUTED, fontweight="bold",
                     ha=ha, transform=ax_tbl.transAxes)
    ax_tbl.axhline(y0 - row_h * 0.32, color=GRIDLINE, linewidth=1, xmin=0, xmax=1)
    for i, a in enumerate(top):
        y = y0 - row_h * (i + 1)
        band_color = BAND_COLOR[a["band"]]
        ax_tbl.add_patch(FancyBboxPatch((-0.045, y - 0.012), 0.02, 0.02,
                                          boxstyle="round,pad=0,rounding_size=0.01",
                                          linewidth=0, facecolor=band_color, transform=ax_tbl.transAxes))
        ax_tbl.text(col_x[0], y, a["account_name"], fontsize=10.5, color=INK, transform=ax_tbl.transAxes)
        ax_tbl.text(col_x[1], y, a["csm"], fontsize=10.5, color=INK_SECONDARY, transform=ax_tbl.transAxes)
        ax_tbl.text(col_x[2], y, f"{a['health_score']:.0f}", fontsize=10.5, color=band_color,
                     fontweight="bold", transform=ax_tbl.transAxes)
        ax_tbl.text(col_x[3], y, f"{a['days_to_renewal']}d", fontsize=10.5, color=INK_SECONDARY,
                     transform=ax_tbl.transAxes)
        ax_tbl.text(col_x[4], y, fmt_money(a["risk_weighted_arr"]), fontsize=10.5, color=INK,
                     fontweight="bold", ha="right", transform=ax_tbl.transAxes)
    ax_tbl.set_xlim(-0.06, 1.02)
    ax_tbl.set_ylim(0, 1)

    ax_footer = fig.add_subplot(gs[4])
    ax_footer.axis("off")
    ax_footer.axhline(0.9, color=GRIDLINE, linewidth=1, xmin=0, xmax=1)
    ax_footer.text(0, 0.15, "Open-source, directional version. obludzyner.com  -  Book a Revenue Audit for your real numbers.",
                     fontsize=9, color=INK_MUTED, transform=ax_footer.transAxes)

    fig.savefig(out_path, facecolor=SURFACE)
    print(f"Wrote {out_path}")


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 render_chart.py result.json out.png", file=sys.stderr)
        sys.exit(1)
    with open(sys.argv[1]) as f:
        result = json.load(f)
    render(result, sys.argv[2])


if __name__ == "__main__":
    main()
