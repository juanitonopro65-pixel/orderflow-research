#!/usr/bin/env python3
"""Forward paper test of the Ciel engine on wheat and gold.

Why this exists: the backtest says wheat carries PF 1.77 and gold PF 1.17, and
that the two are uncorrelated (r=-0.004). Both numbers come from historical bars
the strategy has never actually traded. This runs the identical logic forward on
live data, logging every decision, so the backtest gets confirmed or refuted
against price action it has not seen.

It places no orders and touches no broker. Paper only.

THE POINT OF COMPARISON: wheat's edge declines year over year
(+$16,479 / +$7,031 / +$4,521). The question is whether the 2026 rate holds, not
whether the 2024 one does. Target sample: ~50 closed trades per market.

    python ciel_paper.py             one cycle for both markets
    python ciel_paper.py --market ZW=F
    python ciel_paper.py --stats     report without touching state

Run it hourly while the session is open. Repeated runs inside the same hour are
harmless: each bar is processed exactly once, keyed by its own timestamp.
"""
import argparse
import csv
import json
import os
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
AQUI = os.path.dirname(os.path.abspath(__file__))
ESTADO = os.path.join(AQUI, "paper_state.json")
LOG = os.path.join(AQUI, "paper_trades.csv")

COSTO = 5.0                  # por trade, ida y vuelta
RIESGO_MIN, RIESGO_MAX = 150.0, 400.0
TIMEOUT_BARRAS = 8           # el motor original cierra a las 8 velas horarias
MUESTRA_OBJETIVO = 50        # antes de esto la muestra no decide nada

MERCADOS = {
    "ZW=F": {"nombre": "Trigo", "dpp": 50.0},   # 1 contrato entero, riesgo ~$262
    "GC=F": {"nombre": "Oro", "dpp": 10.0},     # micro MGC, riesgo ~$203
}


