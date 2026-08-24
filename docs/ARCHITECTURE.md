# Architecture

Four processes, one broker, and a deliberate air-gap between "decide" and "trade".

```
Quantower (broker platform)
  └── C# bridge plugins, one per instrument, each an HTTP endpoint
        :8765 Ciel/MGC    :8766 OF-MGC    :8767 OF-MES
        exposes /health, level-2 depth, volume analysis, place_order,
        close_partial, and last_tick_age_s for liveness checks
             │
   ┌─────────┴──────────┐
   │                    │
paper simulator      live executor
agus_orderflow_      agus_ejecutor_
reader.py            of_mgc.py
   │                    │
   └── identical signal semantics, so the two can be compared event by event
```

Both run on a one-minute Windows Scheduled Task. The paper simulator always
runs. The executor decides at each tick whether it is allowed to trade.

## The signal

Divergence between price and cumulative delta, requiring a streak of ≥ 2 cycles
before it fires. Cumulative delta resets per session (13:30 UTC). Lookback 5
bars: bullish when price makes a lower low while cumulative delta does not.

Absorption and imbalance were implemented and then switched off — the 30-day
historical backtest (`src/backtest_of_pro.py`) showed absorption alone loses
money and MES is unprofitable once costs are applied. Divergence-only survived.

## Live/paper: the two-hands rule

The executor trades real money **only** if the file `OF_LIVE_MGC.txt` exists.

That file is created by a human double-clicking a `.bat` that demands a typed
`SI` confirmation. No automated process creates it — not the scheduler, not the
executor, not an assistant. Deleting the file reverts to dry-run on the next
tick, so the abort path requires no working code.

This exists because a config flag inside a program that trades money is a single
point of failure, and the failure is expensive.

## Guardrails, in the order they are checked

| Guard | Trigger | Action |
|---|---|---|
| MLL kill | balance ≤ trailing floor + $100 | flatten, `dead=true`, stop for good |
| Daily brake | day P&L ≤ −$300 | stop opening for the rest of the day |
| Consistency ceiling | day P&L ≥ $600 | stop — prop rules cap single-day share |
| Conflict | Ciel's `LIVE_MGC.txt` also present | refuse: two systems, one account |
| Foreign position | position on the account the executor did not open | refuse |
| News window | high-impact USD event, −40/+15 min | refuse |

The −$300 brake is the only guard chosen by backtest rather than judgement
(`src/backtest_of_freno.py`, 30 days): it rescued 4 of 4 bad days and cut no
recoveries. −$450 and a three-consecutive-stops rule both tested worse.

## Order placement

Brackets are server-side. `place_order` submits entry plus stop and target to
the broker, so a crashed bridge cannot leave an unprotected position — which is
what happened on 30 July, when the bridges died five minutes after an entry and
the broker closed the trade correctly without any local process alive.

The timeout exit is the exception: it is enforced locally via `close_partial`,
so it is the one exit that does *not* survive a process death.

## Known defect

The bracket is computed from the reference ask/bid, then the entry fills at
market. When the fill differs from the reference, the true distance to target
shifts by that difference while the recorded target does not. Measured at one
tick on essentially every trade — small per trade, structural in aggregate, and
invisible unless fills are reconciled against the reference price.
