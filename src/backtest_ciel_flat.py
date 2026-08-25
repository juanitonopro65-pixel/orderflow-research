# -*- coding: utf-8 -*-
"""Compara backtest LEGACY (stops nocturnos) vs LUCID (flat 16:40, sin entradas >= 15:00).

Mide el impacto de las reglas reales de Lucid sobre PF y P&L antes de operar el eval.
Uso: python backtest_ciel_flat.py [dias]     (default 730)
     python backtest_ciel_flat.py 60          solo últimos 60 días
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ciel_engine import (
    CielConfig,
    MARKETS,
    fetch_yahoo,
    mapa_tendencia,
    run_backtest,
    trades_metrics,
)


def rep(label: str, trades: list, motivos: bool = False):
    m = trades_metrics(trades)
    if m["n"] < 1:
        print(f"  {label:28} sin trades")
        return
    print(
        f"  {label:28} n={m['n']:>4} WR={m['wr']:>5.1f}% PF={m['pf']:>5.2f} "
        f"tot=${m['total']:>+9.0f}"
    )
    if motivos:
        mot: dict[str, int] = {}
        for t in trades:
            k = t[3]
            mot[k] = mot.get(k, 0) + 1
        print(f"    motivos: {mot}")


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 730
    rng = f"{days}d" if days <= 730 else "2y"
    print("=" * 72)
    print(f"  Ciel LEGACY vs LUCID SESSION — ventana {rng}")
    print("  LEGACY: SL/TP overnight | entradas 9:30–16:00")
    print("  LUCID:  flat 16:40 ET   | entradas 9:30–15:00 | sin overnight")
    print("=" * 72)

    cfg_legacy = CielConfig(lucid_session=False)
    cfg_lucid = CielConfig(lucid_session=True)

    for sym, info in MARKETS.items():
        print(f"\n  --- {info['nombre']} ({sym}) dpp=${info['dpp']:.0f} ---")
        daily = fetch_yahoo(sym, "1d", "2y")
        h1 = fetch_yahoo(sym, "1h", rng)
        if len(h1) < 61:
            print("  datos insuficientes")
            continue
        tmap = mapa_tendencia(daily)
        dpp = info["dpp"]
        t_legacy = run_backtest(h1, tmap, dpp, cfg_legacy)
        t_lucid = run_backtest(h1, tmap, dpp, cfg_lucid)
        rep("LEGACY", t_legacy, motivos=True)
        rep("LUCID", t_lucid, motivos=True)
        if t_legacy and t_lucid:
            d_pf = trades_metrics(t_lucid)["pf"] - trades_metrics(t_legacy)["pf"]
            d_tot = trades_metrics(t_lucid)["total"] - trades_metrics(t_legacy)["total"]
            print(f"    delta PF={d_pf:+.2f}  delta $={d_tot:+.0f}")

    print("\n" + "=" * 72)


if __name__ == "__main__":
    main()