def bajar(sym, itv, rng):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + sym + "?interval=" + itv + "&range=" + rng)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 CielPaper/1.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=40).read().decode())
    r = d["chart"]["result"][0]
    ts, q = r["timestamp"], r["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        out.append((t, o, h, l, c))
    return out


def solo_cerradas(barras, itv_seg=3600):
    """Descarta la vela en curso.

    Sin esto el motor decidiria sobre un cierre que todavia puede moverse, y el
    forward dejaria de ser comparable con el backtest, que solo ve cierres.
    """
    ahora = datetime.now().timestamp()
    return [b for b in barras if b[0] + itv_seg <= ahora]


def sma(v, i, p):
    return sum(v[i - p + 1:i + 1]) / p if i >= p - 1 else None


def atr(H, L, C, i, p=14):
    if i < p:
        return None
    s = 0.0
    for k in range(i - p + 1, i + 1):
        s += max(H[k] - L[k], abs(H[k] - C[k - 1]), abs(L[k] - C[k - 1]))
    return s / p


def mapa_tendencia(diario):
    """ALCISTA / BAJISTA / LATERAL por dia. Copia exacta de daily_trend_map.

    Dos detalles que NO son cosmeticos y que una version 'parecida' se come:

    1. Clasifica con `j = i-1`, el dia ANTERIOR. Usar el cierre del propio dia
       para decidir como operarlo es sesgo de anticipacion: informacion que a esa
       hora todavia no existe.
    2. Exige las TRES condiciones -precio sobre MA20, MA20 sobre MA50, y MA20
       subiendo respecto a 5 dias atras-. Una version laxa (solo MA20 vs MA50)
       marca tendencia en mercados que en realidad estan picoteando, y manda al
       motor a operar tendencia dentro del ruido.

    Medido con la version laxa y con anticipacion: trigo WR 44% en vez de 62%.
    """
    C = [x[4] for x in diario]
    m = {}
    for i in range(len(diario)):
        f = datetime.fromtimestamp(diario[i][0], ET).date()
        j = i - 1
        if j < 50:
            m[f] = "LATERAL"
            continue
        ma20, ma50, ma20p = sma(C, j, 20), sma(C, j, 50), sma(C, j - 5, 20)
        p = C[j]
        if ma20 is None or ma50 is None or ma20p is None:
            m[f] = "LATERAL"
        elif p > ma20 > ma50 and ma20 > ma20p:
            m[f] = "ALCISTA"
        elif p < ma20 < ma50 and ma20 < ma20p:
            m[f] = "BAJISTA"
        else:
            m[f] = "LATERAL"
    return m


def evaluar(sym, st):
    """Un ciclo para un mercado. Devuelve (eventos, linea_resumen)."""
    cfg = MERCADOS[sym]
    dpp = cfg["dpp"]
    lo_p, hi_p = RIESGO_MIN / dpp, RIESGO_MAX / dpp   # recorte del stop, en puntos

    diario = bajar(sym, "1d", "2y")
    h1 = solo_cerradas(bajar(sym, "1h", "60d"))
    if len(h1) < 61:
        return [], cfg["nombre"] + ": datos insuficientes"

    tmap = mapa_tendencia(diario)
    T = [x[0] for x in h1]
    H = [x[2] for x in h1]
    L = [x[3] for x in h1]
    C = [x[4] for x in h1]

    ms = st.setdefault(sym, {"pos": None, "ultima_barra": 0, "trades": 0,
                             "wins": 0, "pnl": 0.0})
    eventos = []

    for i in range(60, len(h1)):
        if T[i] <= ms["ultima_barra"]:
            continue                       # ya procesada en una corrida anterior
        dt = datetime.fromtimestamp(T[i], ET)
        ms["ultima_barra"] = T[i]

        # --- 1) gestionar la posicion abierta contra ESTA vela
        if ms["pos"]:
            p = ms["pos"]
            dirn, e, slv, tpv = p["dir"], p["entry"], p["sl"], p["tp"]
            toca_sl = (L[i] <= slv) if dirn == 1 else (H[i] >= slv)
            toca_tp = (H[i] >= tpv) if dirn == 1 else (L[i] <= tpv)
            cierre = None
            # El SL se comprueba ANTES que el TP: si una vela contiene los dos
            # no se sabe cual llego primero, y suponer el peor caso es lo honesto.
            if toca_sl:
                cierre, precio, pnl = "SL", slv, -abs(e - slv) * dpp - COSTO
            elif toca_tp:
                cierre, precio, pnl = "TP", tpv, abs(tpv - e) * dpp - COSTO
            elif i - p["barra_i"] >= TIMEOUT_BARRAS:
                mv = (C[i] - e) if dirn == 1 else (e - C[i])
                cierre, precio, pnl = "TIEMPO", C[i], mv * dpp - COSTO
            if cierre:
                ms["trades"] += 1
                ms["wins"] += 1 if pnl > 0 else 0
                ms["pnl"] += pnl
                eventos.append([dt.strftime("%Y-%m-%d %H:%M"), cfg["nombre"],
                                "CIERRE", cierre, round(precio, 4), round(pnl, 2),
                                p["modo"], "SELL" if dirn == -1 else "BUY",
                                round(e, 4), round(slv, 4), round(tpv, 4)])
                ms["pos"] = None
            # Se sale SIEMPRE, se haya cerrado o no. Esto importa: si se cae
            # aqui y se busca entrada en la MISMA vela, el motor reentra justo
            # despues de un stop, en plena contra, y fabrica perdidas que el
            # backtest nunca toma. Medido: WR 40% en vez de 65%.
            continue

        # --- 2) buscar entrada
        mins = dt.hour * 60 + dt.minute
        if not (9 * 60 + 30 <= mins < 16 * 60):
            continue
        reg = tmap.get(dt.date(), "LATERAL")
        a = atr(H, L, C, i)
        if not a or a <= 0:
            continue
        lo = min(L[max(0, i - 47):i + 1])
        hi = max(H[max(0, i - 47):i + 1])
        if hi <= lo:
            continue
        p100 = (C[i] - lo) / (hi - lo) * 100
        sd = min(max(1.75 * a, lo_p), hi_p)

        modo = dirn = tpd = None
        if reg != "LATERAL":                        # TREND: a favor del diario
            if reg == "ALCISTA" and p100 <= 50:
                modo, dirn, tpd = "TREND", 1, 1.5 * sd
            elif reg == "BAJISTA" and p100 >= 50:
                modo, dirn, tpd = "TREND", -1, 1.5 * sd
        else:                                       # FADE: extremos del rango
            if p100 >= 85:
                modo, dirn, tpd = "FADE", -1, 0.5 * sd
            elif p100 <= 15:
                modo, dirn, tpd = "FADE", 1, 0.5 * sd
        if not modo:
            continue

        e = C[i]
        slv, tpv = e - dirn * sd, e + dirn * tpd
        ms["pos"] = {"dir": dirn, "entry": e, "sl": slv, "tp": tpv,
                     "barra_i": i, "modo": modo,
                     "abierta": dt.strftime("%Y-%m-%d %H:%M")}
        eventos.append([dt.strftime("%Y-%m-%d %H:%M"), cfg["nombre"], "ABRE", modo,
                        round(e, 4), "", modo, "SELL" if dirn == -1 else "BUY",
                        round(e, 4), round(slv, 4), round(tpv, 4)])

    abierta = "abierta" if ms["pos"] else "plana"
    wr = ms["wins"] / ms["trades"] * 100 if ms["trades"] else 0.0
    resumen = ("%-6s %3d trades  WR %5.1f%%  %+9.2f  (%s)"
               % (cfg["nombre"], ms["trades"], wr, ms["pnl"], abierta))
    return eventos, resumen


def cargar():
    if os.path.exists(ESTADO):
        with open(ESTADO, encoding="utf-8") as f:
            return json.load(f)
    return {}


def guardar(st):
    tmp = ESTADO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, ESTADO)     # atomico: un corte a media escritura no corrompe


