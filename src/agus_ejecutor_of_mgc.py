# -*- coding: utf-8 -*-
"""agus_ejecutor_of_mgc.py — EJECUTOR "MANAS" (bautizada por Juan 22-jul):
OF-MGC solo-divergencia en VENTANA LONDRES (02-11 COT) -> eval Lucid $25k.

SEÑAL: bridge OF 8766 (/signal), SOLO divergencia con racha >= 2 — config VALIDADA:
backtest 30d Rithmic CON costos = PF 1.15, +$1,749/mes, maxDD $646 (backtest_of_pro.py);
forward paper (agus_orderflow_reader) corre en paralelo como control. NO tocar umbrales.
EJECUCION (v2, 20-jul tras dia 1 live): bridge AgustinaBridge 8765 via place_order — entrada
ahora a MARKET/IOC (el bridge cambio de Limit->Market: la limite no cruzaba y llenaba tarde ->
MISSED/huerfano). Brackets SL/TP server-side; close_partial para el timeout. La CONTABILIDAD
es por DELTA DE BALANCE REAL (get_balance del 8765), NO por precio de señal — incluye costos y
fill real (el dia 1 el ejecutor conto +$80 vs cuenta real +$163). Guardrails leen balance real.
Scalp CONGELADO: SL 6 / TP 9 pts / timeout 25 min / 1 MGC / 1 trade a la vez / ventana 7-16 COT.

DOS MANOS (regla de la casa): existe OF_LIVE_MGC.txt -> ordenes REALES en Lucid.
Sin flag -> DRY-RUN (simula con el precio del 8766, mismas reglas, loguea que HARIA).
EL ASISTENTE NUNCA CREA EL FLAG — ese click es solo de Juan.

GUARDRAILS (cada corrida, ANTES de abrir):
  - MLL: start_balance + P&L del dia <= piso trailing + $100 -> MUERTE (flatten, dead=true,
    no opera mas; revivir = editar el state a mano). Piso 24,141 = peak EOD ~25,141 - $1,000
    (aire ~$822 al 6-jul). CONFIRMADO por Juan contra el dashboard de Lucid (16-jul).
  - freno diario -$300 (sugerencia del backtest = 5 SL) -> no abre mas hoy.
  - techo consistencia: si el dia ya va en +$510 no abre mas (Flex: mejor dia <= $625 al pasar;
    $510 + TP $90 = $600 tope) — regla de la CUENTA, no tuneo del edge.
  - calendario FF (16-jul): evento HIGH USD -> no abrir desde -40min hasta +15min del evento
    (scalp de 25min: ninguna posicion viva en el spike). Cache 6h en of_calendar_cache.json;
    API caida -> degrada a operar. OJO: parser PROPIO (country/date ISO) — el get_news_context
    de la casa lee currency/time que YA NO EXISTEN en el JSON de FF (nunca bloqueaba).
  - conflicto de carril: si existe LIVE_MGC.txt (Ciel VIVO) no ejecuta real — 1 carril por cuenta.
  - posicion ajena en la cuenta (keepalive/manual) -> no abre.
La gestion del trade abierto (SL/TP/timeout) corre TAMBIEN fuera de ventana.
Corre cada 1 min (tarea "Agus OF MGC ejecutor"). Log solo EVENTOS: of_exec_log.csv.
Estado: of_exec_state.json. Discord canal OF-MGC (prefijo 🔴 LIVE / 🧪 DRY).
"""
import json, os, sys, csv, urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from quantower_bridge import QuantowerBridge

SIGNAL_URL = "http://localhost:8766/signal"
FLAG_OF    = os.path.join(HERE, "OF_LIVE_MGC.txt")
FLAG_CIEL  = os.path.join(HERE, "LIVE_MGC.txt")
STATE      = os.path.join(HERE, "of_exec_state.json")
LOG        = os.path.join(HERE, "of_exec_log.csv")
BAL        = os.path.join(HERE, "daily_balance.json")

