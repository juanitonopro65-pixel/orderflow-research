# -*- coding: utf-8 -*-
"""COMBO TREND+FADE vs el eval Lucid — motor unificado en ciel_engine.py.
Uso: python backtest_combo_eval.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ciel_engine import CielConfig, fetch_yahoo, mapa_tendencia, run_backtest

DPP, COST = 10.0, 5.0


def run_trend(h1, tmap, zona=20):
    cfg = CielConfig(zona_trend=zona, cost=COST)
    return [(d, p, tag) for d, p, tag, _ in run_backtest(h1, tmap, DPP, cfg) if tag == "TREND"]


def run_fade(h1, tmap, ext=85, tp_r=0.5):
    cfg = CielConfig(fade_ext=ext, fade_tp_r=tp_r, cost=COST)
    return [(d, p, tag) for d, p, tag, _ in run_backtest(h1, tmap, DPP, cfg) if tag == "FADE"]


def eval_metrics(trades, label):
    if not trades:
        print(f"  {label}: sin trades")
        return
    trades = sorted(trades, key=lambda x: x[0])
    daily = {}
    for d, p, _ in trades:
        daily[d] = daily.get(d, 0.0) + p
    days = sorted(daily)
    bal = peak = mdd = 0.0
    muertes = 0
    bal_t = peak_t = 0.0
    for d in days:
        bal += daily[d]
        peak = max(peak, bal)
        mdd = max(mdd, peak - bal)
        bal_t += daily[d]
        peak_t = max(peak_t, bal_t)
        if peak_t - bal_t >= 1000.0:
            muertes += 1
            bal_t = 0.0
            peak_t = 0.0
    pl = [p for _, p, _ in trades]
    w = [x for x in pl if x > 0]
    l = [x for x in pl if x <= 0]
    pf = sum(w) / abs(sum(l)) if l else 99
    dias_verdes = sum(1 for d in days if daily[d] > 0)
    dias_100 = sum(1 for d in days if daily[d] >= 100.0)
    dias_rojos_400 = sum(1 for d in days if daily[d] <= -400.0)
    total = sum(pl)
    print(
        f"  {label:14} trades={len(pl):>3} PF={pf:.2f} tot=${total:+8.0f} | maxDD=${mdd:>5.0f} | "
        f"MUERTES trailing $1k (2y): {muertes} | dias op={len(days)} verdes={dias_verdes} "
        f">=+$100: {dias_100} | <=-$400: {dias_rojos_400}"
    )


def main():
    print("=" * 118)
    print("  TREND(v3.3 zona20) vs FADE vs COMBO — GC=F 2y (ciel_engine)")
    print("=" * 118)
    daily = fetch_yahoo("GC=F", "1d", "2y")
    h1 = fetch_yahoo("GC=F", "1h", "730d")
    tmap = mapa_tendencia(daily)
    tt = run_trend(h1, tmap)
    ff = run_fade(h1, tmap)
    print()
    eval_metrics(tt, "TREND solo")
    eval_metrics(ff, "FADE solo")
    eval_metrics(tt + ff, "COMBO T+F")
    print()
    tnd = [p for _, p, _ in tt]
    lat = [p for _, p, _ in ff]
    print(f"  Aporte por regimen: TREND ${sum(tnd):+.0f} | FADE ${sum(lat):+.0f}")
    print("=" * 118)


if __name__ == "__main__":
    main()
