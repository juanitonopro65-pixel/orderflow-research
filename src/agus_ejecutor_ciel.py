# -*- coding: utf-8 -*-
"""agus_ejecutor_ciel.py — Ejecutor Ciel multi-mercado (MGC + ZW) vía Quantower.

SEÑAL: ciel_engine (tendencia diaria + fade/trend en H1).
EJECUCIÓN: AgustinaBridge
  :8765 MGC   :8768 ZW
  brackets SL/TP server-side.

DOS MANOS: LIVE_MGC.txt (o LIVE_CIEL.txt) → órdenes REALES. Sin archivo → DRY-RUN.
OF_LIVE_MGC.txt presente → no ejecuta real (1 carril por cuenta).
EL ASISTENTE NUNCA CREA LIVE_*.txt.

GUARDRAILS (LucidFlex, cuenta compartida):
  - MLL trailing (CIEL_LUCID_PROFILE=25k|150k)
  - freno diario
  - consistencia 50% eval
  - flat 16:40 ET / sin entradas >= 15:00 ET
  - escalera 1→2 contratos con colchón

Uso (Windows + Quantower):
  set CIEL_LUCID_PROFILE=25k
  set CIEL_MARKETS=MGC
  python agus_ejecutor_ciel.py

  set CIEL_MARKETS=MGC,ZW
  python agus_ejecutor_ciel.py

  python agus_ejecutor_ciel.py --markets MGC
  python agus_ejecutor_ciel.py --check     # health bridges
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from ciel_engine import (  # noqa: E402
    CielConfig,
    et_mins_now,
    load_market_bars,
    mapa_tendencia,
    signal_on_latest_bar,
)
from ciel_markets import MARKETS, parse_markets  # noqa: E402
from quantower_bridge import QuantowerBridge, bridge_for  # noqa: E402
from risk_lucid_flex import (  # noqa: E402
    PROFILES,
    consistency_blocks_open,
    contracts_ladder,
    daily_stopped,
    mll_killed,
)

ET = ZoneInfo("America/New_York")

FLAG_CIEL = os.path.join(HERE, "LIVE_MGC.txt")
FLAG_CIEL_ALT = os.path.join(HERE, "LIVE_CIEL.txt")
FLAG_OF = os.path.join(HERE, "OF_LIVE_MGC.txt")
STATE = os.path.join(HERE, "ciel_exec_state.json")
LOG = os.path.join(HERE, "ciel_exec_log.csv")
BAL = os.path.join(HERE, "ciel_eval_balance.json")

TIMEOUT_MIN = 8 * 60
CANAL = "CIEL"

PROFILE_NAME = os.environ.get("CIEL_LUCID_PROFILE", "150k").lower()
PROFILE = PROFILES.get(PROFILE_NAME, PROFILES["150k"])

CFG = CielConfig(
    lucid_session=True,
    flat_after_min=PROFILE.flat_after_min,
    no_entry_after_min=PROFILE.no_entry_after_min,
    session_open_min=PROFILE.session_open_min,
)

try:
    from agus_discord import enviar_texto
except Exception:
    def enviar_texto(msg, mercado=CANAL):
        print(f"[discord-off] {msg}")


def is_live() -> bool:
    return os.path.exists(FLAG_CIEL) or os.path.exists(FLAG_CIEL_ALT)


def default_state() -> dict:
    return {
        "dead": False,
        "day": "",
        "day_pnl": 0.0,
        "day_start_bal": None,
        "blocked": "",
        "best_day": 0.0,
        "stats": {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0},
        "markets": {},
    }


def _mkt_slot(st: dict, mid: str) -> dict:
    mk = st.setdefault("markets", {})
    if mid not in mk:
        mk[mid] = {"open": None, "last_bar_ts": 0}
    # migrate legacy single-open state (MGC only)
    if mid == "MGC" and st.get("open") and not mk[mid].get("open"):
        mk[mid]["open"] = st.pop("open")
        if "last_bar_ts" in st:
            mk[mid]["last_bar_ts"] = st.pop("last_bar_ts", 0)
    return mk[mid]


def load_state() -> dict:
    try:
        with open(STATE, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        return default_state()
    base = default_state()
    base.update({k: st.get(k, base[k]) for k in base if k != "markets"})
    base["markets"] = st.get("markets") or {}
    if st.get("open") and "MGC" not in base["markets"]:
        base["markets"]["MGC"] = {
            "open": st["open"],
            "last_bar_ts": st.get("last_bar_ts", 0),
        }
    return base


def save_state(st: dict) -> None:
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)


def log_ev(ts, modo, evento, precio, detalle, mercado=""):
    nuevo = not os.path.exists(LOG)
    with open(LOG, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["timestamp", "modo", "mercado", "evento", "precio", "detalle"])
        w.writerow([ts, modo, mercado, evento, precio, detalle])


def eval_start_balance():
    try:
        with open(BAL, encoding="utf-8") as f:
            return float(json.load(f)["eval_start_balance"])
    except Exception:
        return None


def get_balance_any(bridges: dict[str, QuantowerBridge]) -> float | None:
    for br in bridges.values():
        b = br.get_balance()
        if b is not None:
            return b
    return None


def _book(st, slot, o, res, pnl, price, ts, modo, live, src, mcfg):
    pnl = round(pnl, 2)
    slot["open"] = None
    s = st["stats"]
    s["trades"] += 1
    s["wins" if pnl > 0 else "losses"] += 1
    s["pnl"] = round(s["pnl"] + pnl, 2)
    if not live:
        st["day_pnl"] = round(st["day_pnl"] + pnl, 2)
    st["best_day"] = max(st.get("best_day", 0.0), st["day_pnl"])
    wr = s["wins"] / s["trades"] * 100 if s["trades"] else 0
    emoji = "🔴" if live else "🧪"
    mid = mcfg["id"]
    log_ev(
        ts, modo, f"CIERRE {res}", price,
        f"{o['dir']} entry {o['entry']} pnl {pnl:+.2f} ({src})", mid,
    )
    enviar_texto(
        f"{emoji} **{modo} Ciel {mid} — {o['dir']} cerrado {res}** ({pnl:+.0f}$ {src})\n"
        f"entrada {o['entry']} → {price} | dia {st['day_pnl']:+.0f}$ | "
        f"{s['trades']}t {wr:.0f}%WR {s['pnl']:+.0f}$",
        mercado=mcfg["canal"],
    )


def gestionar_abierto(st, slot, price, br, live, ts, modo, mcfg):
    o = slot["open"]
    contracts = o.get("contracts", 1)
    dpp = float(o.get("dpp", mcfg["dpp"]))
    d = 1 if o["dir"] == "BUY" else -1
    try:
        mins = (datetime.now() - datetime.strptime(o["opened"], "%Y-%m-%d %H:%M:%S")).total_seconds() / 60.0
    except Exception:
        mins = 0.0

    if not live:
        hit_sl = (price <= o["sl"]) if d == 1 else (price >= o["sl"])
        hit_tp = (price >= o["tp"]) if d == 1 else (price <= o["tp"])
        flat = et_mins_now() >= PROFILE.flat_after_min
        if not (hit_sl or hit_tp or mins >= TIMEOUT_MIN or flat):
            return
        if hit_tp:
            res, pnl = "TP", abs(o["tp"] - o["entry"]) * dpp * contracts
        elif hit_sl:
            res, pnl = "SL", -abs(o["entry"] - o["sl"]) * dpp * contracts
        elif flat:
            res, pnl = "FLAT", (price - o["entry"]) * d * dpp * contracts
        else:
            res, pnl = f"TIME({mins:.0f}m)", (price - o["entry"]) * d * dpp * contracts
        _book(st, slot, o, res, pnl, price, ts, modo, live, "sim", mcfg)
        return

    pos = br.get_positions()
    if pos.get("error"):
        log_ev(ts, modo, "POS_ILEGIBLE", price, str(pos.get("error"))[:80], mcfg["id"])
        return
    nopen = pos.get("open_positions", 0)
    bal = br.get_balance()

    force = et_mins_now() >= PROFILE.flat_after_min
    if nopen > 0 and (mins >= TIMEOUT_MIN or force):
        if not o.get("closing"):
            reason = "Ciel flat Lucid" if force else "Ciel timeout 8h"
            br.close_partial(contracts, reason)
            o["closing"] = True
            o["close_reason"] = "FLAT" if force else "TIME"
        elif mins >= TIMEOUT_MIN + 10 or (force and mins > 5):
            br.close_partial(contracts, "Ciel close RETRY")
        return

    if nopen > 0:
        return

    bp = o.get("bal_placed")
    if bal is None:
        o["balfail"] = o.get("balfail", 0) + 1
        if o["balfail"] >= 5:
            est = (price - o["entry"]) * d * dpp * contracts
            _book(st, slot, o, "CERRADO?", est, price, ts, modo, live, "est-sin-balance", mcfg)
        return

    if bp is not None and abs(bal - bp) > 0.005:
        pnl = bal - bp
        # Con 2 mercados abiertos el delta de balance NO es PnL de este trade.
        # Si hay otra posición Ciel abierta, estimar por precio.
        otros = sum(
            1 for m, sl in st.get("markets", {}).items()
            if m != mcfg["id"] and sl.get("open")
        )
        if otros > 0:
            pnl = (price - o["entry"]) * d * dpp * contracts
            src = "est-multi"
        else:
            src = "real"
        res = o.get("close_reason") or ("TP" if pnl >= 0 else "SL")
        _book(st, slot, o, res, pnl, price, ts, modo, live, src, mcfg)
        return

    o["tries"] = o.get("tries", 0) + 1
    if o["tries"] >= 3:
        slot["open"] = None
        log_ev(ts, modo, "NO_FILL", price, f"{o['dir']} sin cambio de balance", mcfg["id"])


def price_for(br: QuantowerBridge, yahoo: str, live: bool):
    bid, ask = br.get_current_price()
    if bid and ask:
        return bid, ask, round((bid + ask) / 2, 2)
    if live:
        return None, None, None
    try:
        _, h1 = load_market_bars(yahoo, None)
        if h1:
            mid = float(h1[-1][4])
            return mid, mid, mid
    except Exception:
        pass
    return None, None, None


def try_open(st, slot, br, bid, ask, price, live, ts, modo, mcfg, eval_profit):
    if slot.get("open") or st.get("blocked"):
        return
    if et_mins_now() >= PROFILE.no_entry_after_min:
        return

    daily, h1 = load_market_bars(mcfg["yahoo"], br if (live and br.is_connected()) else None)
    if len(h1) < 61:
        return

    bar_ts = h1[-1][0]
    if bar_ts <= slot.get("last_bar_ts", 0):
        return

    tmap = mapa_tendencia(daily)
    dpp = mcfg["dpp"]
    sig = signal_on_latest_bar(h1, tmap, dpp, has_position=False, cfg=CFG)
    slot["last_bar_ts"] = bar_ts
    if not sig:
        return

    contracts = contracts_ladder(max(eval_profit, 0), PROFILE)
    tp_dist = abs(sig["tp"] - sig["entry"]) * dpp * contracts
    blocked, why = consistency_blocks_open(
        st["day_pnl"], st.get("best_day", 0), max(eval_profit, 0), tp_dist, PROFILE
    )
    if blocked:
        st["blocked"] = "consistencia"
        log_ev(ts, modo, "TECHO_CONSISTENCIA", price, why, mcfg["id"])
        enviar_texto(f"🧢 {modo} Ciel — bloqueado: {why}", mercado=mcfg["canal"])
        return

    direc = "BUY" if sig["dir"] == 1 else "SELL"
    entry = round(ask if direc == "BUY" else bid, 2)
    sl = round(float(sig["sl"]), 2)
    tp = round(float(sig["tp"]), 2)

    if live:
        if os.path.exists(FLAG_OF):
            log_ev(ts, modo, "CONFLICTO_OF", price, "OF_LIVE_MGC.txt existe", mcfg["id"])
            return
        pos = br.get_positions()
        if pos.get("open_positions", 0) > 0:
            log_ev(ts, modo, "POSICION_AJENA", price, "bridge con posicion", mcfg["id"])
            return
        bal_placed = br.get_balance()
        r = br.place_order(direc.lower(), contracts, entry, sl, tp)
        if r.get("status") != "ok":
            log_ev(ts, modo, "ORDEN_RECHAZADA", entry, str(r.get("message", r)), mcfg["id"])
            return
    else:
        bal_placed = None

    slot["open"] = {
        "dir": direc,
        "entry": entry,
        "opened": ts,
        "sl": sl,
        "tp": tp,
        "modo": sig.get("modo", "TREND"),
        "contracts": contracts,
        "dpp": dpp,
        "market": mcfg["id"],
        "bal_placed": bal_placed,
        "tries": 0,
        "balfail": 0,
    }
    emoji = "🔴" if live else "🧪"
    log_ev(
        ts, modo, f"ABRE {direc}", entry,
        f"sl {sl} tp {tp} x{contracts} {sig.get('modo')} bar {bar_ts}", mcfg["id"],
    )
    enviar_texto(
        f"{emoji} **{modo} Ciel {mcfg['id']} — ABRE {direc}** x{contracts} @ {entry}\n"
        f"SL {sl} | TP {tp} | {sig.get('modo')} | perfil {PROFILE.name} | :{mcfg['port']}",
        mercado=mcfg["canal"],
    )


def flatten_all(st, bridges, reason: str):
    for mid, slot in st.get("markets", {}).items():
        o = slot.get("open")
        if not o:
            continue
        br = bridges.get(mid)
        if br:
            br.close_partial(o.get("contracts", 1), reason)


def check_bridges(market_ids: list[str]) -> int:
    print("=" * 56)
    print("  Ciel bridges — health check")
    print("=" * 56)
    ok_n = 0
    for mid in market_ids:
        mcfg = MARKETS[mid]
        br = QuantowerBridge(port=mcfg["port"], quiet=True)
        up = br.is_connected()
        bid, ask = br.get_current_price() if up else (None, None)
        sym = br.get_symbol() if up else None
        status = "OK" if up else "DOWN"
        if up:
            ok_n += 1
        px = f" mid={(bid+ask)/2:.2f}" if bid and ask else ""
        print(f"  {mid:4} :{mcfg['port']}  {status:4}  symbol={sym or '-'}{px}")
        if not up:
            print(f"         → En Quantower: Strategy Runner → AgustinaBridge")
            print(f"           gráfico {mid}/continuo, puerto HTTP = {mcfg['port']}")
    print("=" * 56)
    return 0 if ok_n == len(market_ids) else 1


def main(market_ids: list[str] | None = None):
    market_ids = market_ids or parse_markets(os.environ.get("CIEL_MARKETS"))
    st = load_state()
    if st.get("dead"):
        return

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hoy = ts[:10]
    if st.get("day") != hoy:
        st["day"] = hoy
        st["day_pnl"] = 0.0
        st["blocked"] = ""
        st["day_start_bal"] = None

    live = is_live()
    modo = "LIVE" if live else "DRY"
    bridges = {mid: bridge_for(mid, quiet=not live) for mid in market_ids}

    # 1) gestionar abiertos
    for mid in market_ids:
        mcfg = MARKETS[mid]
        slot = _mkt_slot(st, mid)
        br = bridges[mid]
        bid, ask, price = price_for(br, mcfg["yahoo"], live)
        if price is None:
            if live and slot.get("open"):
                log_ev(ts, modo, "SIN_PRECIO", "", f"bridge :{mcfg['port']}", mid)
            continue
        if slot.get("open"):
            gestionar_abierto(st, slot, price, br, live, ts, modo, mcfg)

    bal_now = get_balance_any(bridges) if live else None
    if live and bal_now is not None:
        if st.get("day_start_bal") is None:
            st["day_start_bal"] = bal_now
        st["day_pnl"] = round(bal_now - st["day_start_bal"], 2)
        st["best_day"] = max(st.get("best_day", 0.0), st["day_pnl"])

    eval_start = eval_start_balance()
    if live and bal_now is not None and eval_start is None:
        try:
            with open(BAL, "w", encoding="utf-8") as f:
                json.dump({"eval_start_balance": bal_now, "set_at": ts}, f, indent=2)
            eval_start = bal_now
        except Exception:
            pass
    eval_profit = (
        (bal_now - eval_start) if (live and bal_now is not None and eval_start is not None)
        else st["stats"]["pnl"]
    )

    if live and mll_killed(bal_now, PROFILE):
        st["dead"] = True
        flatten_all(st, bridges, "MLL guard")
        log_ev(ts, modo, "MLL_KILL", "", f"balance {bal_now}", "")
        enviar_texto(f"🚨 **Ciel MUERTO por MLL** balance {bal_now:.0f}", mercado=CANAL)
        save_state(st)
        return

    if not st.get("blocked") and daily_stopped(st["day_pnl"], PROFILE):
        st["blocked"] = "freno diario"
        log_ev(ts, modo, "FRENO_DIARIO", "", f"dia {st['day_pnl']:+.0f}", "")
        enviar_texto(f"🛑 {modo} Ciel — freno diario {st['day_pnl']:+.0f}$", mercado=CANAL)

    # 2) nuevas entradas (una por mercado por ciclo, si hay señal)
    for mid in market_ids:
        mcfg = MARKETS[mid]
        slot = _mkt_slot(st, mid)
        br = bridges[mid]
        bid, ask, price = price_for(br, mcfg["yahoo"], live)
        if price is None:
            continue
        try_open(st, slot, br, bid, ask, price, live, ts, modo, mcfg, eval_profit)

    save_state(st)


def cli():
    ap = argparse.ArgumentParser(description="Ejecutor Ciel Quantower (MGC+ZW)")
    ap.add_argument("--markets", default=None, help="MGC | ZW | MGC,ZW")
    ap.add_argument("--check", action="store_true", help="solo health check bridges")
    ap.add_argument("--profile", default=None, help="25k | 150k (override env)")
    a = ap.parse_args()

    if a.profile:
        global PROFILE, PROFILE_NAME, CFG
        PROFILE_NAME = a.profile.lower()
        PROFILE = PROFILES.get(PROFILE_NAME, PROFILES["150k"])
        CFG = CielConfig(
            lucid_session=True,
            flat_after_min=PROFILE.flat_after_min,
            no_entry_after_min=PROFILE.no_entry_after_min,
            session_open_min=PROFILE.session_open_min,
        )

    mids = parse_markets(a.markets or os.environ.get("CIEL_MARKETS"))
    if a.check:
        raise SystemExit(check_bridges(mids))
    main(mids)


if __name__ == "__main__":
    try:
        cli()
    except SystemExit:
        raise
    except Exception as ex:
        tb = traceback.format_exc().replace("\n", " | ")[:220]
        try:
            log_ev(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "?", "CRASH", "", tb, "")
        except Exception:
            pass
        try:
            enviar_texto(f"💥 **Ciel ejecutor CRASH** — {type(ex).__name__}: {ex}", mercado=CANAL)
        except Exception:
            pass
        raise
