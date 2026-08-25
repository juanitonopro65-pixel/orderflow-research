# -*- coding: utf-8 -*-
"""Bootstrap Monte Carlo — P(pasar) LucidFlex $150k sobre P&L diario Ciel.

Wrapper de fase 3 del plan. Misma lógica que `sim_eval_lucid.py --bootstrap`.

Uso:
  python bootstrap_portfolio.py
  python bootstrap_portfolio.py --n 5000 --lucid-session
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sim_eval_lucid import bootstrap, load_portfolio_daily  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000, help="tiradas Monte Carlo")
    ap.add_argument("--lucid-session", action="store_true",
                    help="backtest con flat 16:40 (reglas Lucid)")
    a = ap.parse_args()

    mode = "LUCID" if a.lucid_session else "LEGACY"
    print(f"Bootstrap portfolio Ciel ({mode}) — {a.n} tiradas\n")
    try:
        daily = load_portfolio_daily(a.lucid_session)
    except Exception as e:
        print(f"  Error datos Yahoo: {e}")
        return 1

    op = sum(1 for _, p in daily if p != 0)
    tot = sum(p for _, p in daily)
    print(f"  Dias con P&L: {op}  |  total 1x1: ${tot:+.0f}\n")

    b = bootstrap(daily, ladder=True, n=a.n)
    print(f"  Escalera 1→2  P(pasar)={b['p_pass']:.1f}%  mediana dias={b['med_days']}")
    print(f"  desglose: {b['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
