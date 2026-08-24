# orderflow-research

An algorithmic futures trading system: live-market data bridges, an order-flow
signal engine, a paper simulator, a guarded live executor, and the backtests
used to decide what got deployed.

Built solo. Traded real money on Micro Gold futures (MGC) through Quantower.

**It lost money. This repository documents exactly why, with the raw ledger
included so every figure can be recomputed.**

---

## The headline

| | trades | win rate | net |
|---|---|---|---|
| Dry-run — *the sample the go-live decision was based on* | 13 | 69.2% | **+$288.00** |
| **Live, real money** (20–30 Jul 2026) | **75** | **38.7%** | **−$430.20** |

```bash
python analysis/live_results.py     # reproduces every number in docs/RESULTS.md
```

Two things worth knowing before reading further, because both are the kind of
error that survives if nobody writes it down:

**1. The ledger was contaminated.** Four synthetic unit-test rows (fixture price
`entry 4000.0`; one with the timestamp literally `t`) sat inside the live ledger
and inflated it by $157. A first pass over this data reported −$273.20. The real
figure is −$430.20. `analysis/live_results.py` filters them in code you can read.

**2. The simulated log and reality disagree violently.** For 27–30 July the
signal log totals **+$12,062**; over those same four days the real account lost
**$370**. The simulator counted the same market move up to ten times over,
and recorded +$600 winners that reached target in five minutes — sixty points of
gold in five minutes, which does not happen. See [docs/METHOD.md](docs/METHOD.md).

---

## Why it lost — the actual mechanism

The system was designed as a scalp: 6-point stop (−$60), 9-point target (+$90),
forced exit after 25 minutes. That is a 1 : 1.5 payoff needing a 40% win rate.

What ran was not that system:

```
exit reason      TIME(26m)=35   SL=26   TIME(25m)=5   TP=9
reached target    9 / 75  (12%)
closed on clock  40 / 75  (53%)
```

**Only 12% of trades ever reached the target.** The 25-minute clock closed more
than half of them wherever price happened to be. So the realised payoff was not
1 : 1.5 but **1.23 : 1**, which needs a **44.9%** win rate to break even. The
system delivered 38.7%.

The gap is 6.2 points of win rate — and it is a *geometry* problem, not a
signal-strength problem. A target the clock never lets you reach is not a target.

### What is *not* the explanation

Measured, not assumed:

- **Commission.** $0.60 round-turn, not the $2.60 the paper simulator charged.
  18% of the friction. Real transaction cost is $3.39/trade, and 82% of that is
  slippage — mostly stop slippage (mean $3.60, tail to $29).
- **Entry slippage is structural, not noise.** The executor anchors the bracket
  to the reference ask/bid and then fills at market, so any difference between
  reference and fill shifts the *real* distance to target 1:1
  (`src/agus_ejecutor_of_mgc.py`). One tick, every trade.
- **Limit entries would be worse.** The obvious fix is measured as harmful:
  adverse selection removes the trades that never come back — the good ones.
- **Gross P&L before any cost was already negative.** Costs made a losing system
  lose faster. They did not cause the loss.

---

## Repository layout

```
src/         the system — executor, paper simulator, backtests
data/        raw evidence: 34,276 one-minute bars with order flow,
             7,657 logged signals, the complete live trade ledger
analysis/    scripts that regenerate every published figure
docs/        architecture, results, and the research record
```

- [docs/RESULTS.md](docs/RESULTS.md) — every number, and how it was obtained
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the system is built
- [docs/METHOD.md](docs/METHOD.md) — hypotheses tested and killed, and the
  measurement traps that produced false positives along the way

## Status

Not running. Halted 30 July 2026. Nothing here is a recommendation to trade, and
the results argue against deploying this system as it stands.

The engineering is reusable; the strategy is not yet profitable.
