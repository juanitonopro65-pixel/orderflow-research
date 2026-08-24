"""
quantower_bridge.py — Puente Python hacia Quantower (GC Gold Futures)
=====================================================================
Modulo INDEPENDIENTE — no toca MT5 ni agus_signal.py.

Requiere que AgustinaBridge este corriendo dentro de Quantower.
El bridge C# expone un servidor HTTP en localhost:8765.

Endpoints disponibles:
  GET /health -> {"status":"ok"}
  GET /price  -> {"bid":3320.5,"ask":3320.7,"mid":3320.6,"symbol":"GCQ6","ts":"..."}

Uso:
    from quantower_bridge import QuantowerBridge
    bridge = QuantowerBridge()
    bid, ask = await bridge.get_current_price()
"""

import asyncio
import json
import urllib.request
import urllib.error
from datetime import datetime
from math import floor
from typing import Optional

# ─── Configuracion GC ─────────────────────────────────────────────────────────

BRIDGE_PORT    = 8765
BRIDGE_URL     = f"http://localhost:{BRIDGE_PORT}"

TICK_SIZE      = 0.10
TICK_VALUE     = 10.00
CONTRACT_SIZE  = 100
MAX_CONTRACTS  = 3
RISK_PER_TRADE = 250.0   # USD — ajustado para cuenta Lucid $25K

# ─── Logging ──────────────────────────────────────────────────────────────────

