# -*- coding: utf-8 -*-
"""Feasibility LucidFlex $150k para Ciel — usa ciel_engine v3.4 (zona 50).
Uso: python backtest_150k_ciel.py
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest_combo_eval as ce
from ciel_engine import CielConfig, fetch_yahoo, mapa_tendencia, run_backtest

TARGET = 9000.0
MAXLOSS = 4500.0
MAX_MICROS = 100


def simular(dias_pnl, n_micros):
    eq = 0.0
    peak = 0.0
    peor = 0.0
    for i, (d, p) in enumerate(dias_pnl, 1):
        eq += p * n_micros
        peak = max(peak, eq)
        dd = peak - eq
        peor = max(peor, dd)
        if dd >= MAXLOSS:
            return ("MUERE", i, peor)
        if eq >= TARGET:
            return ("PASA", i, peor)
    return ("NO LLEGA", len(dias_pnl), peor)


def main():
    print("FEASIBILITY 150K FLEX — target $9,000 | MLL $4,500 EOD | ciel_engine v3.4\n")
    daily = fetch_yahoo("GC=F", "1d", "2y")
    h1 = fetch_yahoo("GC=F", "1h", "730d")
    tmap = mapa_tendencia(daily)
    cfg = CielConfig(zona_trend=50, cost=ce.COST)
    trades = run_backtest(h1, tmap, ce.DPP, cfg)
    dias = defaultdict(float)
    for d, p, _, _ in trades:
        dias[d] += p
    serie = sorted(dias.items())
    tot1 = sum(p for _, p in serie)
    print(f"  Ciel combo (zona 50) a 1 micro: {len(serie)} dias op, {tot1:+.0f}$ ({tot1/24:+.0f}$/mes)\n")
    print(f"  {'micros':>7} {'resultado':>10} {'dias':>6} {'~meses':>7} {'peor DD':>10}")
    algun_pasa = False
    for n in (1, 2, 3, 5, 8, 12, 20, 40, 100):
        if n > MAX_MICROS:
            continue
        res, d, peor = simular(serie, n)
        meses = d / 21.0
        flag = "  <== VIABLE" if res == "PASA" else ""
        if res == "PASA":
            algun_pasa = True
        print(f"  {n:>7} {res:>10} {d:>6} {meses:>7.1f} {peor:>10.0f}{flag}")
    print()
    if not algun_pasa:
        print("  Ningun sizing pasa antes del MLL con esta serie diaria (oro solo).")
    else:
        print("  Hay sizing viable en oro solo. Para cartera oro+trigo ver sim_eval_lucid.py")
    print("\n  Para eval completo con consistencia 50%: python sim_eval_lucid.py")


if __name__ == "__main__":
    main()
