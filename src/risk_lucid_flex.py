# -*- coding: utf-8 -*-
"""Reglas LucidFlex eval — MLL, consistencia 50%, freno diario, escalera de contratos."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LucidFlexProfile:
    name: str
    account_size: float
    profit_target: float
    max_loss: float
    mll_floor: float          # balance mínimo antes de MUERTE (trailing EOD aprox)
    mll_buffer: float = 100.0
    daily_stop: float = 400.0
    consistency_max: float = 0.50   # mejor_dia / profit_total eval
    ladder_cushion: float = 1500.0
    flat_after_min: int = 16 * 60 + 40
    no_entry_after_min: int = 15 * 60
    session_open_min: int = 9 * 60 + 30


PROFILES = {
    "25k": LucidFlexProfile(
        name="25k",
        account_size=25000.0,
        profit_target=1250.0,
        max_loss=1000.0,
        mll_floor=24141.0,   # confirmado en OF contra dashboard Lucid
        daily_stop=300.0,
        ladder_cushion=800.0,
    ),
    "150k": LucidFlexProfile(
        name="150k",
        account_size=150000.0,
        profit_target=9000.0,
        max_loss=4500.0,
        mll_floor=145500.0,  # 150k - 4.5k MLL inicial
        daily_stop=450.0,
        ladder_cushion=1500.0,
    ),
}


def contracts_ladder(eval_profit: float, profile: LucidFlexProfile) -> int:
    """1 o 2 contratos según colchón de profit en la eval."""
    return 2 if eval_profit >= profile.ladder_cushion else 1


def consistency_blocks_open(
    day_pnl: float,
    best_day: float,
    eval_profit: float,
    potential_win: float,
    profile: LucidFlexProfile,
) -> tuple[bool, str]:
    """Flex eval: mejor día <= 50% del profit total de la eval."""
    new_day = day_pnl + potential_win
    new_best = max(best_day, new_day)
    new_total = eval_profit + potential_win
    if new_total <= 0:
        return False, ""
    ratio = new_best / new_total
    if ratio > profile.consistency_max + 0.001:
        return True, f"consistencia {ratio:.0%} > {profile.consistency_max:.0%}"
    return False, ""


def mll_killed(balance: float | None, profile: LucidFlexProfile) -> bool:
    if balance is None:
        return False
    return balance <= profile.mll_floor + profile.mll_buffer


def daily_stopped(day_pnl: float, profile: LucidFlexProfile) -> bool:
    return day_pnl <= -profile.daily_stop
