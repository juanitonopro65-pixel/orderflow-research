# -*- coding: utf-8 -*-
"""Simula eval LucidFlex $150k con reglas reales sobre P&L diario de Ciel.

Reglas modeladas:
  - Profit target $9,000
  - Max Loss Limit $4,500 trailing EOD
  - Consistencia 50% en eval (mejor día / profit total <= 50%)
  - Mínimo 2 días con actividad antes de poder pasar
  - Escalera opcional: 1 contrato c/u hasta +$1,500, luego 2 c/u

Uso: python sim_eval_lucid.py
     python sim_eval_lucid.py --lucid-session   (usa reglas flat 16:40 en backtest)
     python sim_eval_lucid.py --bootstrap 2000  (Monte Carlo)
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ciel_engine import (
    CielConfig,
    MARKETS,
    daily_pnl_series,
    fetch_yahoo,
    mapa_tendencia,
    run_backtest,
)

TARGET = 9000.0
MAX_LOSS = 4500.0
LADDER_CUSHION = 1500.0
MIN_TRADING_DAYS = 2
CONSISTENCY_MAX = 0.50


def contracts_for_equity(eq: float, ladder: bool) -> float:
    if not ladder:
        return 1.0
    return 2.0 if eq >= LADDER_CUSHION else 1.0


def sim_path(daily: list[tuple[object, float]], ladder: bool) -> dict:
    """Una tirada determinista día a día."""
    eq = 0.0
    peak = 0.0
    worst_dd = 0.0
    best_day = 0.0
    day_pnls: list[float] = []
    trading_days = 0
    days = 0
    status = "EN CURSO"

    for _, raw_pnl in daily:
        days += 1
        if raw_pnl == 0.0:
            continue
        trading_days += 1
        mult = contracts_for_equity(eq, ladder)
        pnl = raw_pnl * mult
        day_pnls.append(pnl)
        best_day = max(best_day, pnl)
        eq += pnl
        peak = max(peak, eq)
        worst_dd = max(worst_dd, peak - eq)
        if peak - eq >= MAX_LOSS:
            return {
                "status": "MUERE",
                "days": days,
                "trading_days": trading_days,
                "eq": eq,
                "worst_dd": worst_dd,
                "best_day": best_day,
            }
        if eq >= TARGET:
            if trading_days < MIN_TRADING_DAYS:
                status = "META SIN MIN DIAS"
                continue
            consist = best_day / eq if eq > 0 else 1.0
            if consist > CONSISTENCY_MAX:
                status = "META SIN CONSISTENCIA"
                continue
            return {
                "status": "PASA",
                "days": days,
                "trading_days": trading_days,
                "eq": eq,
                "worst_dd": worst_dd,
                "best_day": best_day,
                "consistency": consist,
            }

    return {
        "status": status,
        "days": days,
        "trading_days": trading_days,
        "eq": eq,
        "worst_dd": worst_dd,
        "best_day": best_day,
    }


def bootstrap(daily: list[tuple], ladder: bool, n: int) -> dict:
    if not daily:
        return {}
    counts: dict[str, int] = defaultdict(int)
    pass_days: list[int] = []
    for _ in range(n):
        sample = [daily[random.randrange(len(daily))] for _ in range(len(daily))]
        r = sim_path(sample, ladder)
        counts[r["status"]] += 1
        if r["status"] == "PASA":
            pass_days.append(r["days"])
    total = n
    p_pass = counts["PASA"] / total * 100
    med = sorted(pass_days)[len(pass_days) // 2] if pass_days else 0
    return {"p_pass": p_pass, "med_days": med, "counts": dict(counts)}


def load_portfolio_daily(lucid_session: bool) -> list[tuple]:
    cfg = CielConfig(lucid_session=lucid_session)
    all_trades = []
    mults = []
    for sym, info in MARKETS.items():
        daily = fetch_yahoo(sym, "1d", "2y")
        h1 = fetch_yahoo(sym, "1h", "730d")
        tmap = mapa_tendencia(daily)
        trades = run_backtest(h1, tmap, info["dpp"], cfg)
        all_trades.append(trades)
        mults.append(1.0)
    return daily_pnl_series(all_trades, mults)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lucid-session", action="store_true",
                    help="backtest con flat 16:40 (reglas Lucid)")
    ap.add_argument("--bootstrap", type=int, default=0, metavar="N",
                    help="Monte Carlo con N tiradas")
    ap.add_argument("--no-ladder", action="store_true")
    a = ap.parse_args()

    mode = "LUCID session" if a.lucid_session else "LEGACY overnight"
    print(f"Sim eval LucidFlex $150k — motor Ciel ({mode})\n")
    print(f"  target=${TARGET:.0f}  MLL=${MAX_LOSS:.0f} EOD  consistencia<={CONSISTENCY_MAX:.0%}")
    print(f"  min dias trading={MIN_TRADING_DAYS}  escalera colchon=${LADDER_CUSHION:.0f}\n")

    try:
        daily = load_portfolio_daily(a.lucid_session)
    except Exception as e:
        print(f"  Error descargando datos: {e}")
        print("  (necesita internet y Yahoo accesible)")
        return

    op_days = sum(1 for _, p in daily if p != 0)
    tot_1x = sum(p for _, p in daily)
    print(f"  Dias calendario con P&L: {op_days}  |  P&L total 1x1: ${tot_1x:+.0f}\n")

    ladder = not a.no_ladder
    for label, lad in [("1+1 fijo", False), ("escalera 1->2", True)]:
        if a.no_ladder and lad:
            continue
        r = sim_path(daily, lad)
        print(f"  {label:18} -> {r['status']:22}  dias={r['days']:>4}  "
              f"eq=${r['eq']:+.0f}  peorDD=${r['worst_dd']:.0f}")
        if r["status"] == "PASA":
            print(f"    consistencia={r.get('consistency', 0):.1%}  "
                  f"mejor dia=${r['best_day']:.0f}")

    if a.bootstrap > 0:
        print(f"\n  Bootstrap {a.bootstrap} tiradas (escalera 1->2):")
        b = bootstrap(daily, ladder=True, n=a.bootstrap)
        print(f"    P(pasar)={b['p_pass']:.1f}%  mediana dias={b['med_days']}")
        print(f"    desglose: {b['counts']}")


if __name__ == "__main__":
    main()
