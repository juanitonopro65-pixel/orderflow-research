#!/usr/bin/env python3
"""Reproduces every number in docs/RESULTS.md from the raw trade ledger.

Run it. If a figure in the docs is not printed here, it is not supported.

    python analysis/live_results.py

Why this file exists: an earlier reading of this same ledger reported -$273.20.
That figure was wrong -- four synthetic unit-test rows were sitting in the LIVE
ledger and inflated it by $157. The filter below is the fix, and the reason the
filter is applied *in code you can read* rather than in a spreadsheet.
"""
import csv
import re
from collections import OrderedDict

LEDGER = "data/of_exec_log.csv"
POINT_VALUE = 10.0        # MGC: 1.0 point = $10
SL_POINTS, TP_POINTS = 6, 9


def is_synthetic(row):
    """Unit-test rows written into the live ledger during development.

    Two tells: a literal 'entry 4000.0' (the fixture price) and, in one row,
    the timestamp is the character 't'. Neither is a real fill.
    """
    ts_ok = re.match(r"^\d{4}-\d{2}-\d{2} ", row["timestamp"])
    return (not ts_ok) or "entry 4000.0" in row.get("detalle", "")


def load(mode="LIVE"):
    out = []
    with open(LEDGER, encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            if "CIERRE" not in row.get("evento", ""):
                continue
            if (row.get("modo") or "").strip() != mode:
                continue
            m = re.search(r"pnl ([-+][\d.]+)", row.get("detalle", ""))
            if not m:
                continue
            out.append((row, float(m.group(1)), row["evento"].replace("CIERRE", "").strip()))
    return out


def report(rows, label):
    pnl = [p for _, p, _ in rows]
    wins = [p for p in pnl if p > 0]
    losses = [p for p in pnl if p <= 0]
    n = len(pnl)
    if not n:
        return
    print(f"\n{label}")
    print(f"  trades        {n}")
    print(f"  record        {len(wins)}W / {len(losses)}L   win rate {len(wins)/n*100:.1f}%")
    print(f"  net P&L       ${sum(pnl):+,.2f}")
    print(f"  avg win       ${sum(wins)/len(wins):+.2f}   (full TP would be +${TP_POINTS*POINT_VALUE:.0f})")
    print(f"  avg loss      ${sum(losses)/len(losses):+.2f}   (full SL would be -${SL_POINTS*POINT_VALUE:.0f})")

    reasons = OrderedDict()
    for _, _, why in rows:
        reasons[why] = reasons.get(why, 0) + 1
    print("  exit reason  ", ", ".join(f"{k}={v}" for k, v in
                                       sorted(reasons.items(), key=lambda kv: -kv[1])))
    hit_tp = sum(v for k, v in reasons.items() if k == "TP")
    on_clock = sum(v for k, v in reasons.items() if k.startswith("TIME"))
    print(f"  -> reached target: {hit_tp}/{n} ({hit_tp/n*100:.0f}%)"
          f"   closed on the clock: {on_clock}/{n} ({on_clock/n*100:.0f}%)")

    # Break-even arithmetic on the payoff ACTUALLY realised, not the designed one.
    aw, al = sum(wins)/len(wins), abs(sum(losses)/len(losses))
    print(f"  realised payoff ratio  {aw/al:.2f} : 1")
    print(f"  break-even win rate at that payoff  {al/(aw+al)*100:.1f}%   (achieved {len(wins)/n*100:.1f}%)")


def daily(rows, label):
    days = OrderedDict()
    for row, p, _ in rows:
        d = row["timestamp"][:10]
        days.setdefault(d, [0.0, 0])
        days[d][0] += p
        days[d][1] += 1
    print(f"\n{label}")
    acc = 0.0
    for d, (p, c) in days.items():
        acc += p
        print(f"  {d}   {c:>3} trades   {p:>+9.2f}   cumulative {acc:>+9.2f}")


if __name__ == "__main__":
    live_all = load("LIVE")
    synthetic = [r for r in live_all if is_synthetic(r[0])]
    live = [r for r in live_all if not is_synthetic(r[0])]

    print("=" * 66)
    print("OF-MGC  --  real-money results")
    print("=" * 66)

    print(f"\nSynthetic rows removed from the ledger: {len(synthetic)}"
          f"  (worth ${sum(p for _, p, _ in synthetic):+.2f})")
    for row, p, _ in synthetic:
        print(f"    {row['timestamp']:<20} {row['detalle'][:52]}")

    report(live_all, "AS LOGGED (contaminated -- do not cite)")
    report(live, "CLEAN (this is the real result)")
    daily(live, "Daily equity curve, clean")

    dry = load("DRY")
    report(dry, "DRY-RUN -- the sample that justified going live")
    print("\nThe dry-run sample is what the go/no-go decision was made on."
          "\nIt did not survive contact with real fills.")
