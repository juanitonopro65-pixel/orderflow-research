#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KE (trigo Kansas City) a traves del motor de Ciel, con controles.

Por que existe: KE quedo como "candidato nuevo sin analizar" en el README --
37,467 contratos/dia, el segundo grano mas liquido despues de ZW. La pregunta es
si agrega algo al par trigo+oro o si es el MISMO trade que ZW con otro nombre.

METODO: el motor se copia de src/backtest_combo_eval.py sin cambios de logica
(run_trend + run_fade = Ciel), parametrizado por simbolo y por $/punto. El
recorte del stop del original -min(max(1.75*ATR,15),40) en puntos de oro a $10-
es la banda de riesgo $150-$400; aca se traduce dividiendo por el $/punto de
cada mercado, que es exactamente lo que hizo el estudio de 8 instrumentos.

CONTROLES PRIMERO. Si el port no reproduce las cifras ya publicadas para oro
(375 trades, 58.4%, +$4,863, PF 1.17) y trigo (511, 65.4%, +$28,031, PF 1.77),
entonces cualquier numero que de para KE no significa nada. El README lo dice:
"El oro reproduce el original exacto, que es la prueba de que el port es fiel".

    python ke_wheat.py
"""
import json
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
COST = 5.0
RIESGO_MIN, RIESGO_MAX = 150.0, 400.0

# $/punto por contrato entero. ZW y KE cotizan en centavos/bushel sobre 5.000
# bushels -> 1 centavo = $50. El oro se mide como micro MGC ($10) igual que en
# el estudio original.
MERCADOS = [
    ("GC=F", "Oro (MGC)", 10.0),
    ("ZW=F", "Trigo ZW", 50.0),
    ("KE=F", "Trigo KC (KE)", 50.0),
]


def yh(sym, itv, rng):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + sym + "?interval=" + itv + "&range=" + rng)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 AgusBot/1.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=40).read().decode())
    res = d["chart"]["result"][0]
    ts, q = res["timestamp"], res["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        out.append((t, o, h, l, c))
    return out


def sma(v, i, p):
    return sum(v[i - p + 1:i + 1]) / p if i >= p - 1 else None


def daily_trend_map(daily):
    C = [c for *_, c in daily]
    out = {}
    for i in range(len(daily)):
        d = datetime.fromtimestamp(daily[i][0], ET).date()
        j = i - 1
        if j < 50:
            out[d] = "LATERAL"
            continue
        ma20, ma50 = sma(C, j, 20), sma(C, j, 50)
        ma20p = sma(C, j - 5, 20)
        p = C[j]
        if p > ma20 > ma50 and ma20 > ma20p:
            out[d] = "ALCISTA"
        elif p < ma20 < ma50 and ma20 < ma20p:
            out[d] = "BAJISTA"
        else:
            out[d] = "LATERAL"
    return out


def atr(H, L, C, i, p=14):
    if i < p:
        return None
    trs = [max(H[k] - L[k], abs(H[k] - C[k - 1]), abs(L[k] - C[k - 1]))
           for k in range(i - p + 1, i + 1)]
    return sum(trs) / p


def run(h1, tmap, dpp, zona, modo):
    """modo 'TREND' o 'FADE'. Copia literal del motor, con dpp y clamp parametrizados."""
    T = [x[0] for x in h1]
    H = [x[2] for x in h1]
    L = [x[3] for x in h1]
    C = [x[4] for x in h1]
    lo_p, hi_p = RIESGO_MIN / dpp, RIESGO_MAX / dpp
    trades = []
    pos = None
    for i in range(60, len(h1)):
        dt = datetime.fromtimestamp(T[i], ET)
        if pos:
            dirn, e, slv, tpv, i0 = pos
            hit_sl = (L[i] <= slv) if dirn == 1 else (H[i] >= slv)
            hit_tp = (H[i] >= tpv) if dirn == 1 else (L[i] <= tpv)
            if hit_sl:
                trades.append((dt.date(), -abs(e - slv) * dpp - COST, modo))
                pos = None
            elif hit_tp:
                trades.append((dt.date(), abs(tpv - e) * dpp - COST, modo))
                pos = None
            elif i - i0 >= 8:
                mv = (C[i] - e) if dirn == 1 else (e - C[i])
                trades.append((dt.date(), mv * dpp - COST, modo))
                pos = None
            continue
        mins = dt.hour * 60 + dt.minute
        if not (9 * 60 + 30 <= mins < 16 * 60):
            continue
        tr = tmap.get(dt.date(), "LATERAL")
        a = atr(H, L, C, i)
        if not a or a <= 0:
            continue
        lo = min(L[max(0, i - 47):i + 1])
        hi = max(H[max(0, i - 47):i + 1])
        if hi <= lo:
            continue
        p100 = (C[i] - lo) / (hi - lo) * 100
        sd = min(max(1.75 * a, lo_p), hi_p)
        if modo == "TREND":
            if tr == "LATERAL":
                continue
            if tr == "ALCISTA" and p100 > zona:
                continue
            if tr == "BAJISTA" and p100 < 100 - zona:
                continue
            dirn = 1 if tr == "ALCISTA" else -1
            tpd = 1.5 * sd
        else:
            if tr != "LATERAL":
                continue
            if p100 >= 85:
                dirn = -1
            elif p100 <= 15:
                dirn = 1
            else:
                continue
            tpd = 0.5 * sd
        e = C[i]
        pos = (dirn, e, e - dirn * sd, e + dirn * tpd, i)
    return trades


def metricas(trades):
    if not trades:
        return None
    pl = [p for _, p, _ in trades]
    w = [x for x in pl if x > 0]
    l = [x for x in pl if x <= 0]
    por_ano = {}
    for d, p, _ in trades:
        por_ano[d.year] = por_ano.get(d.year, 0.0) + p
    daily = {}
    for d, p, _ in trades:
        daily[d] = daily.get(d, 0.0) + p
    bal = peak = mdd = 0.0
    for d in sorted(daily):
        bal += daily[d]
        peak = max(peak, bal)
        mdd = max(mdd, peak - bal)
    return {
        "n": len(pl), "wr": len(w) / len(pl) * 100,
        "pf": (sum(w) / abs(sum(l))) if l else 99.0,
        "tot": sum(pl), "mdd": mdd, "por_ano": por_ano,
        "daily": daily,
    }


def correlacion(a, b):
    """r de Pearson sobre P&L diario, solo dias en que AMBOS operaron."""
    dias = sorted(set(a) & set(b))
    if len(dias) < 10:
        return None, len(dias)
    xs = [a[d] for d in dias]
    ys = [b[d] for d in dias]
    n = len(dias)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return (num / (dx * dy) if dx and dy else None), n


def main():
    print("=" * 100)
    print("  KE (trigo Kansas City) por el motor de Ciel -- con oro y ZW como CONTROLES")
    print("=" * 100)
    print("  Vara publicada:  Oro 375t 58.4%% +$4,863 PF 1.17  |  Trigo ZW 511t 65.4%% +$28,031 PF 1.77")
    print("  Si los controles no reproducen esas cifras, el numero de KE no significa nada.\n")

    resultados = {}
    for sym, nombre, dpp in MERCADOS:
        try:
            daily = yh(sym, "1d", "2y")
            h1 = yh(sym, "1h", "730d")
        except Exception as exc:
            print("  %-16s ERROR bajando datos: %s" % (nombre, exc))
            continue
        tmap = daily_trend_map(daily)
        print("  %-16s %d velas diarias, %d horarias" % (nombre, len(daily), len(h1)))
        # el estudio original no dice que zona uso; se prueban las dos versiones
        for zona in (20, 50):
            tr = run(h1, tmap, dpp, zona, "TREND")
            fa = run(h1, tmap, dpp, zona, "FADE")
            m = metricas(tr + fa)
            if not m:
                continue
            anos = " ".join("%d:%+.0f" % (y, v) for y, v in sorted(m["por_ano"].items()))
            print("      zona %d/%d  n=%3d  WR %4.1f%%  PF %5.2f  tot $%+9.0f  maxDD $%6.0f   %s"
                  % (zona, 100 - zona, m["n"], m["wr"], m["pf"], m["tot"], m["mdd"], anos))
            resultados[(sym, zona)] = m
        print()

    # correlacion entre mercados con la zona que mejor reproduzca los controles
    print("  " + "-" * 96)
    for zona in (20, 50):
        ke = resultados.get(("KE=F", zona))
        zw = resultados.get(("ZW=F", zona))
        gc = resultados.get(("GC=F", zona))
        if not (ke and zw and gc):
            continue
        print("  Correlacion de P&L diario (zona %d):" % zona)
        for (na, a), (nb, b) in ((("KE", ke), ("ZW", zw)), (("KE", ke), ("Oro", gc)),
                                 (("ZW", zw), ("Oro", gc))):
            r, n = correlacion(a["daily"], b["daily"])
            print("      %-4s vs %-4s  r = %s   (%d dias en comun)"
                  % (na, nb, ("%+.3f" % r) if r is not None else "n/d", n))
        print()
    print("  Leer: KE solo agrega si es rentable POR SEPARADO y su correlacion con ZW es baja.")
    print("  Si r(KE,ZW) es alta, es el mismo trade con otro ticker: dobla riesgo sin diversificar.")
    print("=" * 100)


if __name__ == "__main__":
    main()
