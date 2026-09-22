#!/usr/bin/env python3
"""
Renewal Risk & ARR-at-Risk Rollup
Obludzyner & Co. | Post-sales advisory for B2B SaaS | https://obludzyner.com

Open-source, zero-dependency companion to nrr-leak-diagnostic. That tool
estimates leak at the company level from 7 questions. This one rolls up
leak at the account level from your actual portfolio, so a leader can see
exactly which accounts, which CSMs, and which renewal window are driving
the number.

Zero dependencies. Python 3.8+. Runs fully offline -- your CSV never
leaves your machine.

Usage:
    python3 rollup.py --csv accounts.csv
    python3 rollup.py --csv accounts.csv --json --svg rollup.svg
    python3 rollup.py --generate-sample sample_accounts.csv   # writes a synthetic sample CSV

CSV columns required (header row, any order):
    account_name, csm, segment, arr, health_score, days_to_renewal

    arr            : annual recurring revenue, numeric
    health_score   : 0-100
    days_to_renewal: integer, can be negative if overdue
"""

import argparse
import csv
import json
import random
import sys

# Health band thresholds -- directional, adjust to your own scorecard.
RED_MAX = 45
YELLOW_MAX = 69

# Risk weight applied to ARR by band when computing "ARR at risk".
# Red counts fully at risk; Yellow counts partially; Green does not.
RISK_WEIGHTS = {"Red": 1.0, "Yellow": 0.35, "Green": 0.0}

RENEWAL_WINDOWS = [
    ("<= 30 days", lambda d: d <= 30),
    ("31-60 days", lambda d: 31 <= d <= 60),
    ("61-90 days", lambda d: 61 <= d <= 90),
    ("> 90 days", lambda d: d > 90),
]


def health_band(score):
    if score < RED_MAX:
        return "Red"
    if score < YELLOW_MAX:
        return "Yellow"
    return "Green"


def renewal_window(days):
    for label, test in RENEWAL_WINDOWS:
        if test(days):
            return label
    return "> 90 days"