SL_PTS, TP_PTS, MAX_MIN = 6.0, 9.0, 25
DPP, CONTRACTS = 10.0, 1
DAILY_STOP  = 300.0     # freno diario (se compara contra -DAILY_STOP)
CONSIST_CAP = 600.0     # tope del dia: no abrir si day_pnl + TP > este numero
MLL_FLOOR   = 24141.0   # piso trailing EOD — CONFIRMADO por Juan contra dashboard Lucid (16-jul)
MLL_BUFFER  = 100.0
EXP_MIN     = 0.0     # FILTRO DE EXPANSION: DESACTIVADO (24-jul). Se puso el 23-jul por un
                      # hallazgo (+$4.1/trade) que NO aguanto un test mejor. Barrido de umbrales
                      # con el motor correcto (+freno): SIN filtro = PF 1.15, +$805, maxDD 349,
                      # 10 trades/dia; >=150 = PF 1.08, +$110, maxDD 531, 1.9/dia; >=100 = PF 0.95
                      # (NEGATIVO). Los numeros del filtro saltan sin patron = ruido de muestra
                      # chica. Y el maxDD SUBE al filtrar: menos trades = cada perdida pesa mas.
                      # LECCION: la FRECUENCIA es la que da la recuperacion (idea de Juan "que
                      # pierda pero recupere") — muchos trades chicos diluyen el dia malo.
                      # Caí en la trampa de comparaciones multiples que yo mismo advertia.
                      # Se deja el calculo de exp_mom porque se LOGUEA en cada ABRE (data p/futuro).
CANAL = "MANAS"   # 22-jul: Juan bautizo asi a la estrategia OF-divergencia en ventana Londres

try:
    from agus_discord import enviar_texto
except Exception:
    def enviar_texto(msg, mercado=CANAL): print(f"[discord-off] {msg}")

# ── VENTANA "MANAS" (22-jul): LONDRES 02-11 COT ──────────────────────────────────
# CAUSA RAIZ de los 3 dias en rojo: el veredicto GO se calculo con el backtest operando
# las 24h, pero el ejecutor estaba limitado a 07-16 COT. Al medir POR VENTANA (ojo: la
# data del bridge viene en UTC = COT+5) resulto que el edge vive en LONDRES y muere en NY:
#     02-11 COT -> PF 1.21 IS / 1.25 OOS (+$296 fuera de muestra, incluye la semana mala)
#     07-16 COT -> PF 0.78 IS / 0.87 OOS  <- la que se estaba operando
#     09-18 COT -> PF 0.71 IS / 0.57 OOS  <- lo peor
# Robustez al spread (Londres): aguanta hasta 3 ticks (PF 1.05 OOS), MUERE en 4 (0.99).
# => el spread real de madrugada es la variable a vigilar antes de armar con plata.
VENT_INI, VENT_FIN = 2, 11

def en_ventana():
    return VENT_INI <= datetime.now().hour < VENT_FIN

def get_signal():
    req = urllib.request.Request(SIGNAL_URL, headers={"User-Agent": "AgusOFExec/1.0"})
    return json.loads(urllib.request.urlopen(req, timeout=5).read().decode())

ACCOUNT_URL = "http://localhost:8765/account"
def get_balance():
    """Balance REAL de la cuenta Lucid (fuente de verdad para P&L y guardrails). None si falla."""
    try:
        req = urllib.request.Request(ACCOUNT_URL, headers={"User-Agent": "AgusOFExec/1.0"})
        d = json.loads(urllib.request.urlopen(req, timeout=5).read().decode())
        b = d.get("balance")
        return float(b) if b is not None else None
    except Exception:
        return None

CAL_CACHE = os.path.join(HERE, "of_calendar_cache.json")
CAL_URL   = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CAL_PRE_MIN, CAL_POST_MIN = 40, 15   # scalp 25min: bloquear abrir 40min antes / 15min despues

