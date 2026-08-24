# Results

Everything here is produced by `python analysis/live_results.py` against
`data/of_exec_log.csv`. If a figure is not in that output, it is not claimed.

## Real money — 20 to 30 July 2026

```
trades        75
record        29W / 46L      win rate 38.7%
net P&L       $-430.20
avg win       $+51.08        (a full target would be +$90)
avg loss      $-41.56        (a full stop would be -$60)
exit reason   TIME(26m)=35, SL=26, TIME(25m)=5, TP=9
reached target      9/75  (12%)
closed on clock    40/75  (53%)
realised payoff     1.23 : 1
break-even win rate 44.9%     achieved 38.7%
```

Daily:

| date | trades | day | cumulative |
|---|---:|---:|---:|
| 2026-07-20 | 5 | +80.00 | +80.00 |
| 2026-07-21 | 4 | −20.60 | +59.40 |
| 2026-07-22 | 4 | −103.40 | −44.00 |
| 2026-07-23 | 9 | −16.40 | −60.40 |
| 2026-07-27 | 9 | +86.60 | +26.20 |
| 2026-07-28 | 12 | −157.20 | −131.00 |
| 2026-07-29 | 18 | −90.80 | −221.80 |
| 2026-07-30 | 14 | −208.40 | **−430.20** |

Note the trade count climbing as the account bled: 4 → 9 → 12 → 18. Nothing in
the code raised it; the market simply produced more qualifying signals on the
choppy days, which is exactly when this system is worst. Trade frequency was an
uncontrolled variable, and it correlated with losing.

## The decision sample that failed

```
DRY-RUN      13 trades   9W/4L   69.2%   +$288.00
LIVE         75 trades  29W/46L  38.7%   -$430.20
```

Thirteen trades were treated as sufficient evidence to risk money. At a true
38.7% win rate, going 9-and-4 or better across 13 trades happens 2.6% of
the time by chance — uncommon, but the sample was tiny enough that it did not
need to be common. The project's own notes had already recorded the rule
"do not crown the order flow on two trades." It was crowned on seventeen.

**Rule adopted afterwards: no real money before ~50 closed trades.**

## Cost structure

Measured from balance deltas on 70 reconciled trades, not assumed:

| component | per trade | share |
|---|---:|---:|
| stop slippage | $1.29 | 38% |
| entry slippage | $1.00 | 30% |
| commission | $0.60 | 18% |
| timeout exit slippage | $0.50 | 15% |
| **total** | **$3.39** | |

Commission is the smallest piece. The paper simulator charged a flat $2.60,
overcharging targets and undercharging stops — so paper and live were never
comparable in the way the go/no-go decision assumed.

Stop slippage has a fat tail: median $2.00, p90 $13, worst $29 (2.9 points
against a 6-point stop).

**Gross P&L before all costs was already negative.** Cost reduction alone cannot
rescue this system.

## Ciel at $150k — the capital question

A separate strategy (trend + range-fade combo) was shelved as "needs larger
capital." `src/backtest_150k_ciel.py` tests that claim against a $150k
evaluation account (target $9,000, max loss $4,500 end-of-day):

```
 micros  result      days   ~months   worst DD   target/DD
      1  NO REACH     317      15.1       1942        4.63
      2  PASS         241      11.5       2403        3.74
      3  PASS         226      10.8       3605        2.50
      5  DIES          51       2.4       4536        1.98
     12  DIES          14       0.7       4760        1.89
    100  "PASS"         2       0.1          0           -
```

Viable at 2 contracts, taking about eleven months. The 100-contract row is an
artefact — the first two days happened to be green — and is included precisely
because a grid like this always produces one, and treating it as a result is how
people talk themselves into leverage.

That is a backtest. Live, the same strategy's gated signals returned −$231
across 7 trades.

## Does a larger account fix this?

The natural intuition is that a $150k account has room a $25k account does not,
so the same system could finally make real money. That intuition is correct for
a system with positive expectancy and backwards for one without.

This system's measured expectancy is **−$5.74 per trade** at one contract.
Account size does not change expectancy; contract count multiplies it. Applying
the real daily results to a $150k evaluation (target +$9,000, max loss $4,500
end-of-day trailing):

| contracts | P&L over the 8 real days | worst drawdown | outcome |
|---:|---:|---:|---|
| 1 | −$430 | $510 | survives, losing |
| 2 | −$860 | $1,020 | survives, losing |
| 5 | −$2,151 | $2,551 | survives, losing |
| 10 | −$4,302 | $5,102 | **account dead in 8.4 days** |
| 20 | −$4,436 | $6,036 | **account dead in 4.2 days** |
| 50 | — | $6,200 | **account dead in 1.7 days** |

No contract count reaches +$9,000, because the per-trade edge is negative. Size
only changes how fast the account dies.

The $4,500 allowance is **room to lose**, not room to profit. Room to lose is
worth having only when you are expected to win — it buys survival through
variance, not through a negative mean.

The same pattern appears in `src/backtest_150k_ciel.py` on a strategy that *does*
backtest positive: it passes at 2 contracts, and dies at 5 and above. Scaling
multiplies drawdown at exactly the rate it multiplies profit, so the ratio of
target to drawdown is fixed by the strategy and cannot be bought with capital.

**What a larger account is genuinely for:** a strategy whose per-trade edge is
positive but whose instrument is too coarse to size properly on small capital.
That is a real problem and larger capital is its real solution. It is not this
system's problem. This system's problem is that the exit geometry gives back the
edge before the target is reached — and that has to be fixed at one contract,
and demonstrated over roughly fifty trades, before contract count is the
question worth asking.
