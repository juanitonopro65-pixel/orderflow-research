# Going faster: the second market

Nine months to pass an evaluation is a long time to ask anyone to wait. This
documents the search for a faster route and what it actually costs.

## First, a correction

An earlier pass reported Ciel at "~59% probability in 9.5 months." That number
sampled only **days the strategy traded**, which silently assumes every calendar
day produces a trade. Ciel trades 317 of 511 calendar days. Modelled correctly,
with non-trading days included as zeros:

```
Ciel on gold alone, 1 contract:   18.6% probability, 18.9 months
Ciel on gold alone, 1->2 ladder:  38.6% probability, 13.1 months
```

Considerably worse. The correction matters more than the original figure did.

## Why more contracts cannot fix it

Speed is `target / daily edge`. Probability is driven by `daily edge / daily
volatility`. Adding contracts multiplies **both** edge and volatility, so it buys
speed and pays for it in probability — the ratio is untouched.

The only way to improve both at once is to raise edge *without* raising
volatility proportionally. Adding an **uncorrelated** market does exactly that:
edge adds linearly, volatility adds in quadrature.

## Searching for a second market

The Ciel engine was run unchanged on eight instruments. The stop clamp — the
original caps stop distance to 15–40 points on gold at $10/point — was expressed
as its dollar equivalent, $150–400 of risk, and converted back to points per
instrument. That preserves the volatility-aware sizing rather than removing it.

Verification that the port is faithful: gold reproduces the original exactly
(375 trades, 58.4% WR, +$4,863, PF 1.17, identical yearly split).

| market | trades | win rate | net | PF | 2024 / 2025 / 2026 |
|---|---:|---:|---:|---:|---|
| **Wheat (ZW)** | 511 | 65.4% | **+$28,031** | **1.77** | +16,479 / +7,031 / +4,521 |
| **Gold (MGC)** | 375 | 58.4% | +$4,863 | 1.17 | +803 / +2,508 / +1,552 |
| Silver | 383 | 60.8% | +$3,533 | 1.10 | negative in 2024 |
| Copper | 373 | 54.4% | +$1,048 | 1.03 | negative in 2025 |
| Crude, Nasdaq, S&P, NatGas | — | — | all negative | 0.74–0.86 | — |

Only gold and wheat are positive in all three years independently.

**Their daily P&L correlation is r = −0.004.** Independent, which is what makes
the combination work rather than just doubling exposure.

## The portfolio

| plan | P(pass) | median months |
|---|---:|---:|
| gold only, 1 contract | 18.6% | 18.9 |
| gold only, 1→2 ladder | 38.6% | 13.1 |
| **gold + wheat, 1 contract each** | **97.6%** | **6.5** |
| gold + wheat, 1→2 ladder | 88.5% | 3.8 |
| **gold + wheat, 2 contracts each** | **81.7%** | **2.8** |
| gold + wheat, 3 contracts each | 67.6% | 1.5 |

Contract sizing is practical at 1 contract each — this was checked, not assumed:

```
Wheat ZW    median ATR 3.00 pts -> stop 5.25 pts -> risk $262 per full contract
Gold MGC    median ATR 11.6 pts -> stop 20.3 pts -> risk $203 per micro
```

Both land inside the $150–400 band naturally. No micro wheat contract is needed,
and no fractional sizing is required.

## What is not established

Wheat has never been traded. Specifically:

- **The edge declines year over year**: +$16,479 → +$7,031 → +$4,521. 2024 is
  59% of the total. That decay is the single biggest reason not to size up on it.
  In mitigation, even the weakest wheat year (2026, +$4,521) is close to gold's
  entire two-year total.
- **Eight instruments were tested and the best one was selected.** That is the
  multiple-comparisons trap this project has documented before. Being positive in
  all three years independently is what separates this from a lucky draw, but it
  is not the same as out-of-sample confirmation.
- Cost is assumed flat at $5.00/trade. Wheat's liquidity in the traded window is
  adequate (6,700–11,900 contracts/hour, and the engine never touches the thin
  overnight session), but its slippage distribution has not been measured the way
  gold's was.
- Yahoo hourly bars, as everywhere else in this analysis.

**Before sizing on wheat:** paper-trade it forward against live fills for ~50
trades, as with any strategy here. The number that matters is whether the 2026
rate holds, not the 2024 one.

## The honest recommendation

The diversification result is the robust part: two uncorrelated markets improve
both speed and probability simultaneously, and that is arithmetic, not a
backtest artefact. The specific choice of wheat is a candidate, not a
conclusion.

If wheat validates forward, **2 contracts each — 82% in under three months** —
is the plan that answers the original objection. If it does not, gold alone is
an 18.6% proposition over nineteen months, and that is not worth anyone's
capital.