def _log(msg: str, nivel: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    prefijos = {"INFO": "[I]", "OK": "[OK]", "WARN": "[W]", "FAIL": "[X]", "DATA": "[D]"}
    print(f"  [{ts}] {prefijos.get(nivel,'[I]')} {msg}", flush=True)

# ─── Clase principal ──────────────────────────────────────────────────────────

class QuantowerBridge:
    """
    Conecta Agustina a Quantower via HTTP local.
    Quantower se encarga de la conexion Rithmic con credenciales ISV.
    """

    def __init__(self, port: int = BRIDGE_PORT, timeout: float = 5.0):
        self._base = f"http://localhost:{port}"
        self._timeout = timeout

    # ── Conexion / estado ─────────────────────────────────────────────────────

    def is_connected(self) -> bool:
        """Verifica que el bridge C# este corriendo en Quantower."""
        try:
            data = self._get("/health")
            return data.get("status") == "ok"
        except Exception:
            return False

    def _get(self, path: str) -> dict:
        url = f"{self._base}{path}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_bars(self, tf: str = "H1", count: int = 100) -> list:
        """
        Retorna barras OHLCV de MGCQ6 desde Rithmic.
        Cada barra: {"t": unix_ts, "o": open, "h": high, "l": low, "c": close, "v": volume}
        Orden: cronologico (oldest → newest).
        """
        result = self._get(f"/bars?tf={tf}&count={count}")
        return result.get("bars", [])

    def get_dom(self) -> dict:
        """
        Snapshot DOM (Level2) de MGCQ6 — top 5 niveles bid/ask.
        {"available": True, "imbalance": 0.62, "bids": [...], "asks": [...],
         "bid_depth": N, "ask_depth": N}
        Si Level2 no disponible en feed: {"available": False, "error": "..."}.
        Nunca lanza — falla silenciosa para no romper el flujo principal.
        """
        try:
            return self._get("/dom")
        except urllib.error.URLError as e:
            return {"available": False, "error": f"Bridge no responde: {e}"}
        except Exception as e:
            return {"available": False, "error": str(e)}

    def get_delta(self, window_min: int = 15) -> dict:
        """
        Delta de order flow rolling (buy vol - sell vol) desde Rithmic.
        Siempre incluye: delta_15m, delta_1h, cvd_slope, tick_count.
        window_min: ventana adicional configurable (1-60m).
        Nunca lanza — falla silenciosa para no romper el flujo principal.
        """
        try:
            return self._get(f"/delta?window={window_min}")
        except urllib.error.URLError as e:
            return {"error": f"Bridge no responde: {e}",
                    "delta_15m": None, "delta_1h": None,
                    "tick_count": 0,   "cvd_slope": "unknown"}
        except Exception as e:
            return {"error": str(e),
                    "delta_15m": None, "delta_1h": None,
                    "tick_count": 0,   "cvd_slope": "unknown"}

    # ── Precio en tiempo real ─────────────────────────────────────────────────

    def get_current_price(self) -> tuple[Optional[float], Optional[float]]:
        """
        Obtiene bid/ask actual de GC desde Quantower.
        Equivalente a mt5.symbol_info_tick(SYMBOL).
        Retorna (bid, ask) o (None, None) si falla.
        """
        try:
            data = self._get("/price")
            bid = data.get("bid")
            ask = data.get("ask")
            if bid and ask and bid > 0 and ask > 0:
                return float(bid), float(ask)
            return None, None
        except urllib.error.URLError:
            _log("Quantower bridge no responde — verifica que AgustinaBridge este corriendo", "FAIL")
            return None, None
        except Exception as e:
            _log(f"Error obteniendo precio: {e}", "FAIL")
            return None, None

    def get_mid_price(self) -> Optional[float]:
        """Precio medio (bid+ask)/2."""
        bid, ask = self.get_current_price()
        if bid and ask:
            return round((bid + ask) / 2, 2)
        return None

    def get_symbol(self) -> Optional[str]:
        """Retorna el simbolo activo (ej: GCQ6)."""
        try:
            data = self._get("/price")
            return data.get("symbol")
        except Exception:
            return None

    # ── Calculo de posicion ───────────────────────────────────────────────────

    @staticmethod
    def calcular_contratos(
        entry_price: float, sl_price: float, risk_usd: float = RISK_PER_TRADE
    ) -> int:
        sl_distance = abs(entry_price - sl_price)
        if sl_distance <= 0:
            return 0
        risk_per_contract = sl_distance * CONTRACT_SIZE
        contracts = floor(risk_usd / risk_per_contract)
        return min(contracts, MAX_CONTRACTS)

    @staticmethod
    def info_contrato(
        entry_price: float, sl_price: float,
        tp1_price: float, risk_usd: float = RISK_PER_TRADE
    ) -> dict:
        sl_dist    = abs(entry_price - sl_price)
        tp1_dist   = abs(tp1_price - entry_price)
        contracts  = QuantowerBridge.calcular_contratos(entry_price, sl_price, risk_usd)
        risk_real  = sl_dist * CONTRACT_SIZE * contracts
        reward_tp1 = tp1_dist * CONTRACT_SIZE * contracts
        ratio      = round(tp1_dist / sl_dist, 2) if sl_dist > 0 else 0
        return {
            "contracts":     contracts,
            "entry":         entry_price,
            "sl":            sl_price,
            "tp1":           tp1_price,
            "sl_ticks":      round(sl_dist / TICK_SIZE),
            "tp1_ticks":     round(tp1_dist / TICK_SIZE),
            "risk_usd":      round(risk_real, 2),
            "reward_usd":    round(reward_tp1, 2),
            "ratio":         ratio,
        }

    # ── Posiciones y cierres ─────────────────────────────────────────────────

    def get_positions(self) -> dict:
        """
        Retorna estado de posiciones abiertas en MGCQ6.
        {"open_positions": N, "net_qty": N, "symbol": "MGCQ6", ...}
        Nunca lanza — retorna open_positions=0 si falla.
        """
        try:
            return self._get("/positions")
        except urllib.error.URLError as e:
            return {"open_positions": 0, "net_qty": 0, "error": f"Bridge no responde: {e}"}
        except Exception as e:
            return {"open_positions": 0, "net_qty": 0, "error": str(e)}

    def close_partial(self, quantity: int = 1, reason: str = "manual") -> dict:
        """
        Cierra parcialmente la posicion en MGCQ6 via POST /close.
        El bridge C# coloca una orden de mercado en direccion opuesta.
        Retorna {"status": "ok"/"error", "message": "...", "qty_closed": N}
        """
        payload = json.dumps({"quantity": quantity, "reason": reason}).encode("utf-8")
        url = f"{self._base}/close"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            return {"status": "error", "message": f"Bridge no responde: {e}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ── Ejecucion de ordenes ──────────────────────────────────────────────────

    def place_order(
        self,
        side: str,          # "buy" | "sell"
        contracts: int,
        entry: float,
        sl: float,
        tp1: float,
        tp2: float = 0.0,
    ) -> dict:
        """
        Coloca una orden limite en Quantower via HTTP.
        Requiere AgustinaBridge corriendo y el endpoint POST /order activo.

        Retorna dict con "status": "ok" | "error" y detalles.
        """
        payload = json.dumps({
            "side":      side.lower(),
            "contracts": contracts,
            "entry":     round(entry, 2),
            "sl":        round(sl, 2),
            "tp1":       round(tp1, 2),
            "tp2":       round(tp2, 2),
        }).encode("utf-8")

        url = f"{self._base}/order"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result
        except urllib.error.URLError as e:
            return {"status": "error", "message": f"Bridge no responde: {e}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


# ─── Test de conexion ─────────────────────────────────────────────────────────

def test_bridge():
    """
    Prueba el bridge:
      1. Verificar que Quantower este corriendo con AgustinaBridge
      2. Obtener precio actual de GC
      3. Mostrar info de contrato
    """
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print()
    print("=" * 55)
    print("  QUANTOWER BRIDGE TEST — GC (Gold Futures)")
    print("=" * 55)

    bridge = QuantowerBridge()

    print()
    print("  [1/3] Verificando bridge en Quantower...")
    if not bridge.is_connected():
        print("  FALLO: Bridge no responde en localhost:8765")
        print()
        print("  Para activarlo en Quantower:")
        print("  1. Abre Strategy Runner (menu Tools > Strategy Manager)")
        print("  2. Busca 'AgustinaBridge' en la lista")
        print("  3. Selecciona cuenta Lucid Trading y activa la estrategia")
        return False

    symbol = bridge.get_symbol()
    print(f"  OK  Bridge activo | Simbolo: {symbol}")

    print()
    print("  [2/3] Obteniendo precio GC...")
    bid, ask = bridge.get_current_price()

    if bid and ask:
        mid = (bid + ask) / 2
        spread_ticks = round((ask - bid) / TICK_SIZE)
        print(f"  OK  BID: ${bid:.2f}  |  ASK: ${ask:.2f}  |  MID: ${mid:.2f}")
        print(f"      Spread: {spread_ticks} ticks = ${spread_ticks * TICK_VALUE:.2f}")
    else:
        print("  WARN: Sin precio — mercado cerrado o bridge sin datos")
        mid = None

    print()
    print("  [3/3] Info de contrato GC (risk $250):")
    precio_ref = mid if mid else 3320.0
    info = QuantowerBridge.info_contrato(
        entry_price=precio_ref,
        sl_price=precio_ref - 6.0,
        tp1_price=precio_ref + 12.0,
        risk_usd=250.0,
    )
    print(f"  SL (-6 pts)  : {info['sl_ticks']} ticks = ${info['sl_ticks']*TICK_VALUE:.0f}/contrato")
    print(f"  TP1 (+12 pts): {info['tp1_ticks']} ticks = ${info['tp1_ticks']*TICK_VALUE:.0f}/contrato")
    print(f"  Risk $250    -> {info['contracts']} contrato(s) | Riesgo real: ${info['risk_usd']:.2f}")
    print(f"  Reward TP1   : ${info['reward_usd']:.2f} | Ratio: 1:{info['ratio']}")

    print()
    print("=" * 55)
    print("  TEST COMPLETADO")
    print("=" * 55)
    print()
    return True


if __name__ == "__main__":
    test_bridge()
