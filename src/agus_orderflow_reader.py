# -*- coding: utf-8 -*-
"""agus_orderflow_reader.py — LECTOR SILENCIOSO del carril order flow (9-jul, Juan).
Lee las señales del bridge AgustinaOrderFlow (localhost:8766/signal), las SIMULA en paper
(1 trade a la vez, SL/TP fijos) y reporta a Discord solo los EVENTOS (abre / cierra), no
cada minuto. NO opera real — es forward test para ver si el order flow tiene edge antes de
arriesgar un peso. Corre cada 1 min por tarea de Windows en la ventana NY.

Combina las 3 señales por voto: divergencia/absorcion/imbalance -> BUY/SELL/NONE.
Registra TODO en orderflow_signals_log.csv + estado en orderflow_paper_state.json.

SIMULACION REALISTA desde el 21-jul (pedido de Juan: "que el paper sea lo mismo que en live").
Antes el paper era OPTIMISTA por 3 motivos y por eso mostraba mas de lo alcanzable:
  1. Entraba al ULTIMO OPERADO; el ejecutor cruza el spread (vende al bid / compra al ask).
  2. Buscaba el stop contra UNA FOTO por minuto; el bracket real dispara con cualquier tick
     -> no veia los pinchazos intra-minuto (el 21-jul uno invisible costo $80 en vivo).
  3. No pagaba comisiones.
Ahora: entrada y salida cruzando el spread, SL/TP contra el RANGO de la vela (bar_high/bar_low
del bridge), SL con prioridad sobre TP si la vela toco ambos (peor caso), y COSTO por trade.
=> El P&L del paper pasa a ser comparable con la cuenta real. OJO: el historico ANTERIOR al
21-jul no es comparable con el nuevo (31 trades/+$765 eran con el modelo optimista).
"""
import json, os, sys, csv, urllib.request
from datetime import datetime

HERE   = os.path.dirname(os.path.abspath(__file__))
# Mercado por argumento: python agus_orderflow_reader.py [MGC|MES]  (default MGC)
MERCADO = (sys.argv[1] if len(sys.argv) > 1 else "MGC").upper()
# HORIZONTE (10 jul): la academia (OFI, arXiv/Quant Finance) muestra que el edge del order
# flow es significativo hasta "varios minutos" y decae rapido. La config vieja (SL/TP 20pts en
# MGC) daba trades de HORAS -> operaba FUERA de la ventana del edge (capturaba ruido). Ahora:
# SL/TP de scalp + SALIDA POR TIEMPO (max_min). Coincide con la estrategia scalp de DeepSeek.
_CFG = {
    "MGC": dict(url="http://localhost:8766/signal", sl=6.0, tp=9.0, dpp=10.0, max_min=25, solo=("div",),  # backtest 30d: SOLO div PF 1.15
                costo=2.60,   # comision round-trip MEDIDA en vivo (SL real -62.60 vs -60 teorico)
                state="orderflow_paper_state.json", log="orderflow_signals_log.csv", canal="OF-MGC"),
    "MES": dict(url="http://localhost:8767/signal", sl=2.5, tp=5.0, dpp=5.0,  max_min=20, solo=(),        # MES: muerto con costos (PF<0.7)
                costo=2.60,
                state="orderflow_mes_state.json",   log="orderflow_mes_log.csv",     canal="OF-MES"),
}.get(MERCADO)
if _CFG is None:
    print(f"mercado desconocido: {MERCADO} (usa MGC o MES)"); sys.exit(0)
SIGNAL_URL = _CFG["url"]
STATE  = os.path.join(HERE, _CFG["state"])
LOG    = os.path.join(HERE, _CFG["log"])
SL_PTS = _CFG["sl"]; TP_PTS = _CFG["tp"]; DPP = _CFG["dpp"]; CANAL = _CFG["canal"]
MAX_MIN = _CFG["max_min"]   # si no resolvio en X min, el edge ya se evaporo -> salir a mercado
SOLO = _CFG.get("solo", ("div","abs","imb"))   # señales habilitadas (backtest 30d 14-jul)
COSTO = _CFG.get("costo", 2.60)                # comision round-trip (21-jul: simulacion REALISTA)
VENT_INI, VENT_FIN = 2, 11                     # 22-jul "MANAS": ventana LONDRES (COT)
# ── ETIQUETA DE EXPANSION (23-jul, backtest_of_expansion.py) ─────────────────────────
# El OF predice CUANDO viene un movimiento (magnitud, NO direccion): cumdelta-momentum
# |CUM[i]-CUM[i-5]| > 150 sube P(mov>=9pts en 25min) de 44% a 60% (+38%). NO se filtra en
# vivo (n=33 muy fino; EXP_MIN=0 en el ejecutor) -> aca solo ETIQUETA cada trade y lleva
# stats separadas exp-vs-calma para comparar en 2-3 sem de forward. El win% NO cambia con la
# expansion (predice magnitud, no lado); lo que deberia moverse es el $/trade y el maxDD.
EXP_THRESH = 150.0