def eventos_hoy():
    """Eventos HIGH USD de hoy en hora LOCAL, cache 6h. Formato FF real: title/country/date
    ISO con offset (currency/time ya no existen — el helper viejo de la casa nunca bloqueaba)."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(CAL_CACHE, encoding="utf-8") as f: c = json.load(f)
        age = (datetime.now() - datetime.strptime(c["fetched"], "%Y-%m-%d %H:%M")).total_seconds()
        if c.get("date") == hoy and age < c.get("ttl_min", 360) * 60:
            return c["events"]
    except Exception:
        pass
    events = []; ok = False
    try:
        req = urllib.request.Request(CAL_URL, headers={"User-Agent": "AgusOFExec/1.0"})
        data = json.loads(urllib.request.urlopen(req, timeout=8).read().decode())
        for e in data:
            if e.get("impact") != "High" or e.get("country") != "USD":
                continue
            try:
                loc = datetime.fromisoformat(e.get("date", "")).astimezone()
            except Exception:
                continue
            if loc.strftime("%Y-%m-%d") == hoy:
                events.append([loc.strftime("%H:%M"), e.get("title", "")])
        ok = True
    except Exception:
        events = []   # API caida/429 -> degrada a operar, pero reintenta en 30min (no 6h ciego)
    try:
        with open(CAL_CACHE, "w", encoding="utf-8") as f:
            json.dump({"date": hoy, "fetched": datetime.now().strftime("%Y-%m-%d %H:%M"),
                       "events": events, "ttl_min": 360 if ok else 30}, f)
    except Exception:
        pass
    return events

def evento_cerca():
    now = datetime.now()
    for et, title in eventos_hoy():
        try:
            ev = datetime.strptime(f"{now.strftime('%Y-%m-%d')} {et}", "%Y-%m-%d %H:%M")
        except Exception:
            continue
        diff = (ev - now).total_seconds() / 60
        if -CAL_POST_MIN <= diff <= CAL_PRE_MIN:
            return f"{title} {et}"
    return None

def load_state():
    try:
        with open(STATE, encoding="utf-8") as f: return json.load(f)
    except Exception:
        return {"open": None, "dead": False, "day": "", "day_pnl": 0.0, "blocked": "",
                "div_last": "NONE", "div_streak": 0,
                "stats": {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0}}

def save_state(s):
    with open(STATE, "w", encoding="utf-8") as f: json.dump(s, f, indent=2)

def log_ev(ts, modo, evento, precio, detalle):
    nuevo = not os.path.exists(LOG)
    with open(LOG, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if nuevo: w.writerow(["timestamp", "modo", "evento", "precio", "detalle"])
        w.writerow([ts, modo, evento, precio, detalle])

def start_balance():
    try:
        with open(BAL, encoding="utf-8") as f: return float(json.load(f)["start_balance"])
    except Exception:
        return None

def _book(st, o, res, pnl, price, ts, modo, live, src):
    """Contabiliza un cierre: stats de por-vida + log + Discord. day_pnl SOLO en DRY
    (en LIVE se recalcula desde el balance real en main). Deja st['open']=None."""
    pnl = round(pnl, 2)
    st["open"] = None
    s = st["stats"]; s["trades"] += 1
    s["wins" if pnl > 0 else "losses"] += 1
    s["pnl"] = round(s["pnl"] + pnl, 2)
    if not live:
        st["day_pnl"] = round(st["day_pnl"] + pnl, 2)
    wr = s["wins"] / s["trades"] * 100 if s["trades"] else 0
    emoji = "🔴" if live else "🧪"
    log_ev(ts, modo, f"CIERRE {res}", price, f"{o['dir']} entry {o['entry']} pnl {pnl:+.2f} ({src})")
    enviar_texto(f"{emoji} **{modo} OF-exec — {o['dir']} cerrado en {res}** ({pnl:+.0f}$ {src})\n"
                 f"entrada {o['entry']} → {price} | dia {st['day_pnl']:+.0f}$ | "
                 f"total {s['trades']}t {wr:.0f}%WR {s['pnl']:+.0f}$", mercado=CANAL)

def gestionar_abierto(st, price, br, live, ts, modo):
    """Gestiona el trade abierto.
    DRY: simulacion identica al paper reader (baseline de comparacion) — NO cambia.
    LIVE: reconcilia contra la posicion REAL y contabiliza por DELTA DE BALANCE (incluye
    costos y fill real) — NO infiere P&L del precio de señal. Mata el bug 20-jul de
    'MISSED que en realidad llenaron' (ejecutor +$80 vs cuenta real +$163)."""
    o = st["open"]; d = 1 if o["dir"] == "BUY" else -1
    try:
        mins = (datetime.now() - datetime.strptime(o["opened"], "%Y-%m-%d %H:%M:%S")).total_seconds() / 60.0
    except Exception:
        mins = 0.0

    # ── DRY: simulacion (baseline) ──
    if not live:
        hit_sl = (price <= o["sl"]) if d == 1 else (price >= o["sl"])
        hit_tp = (price >= o["tp"]) if d == 1 else (price <= o["tp"])
        if not (hit_sl or hit_tp or mins >= MAX_MIN): return
        if hit_tp:   res, pnl = "TP", TP_PTS * DPP * CONTRACTS
        elif hit_sl: res, pnl = "SL", -SL_PTS * DPP * CONTRACTS
        else:        res, pnl = f"TIME({mins:.0f}m)", (price - o["entry"]) * d * DPP * CONTRACTS
        _book(st, o, res, pnl, price, ts, modo, live, "sim")
        return

    # ── LIVE: fuente de verdad = posicion real + balance real ──
    pos = br.get_positions()
    if pos.get("error"):
        # fix 21-jul (flap 13:03): el cliente devuelve open_positions=0 TAMBIEN cuando la
        # lectura FALLA (reconexion Rithmic). "No se" != "plano": no contabilizar ni limpiar
        # nada con datos ciegos — saltar el ciclo y reintentar al proximo minuto.
        log_ev(ts, modo, "POS_ILEGIBLE", price, str(pos.get("error"))[:80])
        return
    nopen = pos.get("open_positions", 0)
    bal   = get_balance()
    if nopen > 0:
        # posicion viva: los brackets (SL/TP) la gestionan server-side; solo forzamos el timeout
        if mins >= MAX_MIN:
            if not o.get("timed_out"):
                br.close_partial(CONTRACTS, "OF timeout 25min")
                o["timed_out"] = True   # se contabiliza el proximo ciclo (nopen==0 + balance movido)
            elif mins >= MAX_MIN + 5:
                # defensa en profundidad: sigue ABIERTA 5min+ tras el cierre por timeout ->
                # reintentar + alertar (nunca deberia pasar con el fix del bridge; por si acaso,
                # p.ej. una posicion inversa) — NO retorno silencioso (evita el deadlock).
                br.close_partial(CONTRACTS, "OF timeout RETRY")
                if not o.get("retry_warned"):
                    o["retry_warned"] = True
                    enviar_texto(f"⚠️ {modo} OF-exec — posicion sigue ABIERTA {mins:.0f}min tras el "
                                 f"cierre por timeout. Reintentando + REVISAR Quantower (posible inversa).",
                                 mercado=CANAL)
        return
    # nopen == 0: la posicion se cerro (bracket o timeout) O la entrada nunca lleno
    bp = o.get("bal_placed")
    if bal is None:
        # no puedo leer balance: NO declarar no-fill a ciegas (podria ser un trade real cerrado)
        o["balfail"] = o.get("balfail", 0) + 1
        if o["balfail"] >= 5:
            est = (price - o["entry"]) * d * DPP * CONTRACTS   # fallback por precio, marcado
            _book(st, o, "CERRADO?", est, price, ts, modo, live, "est-sin-balance")
            enviar_texto(f"⚠️ {modo} OF-exec — cierre contabilizado por ESTIMADO ({est:+.0f}$): "
                         f"el bridge no dio balance 5 ciclos. VERIFICAR la cuenta a mano.", mercado=CANAL)
        return
    if bp is not None and abs(bal - bp) > 0.005:
        # el balance se movio => la entrada LLENO y ya cerro: P&L REAL = delta de balance
        pnl = bal - bp
        res = f"TIME({mins:.0f}m)" if o.get("timed_out") else ("TP" if pnl >= 0 else "SL")
        _book(st, o, res, pnl, price, ts, modo, live, "real")
        return
    # balance legible y SIN cambio => la entrada aun no lleno
    o["tries"] = o.get("tries", 0) + 1
    if o["tries"] >= 3:
        # market/IOC NO deja orden en reposo -> no hay huerfano que cancelar. Limpiar.
        st["open"] = None
        log_ev(ts, modo, "NO_FILL", price, f"{o['dir']} market IOC no lleno (sin cambio de balance) — limpio")
        enviar_texto(f"⚠️ {modo} OF-exec — {o['dir']} @ {o['entry']} no lleno (market IOC). "
                     f"Estado limpio, sin huerfano.", mercado=CANAL)
    return

def main():
    st = load_state()
    if st.get("dead"):
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S"); hoy = ts[:10]
    if st.get("day") != hoy:
        st["day"] = hoy; st["day_pnl"] = 0.0; st["blocked"] = ""; st["day_start_bal"] = None
    live = os.path.exists(FLAG_OF)
    modo = "LIVE" if live else "DRY"
    br = QuantowerBridge()   # 8765

    # precio: DRY usa el del 8766 (comparable con el paper); LIVE prefiere mid real del 8765
    try:
        sig = get_signal()
    except Exception:
        sig = None
    price = float(sig["price"]) if sig else None
    if live:
        b, a = br.get_current_price()
        if b and a: price = round((b + a) / 2, 1)
    if price is None:
        return   # sin bridges no hay nada que hacer

    # racha de divergencia (misma logica del paper reader)
    dv = "NONE"
    if sig:
        dv = sig["signals"]["divergence"]
        if dv != "NONE" and dv == st.get("div_last"): st["div_streak"] = st.get("div_streak", 0) + 1
        elif dv != "NONE":                            st["div_streak"] = 1
        else:                                         st["div_streak"] = 0
        st["div_last"] = dv

    # cumdelta-momentum para el filtro de expansion: |cumdelta ahora - cumdelta hace 5 ciclos|
    exp_mom = 0.0
    if sig:
        cd = float(sig.get("cumulative_delta") or 0)
        h = (st.get("cd_hist") or []) + [cd]; h = h[-6:]; st["cd_hist"] = h
        if len(h) >= 6: exp_mom = abs(h[-1] - h[0])

    # 1) gestionar abierto (tambien fuera de ventana)
    if st["open"]:
        gestionar_abierto(st, price, br, live, ts, modo)

    # 1b) LIVE: day_pnl y balance REALES (fuente de verdad = cuenta, no acumulacion)
    bal_now = get_balance() if live else None
    if live and bal_now is not None:
        if st.get("day_start_bal") is None:
            st["day_start_bal"] = bal_now
        st["day_pnl"] = round(bal_now - st["day_start_bal"], 2)

    # 2) MLL — muerte del eval (guardrail duro). LIVE = balance REAL; DRY = estimado.
    #    El buffer $100 > perdida abierta maxima (1 micro x SL 6pts = $60), asi que el balance
    #    realizado + buffer nunca dispara tarde aunque haya una posicion abierta.
    if live:
        mll_bal = bal_now
    else:
        sb = start_balance(); mll_bal = (sb + st["day_pnl"]) if sb is not None else None
    if mll_bal is not None and mll_bal <= MLL_FLOOR + MLL_BUFFER:
        st["dead"] = True
        if live and br.get_positions().get("open_positions", 0) > 0:
            br.close_partial(CONTRACTS, "MLL guard")
        log_ev(ts, modo, "MLL_KILL", price, f"balance {mll_bal:.0f} <= piso {MLL_FLOOR + MLL_BUFFER:.0f}")
        enviar_texto(f"🚨 **OF-exec MUERTO por MLL guard** — balance {mll_bal:.0f} en el piso. "
                     f"No opera mas (dead=true).", mercado=CANAL)
        save_state(st); return

    # 3) frenos del dia (solo avisa en la transicion)
    if not st["blocked"]:
        if st["day_pnl"] <= -DAILY_STOP:
            st["blocked"] = "freno diario"
            log_ev(ts, modo, "FRENO_DIARIO", price, f"dia {st['day_pnl']:+.0f}")
            enviar_texto(f"🛑 {modo} OF-exec — freno diario ({st['day_pnl']:+.0f}$ <= -{DAILY_STOP:.0f}). "
                         f"No abre mas hoy.", mercado=CANAL)
        elif st["day_pnl"] + TP_PTS * DPP * CONTRACTS > CONSIST_CAP:
            st["blocked"] = "consistencia"
            log_ev(ts, modo, "TECHO_CONSISTENCIA", price, f"dia {st['day_pnl']:+.0f}")
            enviar_texto(f"🧢 {modo} OF-exec — techo de consistencia ({st['day_pnl']:+.0f}$, "
                         f"mejor dia <= $625 del Flex). No abre mas hoy.", mercado=CANAL)

    # 4) abrir
    if (st["open"] is None and not st["blocked"] and en_ventana()
            and sig and st["div_streak"] >= 2 and dv in ("BULLISH", "BEARISH")):
        direc = "BUY" if dv == "BULLISH" else "SELL"
        d = 1 if direc == "BUY" else -1
        # FILTRO DE EXPANSION: la divergencia paso, pero si no viene movimiento (mom bajo),
        # es un "rato muerto" -> no operar. Es el 85% de trades que en backtest daban PF 1.01.
        if EXP_MIN > 0 and exp_mom < EXP_MIN:
            if st.get("last_calma") != ts[:16]:
                log_ev(ts, modo, "SKIP_CALMA", price, f"{direc} sin expansion (cumdelta_mom {exp_mom:.0f}<{EXP_MIN:.0f})")
            st["last_calma"] = ts[:16]
            save_state(st); return
        ev = evento_cerca()
        if ev:
            if st.get("cal_last") != ev:
                st["cal_last"] = ev
                log_ev(ts, modo, "CAL_BLOCK", price, f"señal {direc} bloqueada: {ev}")
                enviar_texto(f"📅 {modo} OF-exec — señal {direc} bloqueada por calendario: {ev} "
                             f"(sin abrir de -{CAL_PRE_MIN} a +{CAL_POST_MIN}min)", mercado=CANAL)
            save_state(st); return
        entry = price
        if live:
            if os.path.exists(FLAG_CIEL):
                log_ev(ts, modo, "CONFLICTO_CIEL", price, "LIVE_MGC.txt existe — 1 carril por cuenta")
                enviar_texto("⚠️ OF-exec — LIVE_MGC.txt (Ciel VIVO) existe: no ejecuto real. "
                             "1 carril por cuenta.", mercado=CANAL)
                save_state(st); return
            pos = br.get_positions()
            if pos.get("error"):
                log_ev(ts, modo, "POS_ILEGIBLE", price, "no abro con posiciones ilegibles (flap conexion)")
                save_state(st); return
            if pos.get("open_positions", 0) > 0:
                log_ev(ts, modo, "POSICION_AJENA", price, "hay posicion en la cuenta — no abro")
                save_state(st); return
            bid, ask = br.get_current_price()
            if not (bid and ask):
                save_state(st); return
            entry = ask if direc == "BUY" else bid   # referencia p/ SL/TP; el bridge llena a MARKET
        entry = round(entry, 1)
        sl = round(entry - d * SL_PTS, 1); tp = round(entry + d * TP_PTS, 1)
        bal_placed = None
        if live:
            bal_placed = get_balance()   # balance ANTES del trade -> P&L real = delta al cerrar
            r = br.place_order(direc.lower(), CONTRACTS, entry, sl, tp)
            if r.get("status") != "ok":
                log_ev(ts, modo, "ORDEN_RECHAZADA", entry, str(r.get("message", r)))
                enviar_texto(f"❌ OF-exec — orden {direc} rechazada: {r.get('message', r)}", mercado=CANAL)
                save_state(st); return
        st["open"] = {"dir": direc, "entry": entry, "opened": ts, "sl": sl, "tp": tp,
                      "bal_placed": bal_placed, "tries": 0, "balfail": 0, "timed_out": False}
        emoji = "🔴" if live else "🧪"
        log_ev(ts, modo, f"ABRE {direc}", entry, f"sl {sl} tp {tp} racha_div {st['div_streak']} exp_mom {exp_mom:.0f}")
        enviar_texto(f"{emoji} **{modo} OF-exec — abre {direc}** @ {entry} (div racha {st['div_streak']})\n"
                     f"SL {sl} | TP {tp} | timeout {MAX_MIN}min | 1 MGC", mercado=CANAL)

    save_state(st)

if __name__ == "__main__":
    # 22-jul: opera de MADRUGADA sin supervision (ventana Londres) -> un crash no debe morir
    # en silencio. Log + Discord + re-raise (para que el traceback completo quede en el .log).
    try:
        main()
    except Exception as _ex:
        import traceback
        _tb = traceback.format_exc().replace("\n", " | ")[:220]
        try:
            log_ev(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "?", "CRASH", "", _tb)
        except Exception:
            pass
        try:
            enviar_texto(f"💥 **MANAS ejecutor CRASHEO** — {type(_ex).__name__}: {str(_ex)[:120]}. "
                         f"Revisar task_of_exec.log. Este ciclo NO opero.", mercado=CANAL)
        except Exception:
            pass
        raise
