# -*- coding: utf-8 -*-
"""BACKTEST del OF v2 PRO sobre HISTORIA REAL de Quantower/Rithmic (14-jul, orden de Juan).
Consume los CSV que exportan los bridges (GET localhost:8766|8767/export?days=N):
  C:\\TradingSignals\\{mgc|mes}_hist_bars.csv    (velas 1-min + delta + cumdelta)
  C:\\TradingSignals\\{mgc|mes}_hist_levels.csv  (footprint: buy/sell por nivel)
Re-ejecuta las señales v2 (divergencia con cumdelta de sesion, absorcion GRADO A con footprint
+ niveles PDH/PDL/VWAP/POC-prev reconstruidos dia a dia) y simula el scalp del reader
(SL/TP/timeout) con velas de 1 minuto. Reporta PF/WR por señal y por variante de umbral.
ESTO convierte el "OF no es backtesteable" en calibracion con historia real.
Uso: python backtest_of_pro.py MES|MGC [dias_a_usar]"""
import csv, sys, os
from datetime import datetime, timedelta
from collections import defaultdict

MERCADO = (sys.argv[1] if len(sys.argv) > 1 else "MES").upper()
CFG = {
    "MGC": dict(bars=r"C:\TradingSignals\mgc_hist_bars.csv", lvls=r"C:\TradingSignals\mgc_hist_levels.csv",
                sl=6.0, tp=9.0, dpp=10.0, max_min=25, tol=1.5, costo=3.5),
    "MES": dict(bars=r"C:\TradingSignals\mes_hist_bars.csv", lvls=r"C:\TradingSignals\mes_hist_levels.csv",
                sl=2.5, tp=5.0, dpp=5.0, max_min=20, tol=2.0, costo=3.5),
}[MERCADO]
SESS_H, SESS_M = 13, 30       # reset sesion NY en UTC (verano)
LOOKBACK = 5