# Discord (degrada solo si falla)
sys.path.insert(0, HERE)
try:
    from agus_discord import enviar_texto
except Exception:
    def enviar_texto(msg, mercado=CANAL): print(f"[discord-off] {msg}")

# ── Ventana NY: fuera de horario no simula (solo el bridge sigue juntando data) ──
def en_ventana():
    # 22-jul "MANAS": LONDRES 02-11 COT. El backtest por ventana (data UTC = COT+5) mostro
    # que el edge vive en Londres (PF 1.21 IS / 1.25 OOS) y muere en NY (0.78 / 0.87).
    # El control en paper acompaña al ejecutor en la MISMA ventana para seguir comparable.
    h = datetime.now().hour
    return VENT_INI <= h < VENT_FIN

def get_signal():
    req = urllib.request.Request(SIGNAL_URL, headers={"User-Agent": "AgusOF/1.0"})
    return json.loads(urllib.request.urlopen(req, timeout=5).read().decode())

def voto(sig, div_ok, imb_ok):
    # v2 (9-jul, calibracion tras 1er dia): divergencia solo si PERSISTE (div_ok, racha>=2)
    # -> filtra el ruido de 75/dia alternando. Imbalance solo 1 bala/dia (imb_ok) -> no pegado
    # 445x. Absorcion siempre (rara, se porto bien: 3/dia). Fix definitivo ira al bridge C#.
    d = sig["signals"]; v = 0; activas = []
    if "div" in SOLO and div_ok and d["divergence"] == "BULLISH": v += 1; activas.append("div+")
    elif "div" in SOLO and div_ok and d["divergence"] == "BEARISH": v -= 1; activas.append("div-")
    if "abs" in SOLO and d["absorption"] == "BUY": v += 1; activas.append("abs+")
    elif "abs" in SOLO and d["absorption"] == "SELL": v -= 1; activas.append("abs-")
    if "imb" in SOLO and imb_ok and d["imbalance"] == "BUY": v += 1; activas.append("imb+")
    elif "imb" in SOLO and imb_ok and d["imbalance"] == "SELL": v -= 1; activas.append("imb-")
    direc = "BUY" if v >= 1 else ("SELL" if v <= -1 else "NONE")
    return direc, abs(v), activas

def load_state():
    try:
        with open(STATE, encoding="utf-8") as f: return json.load(f)
    except Exception:
        return {"open": None, "stats": {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0},
                "imb_day": "", "div_last": "NONE", "div_streak": 0}

def save_state(s):
    with open(STATE, "w", encoding="utf-8") as f: json.dump(s, f, indent=2)

