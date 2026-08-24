# Ciel — the other strategy

**This is not the system that lost money.** Two separate strategies live in this
repository and they have opposite profiles:

| | OF-MGC | Ciel |
|---|---|---|
| what | order-flow divergence scalp | trend-following + range fade |
| holding time | 25 minutes | up to 8 hours |
| trades per day | ~9 | ~1.2 |
| traded real money | yes | **never** |
| expectancy / trade | **−$5.74** (live) | **+$12.97** (backtest) |
| win rate | 38.7% | 58.4% |
| profit factor | < 1 | 1.17 |

OF-MGC was deployed and lost $430. Ciel was shelved *before* deployment on the
grounds that a micro gold contract is too coarse an instrument for a $25k
account — its stops are 15–40 points ($150–400), which on $25k is three bullets.
That reasoning is why it is being reconsidered for a $150k account.

## The measured edge

`src/backtest_combo_eval.py` over GC=F, two years, one trade at a time,
$5.00/trade cost deducted:

```
TREND   161 trades   55.9% WR   +$3,364   PF 1.20   +$20.90/trade
FADE    214 trades   60.3% WR   +$1,498   PF 1.13    +$7.00/trade
COMBO   375 trades   58.4% WR   +$4,863   PF 1.17   +$12.97/trade
```

Positive in each year independently — the test OF-MGC failed:

| year | trades | win rate | net |
|---|---:|---:|---:|
| 2024 | 133 | 56.4% | +$803 |
| 2025 | 143 | 62.2% | +$2,508 |
| 2026 | 99 | 55.6% | +$1,552 |

The two halves are regime-exclusive: trend only fires on directional days, fade
only on ranging ones, so they never compete for the same capital and the combined
figure is not double-counting. The engine checks stop before target within the
same bar, which is the conservative resolution.

## Can it pass a $150k evaluation?

Target +$9,000, max loss $4,500 end-of-day trailing. The single-path backtest
says "passes at 2 contracts in 11.5 months" — but that is **one draw**.
Bootstrapping the real daily distribution over 6,000 runs gives the honest answer:

| plan | P(pass) | median months |
|---|---:|---:|
| 1 contract fixed | 58.4% | 15.8 |
| **1 → 2 after a $1,500 cushion** | **58.8%** | **9.5** |
| 2 contracts fixed | 50.6% | 6.5 |
| 3 contracts fixed | 40.4% | 3.1 |
| 5 contracts fixed | 33.1% | 1.3 |

**Roughly 59%, in roughly nine months.** More size buys speed and costs
probability — the target/drawdown ratio is fixed by the strategy, so contracts
only decide how fast the outcome arrives.

The ladder is the one free improvement found: same probability as staying at one
contract, but it arrives in nine months instead of sixteen. Early variance
cannot kill the account because size is small; later variance is absorbed by
realised profit.

### What does not work here

A daily loss brake — the guard that measurably helped OF-MGC (PF 1.15 → 1.21) —
does almost nothing for Ciel. At $450 and $600 it triggers on **zero of 317
days**. The reason is structural: Ciel takes 1.2 trades per day, so a daily
brake has no subsequent trades to prevent. It cannot stop the trade that
breaches it, only the ones after — and there usually are none.

A $300 brake does help (58.4% → 58.7%, and raw P&L +$4,863 → +$5,744 by cutting
12 bad days), but it is a small effect, not a fix.

## What this is and is not

**Is:** a strategy with positive expectancy, consistent across three years, whose
two components work independently, with a defined plan giving it a ~59% chance
at a $150k evaluation over about nine months.

**Is not:** proven. Ciel has never filled a real order. Specifically:

- The backtest runs on GC=F hourly bars from Yahoo, a proxy for MGC. Intrabar
  path is unknown; the resolution is conservative but it is still an assumption.
- The live forward test of its gated (A+) configuration returned **−$231 over 7
  trades**. That is a sample far too small to conclude anything, and it is also
  a more restrictive configuration than the one backtested here. It is recorded
  because omitting it would be dishonest, not because it is decisive.
- Cost is a flat $5.00/trade. Measured slippage elsewhere in this project had a
  fat tail (worst $29 on a 6-point stop). Ciel's stops are wider so the
  proportional impact is smaller, but the tail was not modelled.
- 59% is a coin flip with an edge. It is a bet with favourable odds over a long
  horizon, not a system that reliably delivers.

**The honest sentence:** the edge appears real and survives the tests that killed
the other strategy, but it has never met a real fill, and the plan is a
nine-month bet at rather better than even odds.
