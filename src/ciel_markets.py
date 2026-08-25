# -*- coding: utf-8 -*-
"""Mercados Ciel para Quantower — puertos y specs.

Puertos (mismo esquema que docs/ARCHITECTURE.md):
  :8765  Ciel MGC (oro micro)
  :8766  OF-MGC (no usar desde Ciel)
  :8767  OF-MES
  :8768  Ciel ZW (trigo entero)

En Quantower: una instancia AgustinaBridge por gráfico/símbolo, con el puerto
configurado en la estrategia. El C# ya expone /health /price /bars /order etc.
"""
from __future__ import annotations

# id → config
MARKETS = {
    "MGC": {
        "id": "MGC",
        "nombre": "Oro",
        "yahoo": "GC=F",
        "port": 8765,
        "dpp": 10.0,          # $ / punto (micro gold)
        "tick": 0.10,
        "canal": "CIEL-MGC",
    },
    "ZW": {
        "id": "ZW",
        "nombre": "Trigo",
        "yahoo": "ZW=F",
        "port": 8768,
        "dpp": 50.0,          # $ / punto (ZW entero 5000 bu)
        "tick": 0.25,
        "canal": "CIEL-ZW",
    },
}

DEFAULT_MARKETS = ("MGC", "ZW")


def parse_markets(raw: str | None) -> list[str]:
    """'MGC,ZW' | 'MGC' | None → lista validada."""
    if not raw or not str(raw).strip():
        return list(DEFAULT_MARKETS)
    out = []
    for part in str(raw).upper().replace(";", ",").split(","):
        k = part.strip()
        if not k:
            continue
        if k not in MARKETS:
            raise ValueError(f"mercado desconocido: {k} (usa {', '.join(MARKETS)})")
        if k not in out:
            out.append(k)
    return out or list(DEFAULT_MARKETS)
