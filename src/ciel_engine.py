# -*- coding: utf-8 -*-
"""Motor Ciel unificado — tendencia diaria + fade intradía.

Una sola fuente de verdad para paper, backtest y (futuro) ejecutor Lucid.
Barra = (unix_ts, open, high, low, close).

Modo legacy (lucid_session=False): gestiona SL/TP en velas nocturnas; entradas 9:30–16:00.
Modo Lucid (lucid_session=True): flat forzado >= 16:40 ET; sin entradas >= 15:00;
  sin gestión overnight (regla sim de Lucid ~4:45 PM).
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# v3.4 paper / eval $150k
DEFAULT_ZONA_TREND = 50.0
DEFAULT_FADE_EXT = 85.0
DEFAULT_FADE_TP_R = 0.5

MARKETS = {
    "ZW=F": {"nombre": "Trigo", "dpp": 50.0},
    "GC=F": {"nombre": "Oro", "dpp": 10.0},
}


@dataclass
class CielConfig:
    cost: float = 5.0
    risk_min_usd: float = 150.0
    risk_max_usd: float = 400.0
    timeout_bars: int = 8
    zona_trend: float = DEFAULT_ZONA_TREND
    fade_ext: float = DEFAULT_FADE_EXT
    fade_tp_r: float = DEFAULT_FADE_TP_R
    lucid_session: bool = False
    session_open_min: int = 9 * 60 + 30
    session_close_min: int = 16 * 60          # exclusivo para entradas (legacy)
    no_entry_after_min: int = 15 * 60       # 15:00 ET si lucid_session
    flat_after_min: int = 16 * 60 + 40      # 16:40 ET cierre forzado Lucid


_SSL_WARNED = False


def _http_get(req: urllib.request.Request, timeout: float = 40) -> bytes:
    """GET con reintento sin verificar SSL si el entorno tiene CA rota (común en conda)."""
    global _SSL_WARNED
    try:
        return urllib.request.urlopen(req, timeout=timeout).read()
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" not in str(e):
            raise
        if not _SSL_WARNED:
            import sys
            print(
                "[ciel_engine] SSL: reintento sin verificar certificado "
                "(fijar SSL_CERT_FILE o REQUESTS_CA_BUNDLE si preferís verificar)",
                file=sys.stderr,
            )
            _SSL_WARNED = True
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return urllib.request.urlopen(req, timeout=timeout, context=ctx).read()


def fetch_yahoo(sym: str, interval: str, range_: str) -> list[tuple]:
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        f"?interval={interval}&range={range_}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 CielEngine/1.0"})
    raw = json.loads(_http_get(req).decode())
    res = raw["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    out = []
    for i, t in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        out.append((t, o, h, l, c))
    return out


def bars_closed(bars: list[tuple], interval_sec: int = 3600) -> list[tuple]:
    now = datetime.now().timestamp()
    return [b for b in bars if b[0] + interval_sec <= now]


def sma(closes: list[float], i: int, period: int) -> Optional[float]:
    if i < period - 1:
        return None
    return sum(closes[i - period + 1 : i + 1]) / period


def atr(H: list, L: list, C: list, i: int, period: int = 14) -> Optional[float]:
    if i < period:
        return None
    s = 0.0
    for k in range(i - period + 1, i + 1):
        s += max(H[k] - L[k], abs(H[k] - C[k - 1]), abs(L[k] - C[k - 1]))
    return s / period


def mapa_tendencia(daily_bars: list[tuple]) -> dict[date, str]:
    """ALCISTA / BAJISTA / LATERAL usando cierre del día ANTERIOR (sin look-ahead)."""
    closes = [b[4] for b in daily_bars]
    out: dict[date, str] = {}
    for i in range(len(daily_bars)):
        d = datetime.fromtimestamp(daily_bars[i][0], ET).date()
        j = i - 1
        if j < 50:
            out[d] = "LATERAL"
            continue
        ma20 = sma(closes, j, 20)
        ma50 = sma(closes, j, 50)
        ma20p = sma(closes, j - 5, 20)
        p = closes[j]
        if ma20 is None or ma50 is None or ma20p is None:
            out[d] = "LATERAL"
        elif p > ma20 > ma50 and ma20 > ma20p:
            out[d] = "ALCISTA"
        elif p < ma20 < ma50 and ma20 < ma20p:
            out[d] = "BAJISTA"
        else:
            out[d] = "LATERAL"
    return out


daily_trend_map = mapa_tendencia  # alias backtest histórico


def _mins_et(ts: int) -> int:
    dt = datetime.fromtimestamp(ts, ET)
    return dt.hour * 60 + dt.minute


def _can_enter(mins: int, cfg: CielConfig) -> bool:
    if mins < cfg.session_open_min:
        return False
    if cfg.lucid_session:
        return mins < cfg.no_entry_after_min
    return mins < cfg.session_close_min


def _must_flat(mins: int, cfg: CielConfig) -> bool:
    return cfg.lucid_session and mins >= cfg.flat_after_min


def _stop_dist(atr_val: float, dpp: float, cfg: CielConfig) -> float:
    lo_p = cfg.risk_min_usd / dpp
    hi_p = cfg.risk_max_usd / dpp
    return min(max(1.75 * atr_val, lo_p), hi_p)


def _close_pnl(dirn: int, entry: float, price: float, dpp: float, cost: float) -> float:
    mv = (price - entry) if dirn == 1 else (entry - price)
    return mv * dpp - cost


def _try_close_position(
    pos: dict,
    i: int,
    H: list,
    L: list,
    C: list,
    mins: int,
    dpp: float,
    cfg: CielConfig,
) -> Optional[tuple[str, float, float]]:
    """Retorna (motivo, precio, pnl) o None si sigue abierta."""
    dirn = pos["dir"]
    e, slv, tpv = pos["entry"], pos["sl"], pos["tp"]
    if _must_flat(mins, cfg):
        return "FLAT", C[i], _close_pnl(dirn, e, C[i], dpp, cfg.cost)
    hit_sl = (L[i] <= slv) if dirn == 1 else (H[i] >= slv)
    hit_tp = (H[i] >= tpv) if dirn == 1 else (L[i] <= tpv)
    if hit_sl:
        return "SL", slv, -abs(e - slv) * dpp - cfg.cost
    if hit_tp:
        return "TP", tpv, abs(tpv - e) * dpp - cfg.cost
    if i - pos["barra_i"] >= cfg.timeout_bars:
        return "TIEMPO", C[i], _close_pnl(dirn, e, C[i], dpp, cfg.cost)
    return None


def _try_entry(
    i: int,
    dt: datetime,
    reg: str,
    H: list,
    L: list,
    C: list,
    dpp: float,
    cfg: CielConfig,
) -> Optional[dict]:
    mins = dt.hour * 60 + dt.minute
    if not _can_enter(mins, cfg):
        return None
    a = atr(H, L, C, i)
    if not a or a <= 0:
        return None
    lo = min(L[max(0, i - 47) : i + 1])
    hi = max(H[max(0, i - 47) : i + 1])
    if hi <= lo:
        return None
    p100 = (C[i] - lo) / (hi - lo) * 100
    sd = _stop_dist(a, dpp, cfg)
    modo = dirn = tpd = None
    if reg != "LATERAL":
        if reg == "ALCISTA" and p100 <= cfg.zona_trend:
            modo, dirn, tpd = "TREND", 1, 1.5 * sd
        elif reg == "BAJISTA" and p100 >= (100 - cfg.zona_trend):
            modo, dirn, tpd = "TREND", -1, 1.5 * sd
    else:
        if p100 >= cfg.fade_ext:
            modo, dirn, tpd = "FADE", -1, cfg.fade_tp_r * sd
        elif p100 <= (100 - cfg.fade_ext):
            modo, dirn, tpd = "FADE", 1, cfg.fade_tp_r * sd
    if not modo:
        return None
    e = C[i]
    return {
        "dir": dirn,
        "entry": e,
        "sl": e - dirn * sd,
        "tp": e + dirn * tpd,
        "barra_i": i,
        "modo": modo,
    }


def run_backtest(
    h1: list[tuple],
    tmap: dict[date, str],
    dpp: float,
    cfg: Optional[CielConfig] = None,
) -> list[tuple[date, float, str, str]]:
    """Backtest batch. Retorna [(fecha, pnl, modo, motivo), ...]."""
    cfg = cfg or CielConfig()
    T = [x[0] for x in h1]
    H = [x[2] for x in h1]
    L = [x[3] for x in h1]
    C = [x[4] for x in h1]
    trades: list[tuple[date, float, str, str]] = []
    pos = None
    for i in range(60, len(h1)):
        dt = datetime.fromtimestamp(T[i], ET)
        mins = _mins_et(T[i])
        if cfg.lucid_session and mins < cfg.session_open_min:
            continue
        if pos:
            closed = _try_close_position(pos, i, H, L, C, mins, dpp, cfg)
            if closed:
                motivo, _, pnl = closed
                trades.append((dt.date(), pnl, pos["modo"], motivo))
                pos = None
            continue
        reg = tmap.get(dt.date(), "LATERAL")
        pos = _try_entry(i, dt, reg, H, L, C, dpp, cfg)
    return trades


def run_paper_cycle(
    h1: list[tuple],
    tmap: dict[date, str],
    dpp: float,
    market_state: dict,
    cfg: Optional[CielConfig] = None,
) -> tuple[list[dict], str]:
    """Un ciclo incremental (forward). market_state: pos, ultima_barra, trades, wins, pnl."""
    cfg = cfg or CielConfig()
    T = [x[0] for x in h1]
    H = [x[2] for x in h1]
    L = [x[3] for x in h1]
    C = [x[4] for x in h1]
    eventos: list[dict] = []
    ultima = market_state.get("ultima_barra", 0)

    for i in range(60, len(h1)):
        if T[i] <= ultima:
            continue
        dt = datetime.fromtimestamp(T[i], ET)
        market_state["ultima_barra"] = T[i]
        mins = _mins_et(T[i])

        if market_state.get("pos"):
            p = market_state["pos"]
            closed = _try_close_position(p, i, H, L, C, mins, dpp, cfg)
            if closed:
                motivo, precio, pnl = closed
                market_state["trades"] = market_state.get("trades", 0) + 1
                if pnl > 0:
                    market_state["wins"] = market_state.get("wins", 0) + 1
                market_state["pnl"] = market_state.get("pnl", 0.0) + pnl
                eventos.append({
                    "ts": dt.strftime("%Y-%m-%d %H:%M"),
                    "evento": "CIERRE",
                    "motivo": motivo,
                    "precio": round(precio, 4),
                    "pnl": round(pnl, 2),
                    "modo": p["modo"],
                    "dir": p["dir"],
                    "entry": p["entry"],
                    "sl": p["sl"],
                    "tp": p["tp"],
                })
                market_state["pos"] = None
            continue

        if cfg.lucid_session and mins < cfg.session_open_min:
            continue
        reg = tmap.get(dt.date(), "LATERAL")
        pos = _try_entry(i, dt, reg, H, L, C, dpp, cfg)
        if pos:
            market_state["pos"] = pos
            eventos.append({
                "ts": dt.strftime("%Y-%m-%d %H:%M"),
                "evento": "ABRE",
                "motivo": pos["modo"],
                "precio": round(pos["entry"], 4),
                "pnl": "",
                "modo": pos["modo"],
                "dir": pos["dir"],
                "entry": pos["entry"],
                "sl": pos["sl"],
                "tp": pos["tp"],
            })

    abierta = "abierta" if market_state.get("pos") else "plana"
    tr = market_state.get("trades", 0)
    wr = market_state.get("wins", 0) / tr * 100 if tr else 0.0
    resumen = f"{tr:3d} trades  WR {wr:5.1f}%  {market_state.get('pnl', 0):+9.2f}  ({abierta})"
    return eventos, resumen


def trades_metrics(trades: list[tuple]) -> dict:
    """PF, total, n desde lista (date, pnl, ...)"""
    if not trades:
        return {"n": 0, "pf": 0.0, "total": 0.0, "wr": 0.0}
    pl = [t[1] for t in trades]
    w = [x for x in pl if x > 0]
    l = [x for x in pl if x <= 0]
    return {
        "n": len(pl),
        "pf": sum(w) / abs(sum(l)) if l else 99.0,
        "total": sum(pl),
        "wr": len(w) / len(pl) * 100,
    }


def daily_pnl_series(trades_list: list[list[tuple]], multipliers: list[float]) -> list[tuple[date, float]]:
    """Combina trades de varios mercados con multiplicador de contratos."""
    daily: dict[date, float] = {}
    for trades, mult in zip(trades_list, multipliers):
        for t in trades:
            d, pnl = t[0], t[1]
            daily[d] = daily.get(d, 0.0) + pnl * mult
    return sorted(daily.items())


def et_now() -> datetime:
    return datetime.now(ET)


def et_mins_now() -> int:
    n = et_now()
    return n.hour * 60 + n.minute


def bars_from_bridge(bridge, tf: str = "H1", count: int = 120) -> list[tuple]:
    """Velas OHLC desde Quantower bridge → formato (t,o,h,l,c)."""
    raw = bridge.get_bars(tf, count)
    out = []
    for b in raw:
        try:
            out.append((int(b["t"]), float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])))
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda x: x[0])
    return out


def load_market_bars(sym: str, bridge=None, h1_count: int = 120) -> tuple[list[tuple], list[tuple]]:
    """Diario (Yahoo 2y) + H1 (bridge si hay, si no Yahoo 60d)."""
    daily = fetch_yahoo(sym, "1d", "2y")
    h1 = None
    if bridge is not None and bridge.is_connected():
        try:
            h1 = bars_from_bridge(bridge, "H1", h1_count)
        except Exception:
            h1 = None
    if not h1 or len(h1) < 61:
        h1 = fetch_yahoo(sym, "1h", "60d")
    h1 = bars_closed(h1)
    return daily, h1


def signal_on_latest_bar(
    h1: list[tuple],
    tmap: dict[date, str],
    dpp: float,
    has_position: bool,
    cfg: Optional[CielConfig] = None,
) -> Optional[dict]:
    """Evalúa solo la última vela cerrada. Retorna pos dict para ABRE o None."""
    cfg = cfg or CielConfig(lucid_session=True)
    if has_position or len(h1) < 61:
        return None
    i = len(h1) - 1
    T = [x[0] for x in h1]
    H = [x[2] for x in h1]
    L = [x[3] for x in h1]
    C = [x[4] for x in h1]
    dt = datetime.fromtimestamp(T[i], ET)
    reg = tmap.get(dt.date(), "LATERAL")
    pos = _try_entry(i, dt, reg, H, L, C, dpp, cfg)
    if pos:
        pos["bar_ts"] = T[i]
        pos["modo"] = pos.get("modo") or (
            "TREND" if reg != "LATERAL" else "FADE"
        )
    return pos
