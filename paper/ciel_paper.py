#!/usr/bin/env python3
"""Forward paper test of the Ciel engine on wheat and gold.

Uses src/ciel_engine.py as the single source of truth.

    python ciel_paper.py --iniciar    # arranca forward desde hoy
    python ciel_paper.py              # un ciclo (correr cada hora)
    python ciel_paper.py --stats      # reporte
    python ciel_paper.py --lucid      # motor con reglas flat 16:40 (preview Lucid)
"""
import argparse
import csv
import json
import os
import sys

from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
AQUI = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(AQUI, "..", "src")
sys.path.insert(0, os.path.abspath(SRC))

from ciel_engine import (  # noqa: E402
    CielConfig,
    MARKETS,
    bars_closed,
    fetch_yahoo,
    mapa_tendencia,
    run_paper_cycle,
)

ESTADO = os.path.join(AQUI, "paper_state.json")
LOG = os.path.join(AQUI, "paper_trades.csv")
MUESTRA_OBJETIVO = 50


def cargar():
    if os.path.exists(ESTADO):
        with open(ESTADO, encoding="utf-8") as f:
            return json.load(f)
    return {}


def guardar(st):
    tmp = ESTADO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, ESTADO)


def anotar(filas, nombre_mercado):
    nuevo = not os.path.exists(LOG)
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["timestamp", "mercado", "evento", "motivo", "precio",
                        "pnl", "modo", "lado", "entrada", "sl", "tp"])
        for ev in filas:
            lado = "SELL" if ev["dir"] == -1 else "BUY"
            w.writerow([
                ev["ts"], nombre_mercado, ev["evento"], ev["motivo"],
                ev["precio"], ev["pnl"], ev["modo"], lado,
                round(ev["entry"], 4), round(ev["sl"], 4), round(ev["tp"], 4),
            ])


def stats():
    if not os.path.exists(LOG):
        print("todavia no hay trades cerrados")
        return
    por = {}
    with open(LOG, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["evento"] != "CIERRE":
                continue
            por.setdefault(r["mercado"], []).append((float(r["pnl"]), r["motivo"]))
    if not por:
        print("hay entradas abiertas pero ningun cierre todavia")
        return
    print("%-8s%7s%8s%11s%7s   %s" % ("mercado", "trades", "WR", "neto", "PF", "motivos"))
    for m, v in sorted(por.items()):
        p = [x for x, _ in v]
        w = [x for x in p if x > 0]
        g, l = sum(w), abs(sum(x for x in p if x <= 0))
        mot = {}
        for _, k in v:
            mot[k] = mot.get(k, 0) + 1
        print("%-8s%7d%7.1f%%%+11.2f%7.2f   %s"
              % (m, len(p), len(w) / len(p) * 100, sum(p), (g / l if l else 0), mot))
        if len(p) < MUESTRA_OBJETIVO:
            print("%8s  faltan %d trades para que la muestra decida algo"
                  % ("", MUESTRA_OBJETIVO - len(p)))
    print("\nCriterio (paper/README.md):")
    print("  SIGUE  si trigo PF>=1.3 con >=50 trades")
    print("  CAE    si trigo PF<1.1 o oro PF<1.0")
    print("Vara historica -- Trigo: PF 1.77 | Oro: PF 1.17 (2y backtest)")


def evaluar_mercado(sym, st, cfg):
    info = MARKETS[sym]
    diario = fetch_yahoo(sym, "1d", "2y")
    h1 = bars_closed(fetch_yahoo(sym, "1h", "60d"))
    if len(h1) < 61:
        return [], info["nombre"] + ": datos insuficientes"
    tmap = mapa_tendencia(diario)
    ms = st.setdefault(sym, {
        "pos": None, "ultima_barra": 0, "trades": 0, "wins": 0, "pnl": 0.0,
    })
    eventos, resumen = run_paper_cycle(h1, tmap, info["dpp"], ms, cfg)
    linea = "%-6s %s" % (info["nombre"], resumen)
    return eventos, linea


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=list(MARKETS))
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--lucid", action="store_true",
                    help="reglas sesion Lucid (flat 16:40, sin entradas >=15:00)")
    ap.add_argument("--iniciar", action="store_true")
    a = ap.parse_args()

    cfg = CielConfig(lucid_session=a.lucid)

    if a.stats:
        stats()
        return

    st = cargar()
    if a.iniciar:
        for sym in MARKETS:
            h1 = bars_closed(fetch_yahoo(sym, "1h", "60d"))
            st[sym] = {
                "pos": None,
                "ultima_barra": h1[-1][0] if h1 else 0,
                "trades": 0, "wins": 0, "pnl": 0.0,
            }
            print("%s: arranca desde %s" % (
                MARKETS[sym]["nombre"],
                datetime.fromtimestamp(h1[-1][0], ET).strftime("%Y-%m-%d %H:%M")
                if h1 else "sin datos",
            ))
        guardar(st)
        modo = "LUCID" if a.lucid else "LEGACY"
        print("\nForward limpio (%s). Correr cada hora en sesion; ver con --stats." % modo)
        return

    mercados = [a.market] if a.market else list(MARKETS)
    for sym in mercados:
        try:
            eventos, linea = evaluar_mercado(sym, st, cfg)
            print(linea)
            for ev in eventos:
                print("   %s  %-6s %-7s %10s  %s" % (
                    ev["ts"], ev["evento"], ev["motivo"], ev["precio"], ev["pnl"]))
            if eventos:
                anotar(eventos, MARKETS[sym]["nombre"])
        except Exception as exc:
            print("%s: error -> %s" % (sym, exc), file=sys.stderr)
    guardar(st)


if __name__ == "__main__":
    main()