def cargar():
    bars = []
    with open(CFG["bars"], encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            bars.append(dict(t=datetime.strptime(r["time_utc"], "%Y-%m-%d %H:%M:%S"),
                             o=float(r["open"]), h=float(r["high"]), l=float(r["low"]), c=float(r["close"]),
                             vol=float(r["volume"]), delta=float(r["delta"])))
    lvls = defaultdict(list)   # time -> [(price, buy, sell)]
    with open(CFG["lvls"], encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            lvls[r["time_utc"]].append((float(r["price"]), float(r["buy"]), float(r["sell"])))
    bars.sort(key=lambda b: b["t"])   # el export viene nuevo->viejo
    return bars, lvls

def sesion_de(t):
    corte = t.replace(hour=SESS_H, minute=SESS_M, second=0)
    return t.date() if t >= corte else (t - timedelta(days=1)).date()

def perfil_va(profile):
    if not profile: return 0, 0, 0
    total = sum(profile.values())
    orden = sorted(profile.items(), key=lambda kv: -kv[1])
    poc = orden[0][0]; acum = 0; en = []
    for px, v in orden:
        en.append(px); acum += v
        if acum >= 0.70 * total: break
    return poc, max(en), min(en)

def backtest(bars, lvls, abs_ratio=2.0, abs_minvol=0.30, abs_volmult=1.5, div_persist=2,
             usar_div=True, usar_abs=True, filtro_cumdelta=False):
    # estado de sesion (reconstruido sin lookahead)
    ses = None; cum = 0.0; vwap_n = 0.0; vwap_d = 0.0
    profile = {}; poc_p = vah_p = val_p = 0.0
    dia = None; today_h = today_l = None; pdh = pdl = 0.0
    hist = []          # velas de la sesion (para lookbacks)
    div_last, div_streak = "NONE", 0
    pos = None; trades = []
    for i, b in enumerate(bars):
        s = sesion_de(b["t"])
        if s != ses:
            ses = s
            poc_p, vah_p, val_p = perfil_va(profile)
            profile = {}; cum = 0.0; vwap_n = vwap_d = 0.0; hist = []
        d = b["t"].date()
        if d != dia:
            if dia is not None: pdh, pdl = today_h, today_l
            dia = d; today_h, today_l = b["h"], b["l"]
        today_h = max(today_h, b["h"]); today_l = min(today_l, b["l"])
        cum += b["delta"]; b2 = dict(b); b2["cum"] = cum
        vwap_n += (b["h"] + b["l"] + b["c"]) / 3 * b["vol"]; vwap_d += b["vol"]
        vwap = vwap_n / vwap_d if vwap_d else 0
        key = b["t"].strftime("%Y-%m-%d %H:%M:%S")
        for px, bv, sv in lvls.get(key, []):
            profile[px] = profile.get(px, 0) + bv + sv
        hist.append(b2)
        if len(hist) > 60: hist.pop(0)

        px_c = b["c"]
        # ── gestionar posicion (con la vela SIGUIENTE en adelante; aqui la actual) ──
        if pos:
            dirn, e, slv, tpv, t0, tag = pos
            hit_sl = (b["l"] <= slv) if dirn == 1 else (b["h"] >= slv)
            hit_tp = (b["h"] >= tpv) if dirn == 1 else (b["l"] <= tpv)
            mins = (b["t"] - t0).total_seconds() / 60
            if hit_sl:
                trades.append((tag, -CFG["sl"] * CFG["dpp"] - CFG["costo"], b["t"].date())); pos = None
            elif hit_tp:
                trades.append((tag, CFG["tp"] * CFG["dpp"] - CFG["costo"], b["t"].date())); pos = None
            elif mins >= CFG["max_min"]:
                trades.append((tag, (px_c - e) * dirn * CFG["dpp"] - CFG["costo"], b["t"].date())); pos = None
        if pos: continue
        if len(hist) < 12: continue
        # ── señales al cierre de esta vela (entrada al open de la siguiente ≈ close actual) ──
        # divergencia
        sig = None; tag = ""
        prev = hist[-LOOKBACK-1:-1]
        if usar_div and len(prev) >= LOOKBACK:
            ph = max(x["h"] for x in prev); pl = min(x["l"] for x in prev)
            pcm = max(x["cum"] for x in prev); pcn = min(x["cum"] for x in prev)
            dv = "BEARISH" if (b["h"] > ph and b2["cum"] < pcm) else ("BULLISH" if (b["l"] < pl and b2["cum"] > pcn) else "NONE")
            if dv != "NONE" and dv == div_last: div_streak += 1
            elif dv != "NONE": div_streak = 1
            else: div_streak = 0
            div_last = dv
            if div_streak >= div_persist:
                cand = 1 if dv == "BULLISH" else -1
                if not filtro_cumdelta or (cand == 1 and b2["cum"] > 0) or (cand == -1 and b2["cum"] < 0):
                    sig = cand; tag = "div"
        # absorcion grado A (footprint)
        if usar_abs and sig is None:
            rng = b["h"] - b["l"]
            f = lvls.get(key, [])
            if rng > 0 and f:
                avg10 = sum(x["vol"] for x in hist[-11:-1]) / 10
                if b["vol"] > abs_volmult * avg10:
                    third = rng / 3
                    bt = st_ = bb = sb = 0.0
                    for px, bv, sv in f:
                        if px >= b["h"] - third: bt += bv; st_ += sv
                        elif px <= b["l"] + third: bb += bv; sb += sv
                    volTop = bt + st_; volBot = bb + sb
                    mid = (b["h"] + b["l"]) / 2
                    n10h = max(x["h"] for x in hist[-11:-1]); n10l = min(x["l"] for x in hist[-11:-1])
                    tol = CFG["tol"]
                    nivel_alto = any(z > 0 and abs(b["h"] - z) <= tol for z in (pdh, vwap, poc_p, vah_p))
                    nivel_bajo = any(z > 0 and abs(b["l"] - z) <= tol for z in (pdl, vwap, poc_p, val_p))
                    if volTop >= abs_minvol * b["vol"] and bt >= abs_ratio * max(st_, 1) and b["c"] < mid and (nivel_alto or b["h"] >= n10h):
                        sig = -1; tag = "abs"
                    elif volBot >= abs_minvol * b["vol"] and sb >= abs_ratio * max(bb, 1) and b["c"] > mid and (nivel_bajo or b["l"] <= n10l):
                        sig = 1; tag = "abs"
        if sig:
            e = px_c
            pos = (sig, e, e - sig * CFG["sl"], e + sig * CFG["tp"], b["t"], tag)
    return trades

def rep(trades, label):
    if len(trades) < 5:
        print(f"  {label:42} n={len(trades)} insuf."); return
    pl = [p for _, p, _ in trades]
    w = [x for x in pl if x > 0]; l = [x for x in pl if x <= 0]
    pf = sum(w) / abs(sum(l)) if l else 99
    wr = len(w) / len(pl) * 100
    dias = defaultdict(float)
    for _, p, d in trades: dias[d] += p
    bal = peak = mdd = 0.0
    for d in sorted(dias):
        bal += dias[d]; peak = max(peak, bal); mdd = max(mdd, peak - bal)
    peor = min(dias.values()); verdes = sum(1 for v in dias.values() if v > 0)
    por = defaultdict(list)
    for tag, p, _ in trades: por[tag].append(p)
    det = " | ".join(f"{k}:n{len(v)},{'+' if sum(v)>0 else ''}{sum(v):.0f}$" for k, v in por.items())
    print(f"  {label:38} n={len(pl):>4} win={wr:>3.0f}% PF={pf:.2f} tot=${sum(pl):+7.0f} | maxDD ${mdd:.0f} peorDia ${peor:+.0f} verdes {verdes}/{len(dias)}  [{det}]")

def main():
    if not os.path.exists(CFG["bars"]):
        print(f"[X] Falta {CFG['bars']} — primero: curl localhost:{8767 if MERCADO=='MES' else 8766}/export?days=30"); return
    bars, lvls = cargar()
    print(f"{MERCADO}: {len(bars)} velas 1-min | {sum(len(v) for v in lvls.values())} niveles footprint")
    print(f"scalp: SL {CFG['sl']} / TP {CFG['tp']} / timeout {CFG['max_min']}m\n")
    rep(backtest(bars, lvls), "BASE (config actual del reader)")
    rep(backtest(bars, lvls, filtro_cumdelta=True), "+ filtro cumdelta (div a favor sesion)")
    rep(backtest(bars, lvls, usar_div=False), "solo ABSORCION grado A")
    rep(backtest(bars, lvls, usar_abs=False), "solo DIVERGENCIA")
    rep(backtest(bars, lvls, div_persist=3), "div persistencia 3")
    rep(backtest(bars, lvls, abs_ratio=1.5, abs_minvol=0.25), "absorcion mas laxa (1.5x/25%)")
    print("\n  (variantes de SL/TP: editar CFG y re-correr — la data ya esta local)")

if __name__ == "__main__":
    main()