def log_row(ts, price, sig, direc, conf, evento):
    nuevo = not os.path.exists(LOG)
    with open(LOG, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if nuevo: w.writerow(["timestamp","price","divergence","absorption","imbalance","cum_delta","direccion","confluencia","evento"])
        d = sig["signals"]
        w.writerow([ts, price, d["divergence"], d["absorption"], d["imbalance"],
                    sig.get("cumulative_delta",""), direc, conf, evento])

def main():
    if not en_ventana():
        return
    try:
        sig = get_signal()
    except Exception as e:
        return   # bridge apagado (Quantower cerrado) — no rompe
    price = float(sig["price"])          # ultimo operado (referencia y log)
    # ── SIMULACION REALISTA (21-jul) ──────────────────────────────────────────────
    # Antes: entraba al "ultimo operado" y buscaba el stop contra UNA FOTO por minuto.
    # Resultado: no veia los pinchazos intra-minuto y sobrestimaba (el 21-jul un pinchazo
    # invisible para el paper costo $80 reales). Ahora replica al ejecutor: cruza el spread
    # (vende al bid / compra al ask) y detecta SL/TP contra el RANGO de la vela, como un
    # bracket real. Si el bridge es viejo (sin estos campos) cae al comportamiento anterior.
    bid = float(sig.get("bid") or 0) or price
    ask = float(sig.get("ask") or 0) or price
    bhi = float(sig.get("bar_high") or 0) or price
    blo = float(sig.get("bar_low") or 0) or price
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hoy = datetime.now().strftime("%Y-%m-%d")
    st = load_state()
    # divergencia: racha de persistencia (filtra el ruido alternante de 75/dia)
    dv = sig["signals"]["divergence"]
    if dv != "NONE" and dv == st.get("div_last"): st["div_streak"] = st.get("div_streak", 0) + 1
    elif dv != "NONE":                            st["div_streak"] = 1
    else:                                         st["div_streak"] = 0
    st["div_last"] = dv
    # cumdelta-momentum (etiqueta de expansion): |cumdelta ahora - hace 5 ciclos|, historia
    # rolling de 6 (=5 min a 1 ciclo/min). MISMA logica que el ejecutor (of_mgc cd_hist).
    _cd = float(sig.get("cumulative_delta") or 0)
    _h = (st.get("cd_hist") or []) + [_cd]; _h = _h[-6:]; st["cd_hist"] = _h
    exp_mom = abs(_h[-1] - _h[0]) if len(_h) >= 6 else 0.0
    div_ok = st["div_streak"] >= 2             # divergencia confirmada (2 corridas mismo lado)
    imb_ok = st.get("imb_day", "") != hoy      # imbalance: 1 sola bala por dia
    direc, conf, activas = voto(sig, div_ok, imb_ok)
    evento = "-"

    # 1) gestionar trade abierto
    if st["open"]:
        o = st["open"]; d = 1 if o["dir"] == "BUY" else -1
        # MAE con el EXTREMO ADVERSO real de la vela (no con la foto): long sufre en el low,
        # short en el high. Asi el MAE sirve de verdad para calibrar el stop por percentiles.
        _adv = round((o["entry"] - (blo if d == 1 else bhi)) * d, 2)
        if _adv > o.get("mae", 0): o["mae"] = _adv
        # deteccion tipo BRACKET: el rango de la vela toca el nivel (no el cierre muestreado)
        hit_sl = (blo <= o["sl"]) if d == 1 else (bhi >= o["sl"])
        hit_tp = (bhi >= o["tp"]) if d == 1 else (blo <= o["tp"])
        # salida por TIEMPO: pasado max_min el edge del OF ya decayo -> cerrar a mercado
        try:
            mins = (datetime.now() - datetime.strptime(o["opened"], "%Y-%m-%d %H:%M:%S")).total_seconds() / 60.0
        except Exception:
            mins = 0.0
        # cierre al final de la ventana: nada queda abierto (los congelados del 13-jul costaron ~$72)
        _n = datetime.now()
        hit_time = (mins >= MAX_MIN
                    or (_n.hour == VENT_FIN - 1 and _n.minute >= 55) or _n.hour >= VENT_FIN)
        if hit_sl or hit_tp or hit_time:
            # SL con PRIORIDAD sobre TP: si la vela toco ambos no sabemos el orden -> asumimos
            # el peor caso (antes se asumia TP, que inflaba el resultado). Costos siempre.
            if hit_sl:   pnl = -SL_PTS * DPP - COSTO; res = "SL"
            elif hit_tp: pnl = TP_PTS * DPP - COSTO;  res = "TP"
            else:
                _exit = bid if d == 1 else ask   # cierra cruzando el spread, como el ejecutor
                pnl = (_exit - o["entry"]) * d * DPP - COSTO; res = f"TIME({mins:.0f}m)"
            st["stats"]["trades"] += 1
            st["stats"]["wins" if pnl > 0 else "losses"] += 1
            st["stats"]["pnl"] = round(st["stats"]["pnl"] + pnl, 1)
            # split expansion-vs-calma por el cumdelta_mom de LA ENTRADA (etiqueta, no filtro)
            _em = o.get("exp_mom", 0.0)
            _tag = "exp" if _em >= EXP_THRESH else "calma"
            _ss = st.setdefault("stats_" + _tag, {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0})
            _ss["trades"] += 1
            _ss["wins" if pnl > 0 else "losses"] += 1
            _ss["pnl"] = round(_ss["pnl"] + pnl, 1)
            evento = f"CIERRE {res} mae={o.get('mae',0)} mom={_em:.0f}"
            s = st["stats"]
            wr = s["wins"] / s["trades"] * 100 if s["trades"] else 0
            _pe = st.get("stats_exp", {}).get("pnl", 0.0); _pc = st.get("stats_calma", {}).get("pnl", 0.0)
            enviar_texto(
                f"📊 **OF paper — {o['dir']} cerrado en {res}** ({pnl:+.0f}$)\n"
                f"entrada {o['entry']} → {price} | señales: {', '.join(o.get('activas',[]))}\n"
                f"acumulado: {s['trades']} trades, {wr:.0f}% WR, P&L {s['pnl']:+.0f}$ (paper) | "
                f"[{_tag} mom={_em:.0f}] exp {_pe:+.0f}$ / calma {_pc:+.0f}$",
                mercado=CANAL)
            st["open"] = None

    # 2) abrir si hay señal y no hay trade
    if not st["open"] and direc != "NONE":
        d = 1 if direc == "BUY" else -1
        _ent = ask if direc == "BUY" else bid   # cruza el spread para llenar, igual que el live
        o = {"dir": direc, "entry": _ent, "opened": ts, "activas": activas,
             "sl": round(_ent - d*SL_PTS, 2), "tp": round(_ent + d*TP_PTS, 2),
             "exp_mom": round(exp_mom, 0)}   # etiqueta de expansion al momento de la entrada
        st["open"] = o; evento = f"ABRE {direc} mom={exp_mom:.0f}"
        if "imb+" in activas or "imb-" in activas: st["imb_day"] = hoy  # gasta la bala del imbalance
        enviar_texto(
            f"🎯 **OF paper — abre {direc}** @ {o['entry']} (confluencia {conf}: {', '.join(activas)})\n"
            f"SL {o['sl']} | TP {o['tp']} | forward test, NO real", mercado=CANAL)

    log_row(ts, price, sig, direc, conf, evento)
    save_state(st)

if __name__ == "__main__":
    main()