def load_csv(path):
    accounts = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        required = {"account_name", "csm", "segment", "arr", "health_score", "days_to_renewal"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            print(f"CSV is missing required columns: {', '.join(sorted(missing))}", file=sys.stderr)
            sys.exit(1)
        for row in reader:
            accounts.append({
                "account_name": row["account_name"],
                "csm": row["csm"],
                "segment": row["segment"],
                "arr": float(row["arr"]),
                "health_score": float(row["health_score"]),
                "days_to_renewal": int(float(row["days_to_renewal"])),
            })
    return accounts


def analyze(accounts):
    for a in accounts:
        a["band"] = health_band(a["health_score"])
        a["risk_weighted_arr"] = a["arr"] * RISK_WEIGHTS[a["band"]]
        a["window"] = renewal_window(a["days_to_renewal"])

    total_arr = sum(a["arr"] for a in accounts)
    total_at_risk = sum(a["risk_weighted_arr"] for a in accounts)

    by_band = {}
    for band in ("Red", "Yellow", "Green"):
        rows = [a for a in accounts if a["band"] == band]
        by_band[band] = {
            "count": len(rows),
            "arr": sum(a["arr"] for a in rows),
        }

    by_csm = {}
    for a in accounts:
        d = by_csm.setdefault(a["csm"], {"count": 0, "arr_at_risk": 0.0, "total_arr": 0.0})
        d["count"] += 1
        d["arr_at_risk"] += a["risk_weighted_arr"]
        d["total_arr"] += a["arr"]

    by_segment = {}
    for a in accounts:
        d = by_segment.setdefault(a["segment"], {"count": 0, "arr_at_risk": 0.0, "total_arr": 0.0})
        d["count"] += 1
        d["arr_at_risk"] += a["risk_weighted_arr"]
        d["total_arr"] += a["arr"]

    by_window = {label: {"count": 0, "arr_at_risk": 0.0} for label, _ in RENEWAL_WINDOWS}
    for a in accounts:
        by_window[a["window"]]["count"] += 1
        by_window[a["window"]]["arr_at_risk"] += a["risk_weighted_arr"]

    top_at_risk = sorted(accounts, key=lambda a: a["risk_weighted_arr"], reverse=True)[:10]

    return {
        "portfolio": {
            "accounts": len(accounts),
            "total_arr": round(total_arr),
            "total_arr_at_risk": round(total_at_risk),
            "pct_arr_at_risk": round((total_at_risk / total_arr) * 100, 1) if total_arr else 0,
        },
        "by_health_band": {k: {"count": v["count"], "arr": round(v["arr"])} for k, v in by_band.items()},
        "by_csm": {
            k: {"count": v["count"], "arr_at_risk": round(v["arr_at_risk"]), "total_arr": round(v["total_arr"])}
            for k, v in sorted(by_csm.items(), key=lambda kv: kv[1]["arr_at_risk"], reverse=True)
        },
        "by_segment": {
            k: {"count": v["count"], "arr_at_risk": round(v["arr_at_risk"]), "total_arr": round(v["total_arr"])}
            for k, v in sorted(by_segment.items(), key=lambda kv: kv[1]["arr_at_risk"], reverse=True)
        },
        "by_renewal_window": {k: {"count": v["count"], "arr_at_risk": round(v["arr_at_risk"])} for k, v in by_window.items()},
        "top_accounts_at_risk": [
            {
                "account_name": a["account_name"],
                "csm": a["csm"],
                "segment": a["segment"],
                "arr": round(a["arr"]),
                "health_score": a["health_score"],
                "band": a["band"],
                "days_to_renewal": a["days_to_renewal"],
                "risk_weighted_arr": round(a["risk_weighted_arr"]),
            }
            for a in top_at_risk
        ],
    }


def render_text(result):
    p = result["portfolio"]
    lines = []
    lines.append("=" * 64)
    lines.append("RENEWAL RISK & ARR-AT-RISK ROLLUP")
    lines.append("=" * 64)
    lines.append(f"Portfolio: {p['accounts']} accounts, ${p['total_arr']:,} total ARR")
    lines.append(f"ARR at risk (risk-weighted): ${p['total_arr_at_risk']:,} ({p['pct_arr_at_risk']}% of portfolio)")
    lines.append("")
    lines.append("BY HEALTH BAND")
    for band, v in result["by_health_band"].items():
        lines.append(f"  {band:<7} {v['count']:>4} accounts   ${v['arr']:>12,} ARR")
    lines.append("")
    lines.append("BY CSM (sorted by ARR at risk)")
    for csm, v in result["by_csm"].items():
        lines.append(f"  {csm:<20} ${v['arr_at_risk']:>12,} at risk   ({v['count']} accounts, ${v['total_arr']:,} total)")
    lines.append("")
    lines.append("BY SEGMENT (sorted by ARR at risk)")
    for seg, v in result["by_segment"].items():
        lines.append(f"  {seg:<20} ${v['arr_at_risk']:>12,} at risk   ({v['count']} accounts, ${v['total_arr']:,} total)")
    lines.append("")
    lines.append("BY RENEWAL WINDOW")
    for label, v in result["by_renewal_window"].items():
        lines.append(f"  {label:<12} {v['count']:>4} accounts   ${v['arr_at_risk']:>12,} at risk")
    lines.append("")
    lines.append("TOP 10 ACCOUNTS AT RISK")
    for a in result["top_accounts_at_risk"]:
        lines.append(
            f"  {a['account_name']:<24} {a['band']:<7} health={a['health_score']:>3.0f}  "
            f"renews in {a['days_to_renewal']:>4}d  ${a['risk_weighted_arr']:>10,} at risk  (CSM: {a['csm']})"
        )
    lines.append("=" * 64)
    lines.append("This is the open-source, directional version of the account-level")
    lines.append("rollup used inside a SHIFT Method engagement. Health bands and risk")
    lines.append("weights here are illustrative -- adjust RED_MAX / YELLOW_MAX / RISK_WEIGHTS")
    lines.append("in rollup.py to match your own scorecard.")
    lines.append("For a Revenue Audit built on your real definitions and data:")
    lines.append("  https://obludzyner.com")
    lines.append("=" * 64)
    return "\n".join(lines)


def render_svg(result, path):
    by_csm = result["by_csm"]
    max_val = max((v["arr_at_risk"] for v in by_csm.values()), default=1) or 1

    def hbar_row(y, label, value, max_value, color):
        w = 0 if max_value == 0 else max(2, (value / max_value) * 260)
        return (
            f'<text x="0" y="{y-4}" font-size="11" font-family="monospace" fill="#0a1a33">{label[:22]}</text>'
            f'<rect x="0" y="{y}" width="260" height="14" fill="#eef1f6" />'
            f'<rect x="0" y="{y}" width="{w:.1f}" height="14" fill="{color}" />'
            f'<text x="{min(w,255)+5}" y="{y+11}" font-size="10" font-family="monospace" fill="#0a1a33">${value:,.0f}</text>'
        )

    rows = []
    y = 60
    rows.append('<text x="0" y="20" font-size="15" font-family="sans-serif" font-weight="bold" fill="#0a1a33">ARR at risk by CSM</text>')
    for csm, v in by_csm.items():
        rows.append(hbar_row(y, csm, v["arr_at_risk"], max_val, "#d9542f"))
        y += 26

    band = result["by_health_band"]
    y += 20
    rows.append(f'<text x="0" y="{y}" font-size="15" font-family="sans-serif" font-weight="bold" fill="#0a1a33">Accounts by health band</text>')
    y += 20
    band_colors = {"Red": "#d9542f", "Yellow": "#d9a52f", "Green": "#2f9e6e"}
    max_count = max((v["count"] for v in band.values()), default=1) or 1
    for name in ("Red", "Yellow", "Green"):
        v = band[name]
        rows.append(hbar_row(y, f"{name} ({v['count']})", v["count"], max_count, band_colors[name]))
        y += 26

    total_h = y + 40
    p = result["portfolio"]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 {total_h}" font-family="sans-serif">
<rect x="0" y="0" width="300" height="{total_h}" fill="#ffffff" />
<text x="0" y="40" font-size="12" font-family="monospace" fill="#5a6472">ARR at risk: ${p['total_arr_at_risk']:,} of ${p['total_arr']:,} ({p['pct_arr_at_risk']}%)</text>
{''.join(rows)}
<text x="0" y="{total_h-10}" font-size="9" font-family="monospace" fill="#9aa5b1">Obludzyner &amp; Co. | obludzyner.com | open-source rollup</text>
</svg>'''
    with open(path, "w") as f:
        f.write(svg)


def generate_sample(path, n=40, seed=7):
    rnd = random.Random(seed)
    csms = ["Dana K.", "Marco P.", "Priya S.", "Tomer L."]
    segments = ["SMB", "Mid-Market", "Enterprise"]
    rows = []
    for i in range(n):
        segment = rnd.choice(segments)
        base_arr = {"SMB": 15000, "Mid-Market": 60000, "Enterprise": 220000}[segment]
        arr = round(base_arr * rnd.uniform(0.5, 2.2))
        health = round(rnd.betavariate(2.2, 2.0) * 100, 1)
        days_to_renewal = rnd.randint(-10, 240)
        rows.append({
            "account_name": f"Account-{i+1:03d}",
            "csm": rnd.choice(csms),
            "segment": segment,
            "arr": arr,
            "health_score": health,
            "days_to_renewal": days_to_renewal,
        })
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["account_name", "csm", "segment", "arr", "health_score", "days_to_renewal"])
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Renewal Risk & ARR-at-Risk Rollup (open-source)")
    parser.add_argument("--csv", type=str, help="path to accounts CSV")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--svg", type=str, help="path to write an SVG chart to")
    parser.add_argument("--generate-sample", type=str, metavar="PATH", help="write a synthetic sample CSV and exit")
    parser.add_argument("--sample-size", type=int, default=40)
    args = parser.parse_args()

    if args.generate_sample:
        generate_sample(args.generate_sample, n=args.sample_size)
        print(f"Wrote synthetic sample CSV with {args.sample_size} accounts to {args.generate_sample}")
        return

    if not args.csv:
        print("Provide --csv accounts.csv (or --generate-sample to create one)", file=sys.stderr)
        sys.exit(1)

    accounts = load_csv(args.csv)
    if not accounts:
        print("CSV had no rows.", file=sys.stderr)
        sys.exit(1)

    result = analyze(accounts)

    if args.svg:
        render_svg(result, args.svg)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_text(result))


if __name__ == "__main__":
    main()