def anotar(filas):
    nuevo = not os.path.exists(LOG)
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["timestamp", "mercado", "evento", "motivo", "precio",
                        "pnl", "modo", "lado", "entrada", "sl", "tp"])
        w.writerows(filas)


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
    print("\nVara del backtest -- Trigo: WR 65.4%% PF 1.77 | Oro: WR 58.4%% PF 1.17")
    print("Lo que importa no es superarla, es si el forward la CONTRADICE.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=list(MERCADOS))
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--iniciar", action="store_true",
                    help="marca las velas actuales como vistas sin operarlas, "
                         "para que el forward empiece HOY y no reprocese historia")
    a = ap.parse_args()
    if a.stats:
        stats()
        return
    st = cargar()
    if a.iniciar:
        for sym in MERCADOS:
            h1 = solo_cerradas(bajar(sym, "1h", "60d"))
            st[sym] = {"pos": None, "ultima_barra": h1[-1][0] if h1 else 0,
                       "trades": 0, "wins": 0, "pnl": 0.0}
            print("%s: arranca desde %s" % (
                MERCADOS[sym]["nombre"],
                datetime.fromtimestamp(h1[-1][0], ET).strftime("%Y-%m-%d %H:%M")
                if h1 else "sin datos"))
        guardar(st)
        print("\nForward limpio. Correr cada hora; ver con --stats.")
        return
    todos = []
    for sym in ([a.market] if a.market else list(MERCADOS)):
        try:
            ev, resumen = evaluar(sym, st)
            todos += ev
            print(resumen)
            for e in ev:
                print("   %s  %-6s %-7s %10s  %s" % (e[0], e[2], e[3], e[4], e[5]))
        except Exception as exc:
            print("%s: error -> %s" % (sym, exc), file=sys.stderr)
    if todos:
        anotar(todos)
    guardar(st)


if __name__ == "__main__":
    main()
