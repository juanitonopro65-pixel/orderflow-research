#!/usr/bin/env python3
"""Compara paper (Yahoo) vs demo/ejecutor Ciel por fecha y mercado.

Uso:
  python analysis/compare_demo.py
  python analysis/compare_demo.py --min-trades 20
"""
import argparse
import csv
import os
import re
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(__file__), "..")


def load_paper(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("evento") != "CIERRE":
                continue
            out.append({
                "ts": r["timestamp"][:10],
                "mercado": r.get("mercado", ""),
                "pnl": float(r["pnl"]),
                "motivo": r.get("motivo", ""),
            })
    return out


def load_demo(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if "CIERRE" not in r.get("evento", ""):
                continue
            m = re.search(r"pnl ([-+][\d.]+)", r.get("detalle", ""))
            if not m:
                continue
            mid = (r.get("mercado") or "").strip().upper()
            out.append({
                "ts": r["timestamp"][:10],
                "modo": r.get("modo", ""),
                "mercado": mid,
                "pnl": float(m.group(1)),
                "motivo": r.get("evento", "").replace("CIERRE ", ""),
            })
    return out


def pf(rows):
    if not rows:
        return 0.0, 0, 0.0, 0.0
    pl = [x["pnl"] for x in rows]
    w = [x for x in pl if x > 0]
    l = [x for x in pl if x <= 0]
    p = sum(w) / abs(sum(l)) if l else 99.0
    wr = sum(1 for x in pl if x > 0) / len(pl) * 100
    return p, len(pl), sum(pl), wr


def line(label, rows):
    p, n, tot, wr = pf(rows)
    if n:
        print(f"  {label:16} n={n:3} WR={wr:5.1f}% PF={p:5.2f} net=${tot:+8.2f}")
    else:
        print(f"  {label:16} (sin cierres)")
    return n, wr, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", default=os.path.join(ROOT, "paper", "paper_trades.csv"))
    ap.add_argument("--demo", default=os.path.join(ROOT, "src", "ciel_exec_log.csv"))
    ap.add_argument("--min-trades", type=int, default=20,
                    help="mínimo cierres demo para veredicto")
    a = ap.parse_args()

    paper = load_paper(a.paper)
    demo = load_demo(a.demo)

    print("=" * 64)
    print("  Paper (Yahoo) vs Demo/Ejecutor (Quantower)")
    print("=" * 64)

    _, paper_wr, paper_pf = line("PAPER oro", [x for x in paper if "Oro" in x["mercado"]])
    line("PAPER trigo", [x for x in paper if "Trigo" in x["mercado"]])
    _, pwr_tot, ppf_tot = line("PAPER total", paper)

    n_demo, dwr, dpf = line("DEMO total", demo)
    line("DEMO MGC", [x for x in demo if x["mercado"] in ("MGC", "")])
    line("DEMO ZW", [x for x in demo if x["mercado"] == "ZW"])

    if paper and demo:
        slip = []
        pd = defaultdict(list)
        for x in paper:
            pd[x["ts"]].append(x["pnl"])
        dd = defaultdict(list)
        for x in demo:
            dd[x["ts"]].append(x["pnl"])
        for d in sorted(set(pd) & set(dd)):
            slip.append(sum(pd[d]) - sum(dd[d]))
        if slip:
            print(f"\n  Días con ambos: {len(slip)}  "
                  f"slippage medio/día: ${sum(slip)/len(slip):+.2f}")

    print()
    if n_demo < a.min_trades:
        print(f"  Veredicto: ESPERAR — demo tiene {n_demo}/{a.min_trades} cierres")
    elif dpf >= 1.0 and (pwr_tot == 0 or abs(dwr - pwr_tot) <= 15):
        print("  Veredicto: OK → podés comprar Flex $150k (criterio PF/WR)")
    else:
        print(f"  Veredicto: NO — PF demo={dpf:.2f} WR demo={dwr:.1f}% "
              f"(paper WR={pwr_tot:.1f}% PF={ppf_tot:.2f})")

    print("  Criterio: PF>=1.0 y WR dentro de ±15% del paper")
    print("=" * 64)


if __name__ == "__main__":
    main()
