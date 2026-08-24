# Method: what was tested, what died, and the traps that faked results

The value in this repository is not the strategy. It is the record of what was
measured, because most of it came back negative and that is expensive knowledge.

## Hypotheses killed with data

| Hypothesis | Verdict | Evidence |
|---|---|---|
| Micro-scalp, $5 target, guess the next seconds | dead | PF 0.10–0.39 across every signal variant. The signal was irrelevant: at $2.60 commission on a $5 target, break-even needs ~76% directional accuracy. Order flow gives ~50%. |
| Quality score ≥ 78 as an entry gate | dead, inverted | Q ≥ 78 went 0-for-6; Q < 70 won 71%. The gate was removed, not tuned. |
| Expansion filter (cumulative-delta momentum) | dead | n=227. Threshold sweep non-monotonic and sign-flipping. Permutation test (20,000 shuffles) p=0.46, p=0.95 after correcting for 5 comparisons. Bootstrap CI [−$28, +$15] per trade. In-sample +$22.13/trade, out-of-sample −$23.30. |
| "Take every signal, not only the A+ ones" | dead | Raw 397 signals = +$7,926. Simulated one-at-a-time = **−$1,883** (61 trades, 32% WR). |
| Price-action exhaustion | dead | tested, no edge |
| Efficiency-ratio regime detector | dead | did not beat the moving-average regime it was meant to replace |
| London breakout | dead | PF 0.77 |
| MNQ (index futures), price and order flow | dead | no edge in either |
| Absorption / imbalance signals | dead | lose money alone once costs apply; only divergence survived |
| Limit entries to avoid slippage | dead | adverse selection: filters out the trades that never come back, i.e. the winners. Costs $1.01–$1.62/trade more than market entry, and raises max drawdown from $654 to $722. |

One thing survived, and it is not tradeable on its own: **cumulative-delta
momentum predicts move *magnitude*** — P(move ≥ 9 points in 25 min) rises from a
42.6% base to 56.9% at momentum ≥ 150 (n=3,306, 95% CI 55.2–58.6), and it holds
out-of-sample. It does **not** predict *direction* (47.6% same-sign, i.e.
nothing). Knowing something will move without knowing which way does not pick a
side. It could size a target; it cannot choose one.

## Measurement traps that produced false results

Each of these produced a number that looked real and was not.

**1. The overlap mirage — the expensive one.**
Signals fire every 30 minutes. On a trending day, ten of them are the same idea,
and each is scored against the same market move. The raw sum counts one move ten
times.

```
week      raw       one-at-a-time    inflation
W27    +$4,738         -$660           -7.2x     <- "the $4k week"
W29    +$4,134         -$602           -6.9x
W30    +$2,646         -$252          -10.5x
```

Three separate weeks that read as strongly profitable were losing weeks. With
one contract you can hold one position; any accounting that does not enforce
that is fiction. **Every P&L figure in this repository is simulated
one-trade-at-a-time.**

**2. Test rows inside the production ledger.**
Four unit-test fixtures (`entry 4000.0`, one timestamped `t`) sat in the live
ledger, worth +$157 — enough to move the headline from −$430 to −$273 and make a
clearly failing system look near break-even. Filtered in
`analysis/live_results.py`; a validator on write would have been better.

**3. A decision sample of thirteen.**
Dry-run went 9-4 (69%). Live went 29-46 (38.7%). At the true rate, 9-of-13 or
better arrives 2.6% of the time by chance — rare, but thirteen trades is small
enough that rare things decide the outcome.

**4. A cost model that was wrong in both directions.**
The simulator charged a flat $2.60/trade. Reality: $0.60 commission, and total
friction $3.39 concentrated in slippage — overcharging targets, undercharging
stops. Paper and live were therefore never measuring the same system.

**5. Circular arithmetic dressed up as a cost.**
An early pass computed "$4.22/trade of cost" as the gap between actual P&L and
what the trades *would* have made closing exactly at stop or target. That is not
a cost — it is the distance to a world where the 25-minute timeout does not
exist. It reproduces as `(32×90 − 47×60 + 273.20)/79` to the cent, and it was
built on the contaminated 79-trade sample. Any metric derived from a
counterfactual needs the counterfactual stated out loud.

**6. A timezone shift disguised as a strategy change.**
The trading window was moved to the London session on 22 July. The following
week was red. The window had been validated on data timestamped UTC, then
applied as local time — 07:00–16:00 measured, 02:00–11:00 traded. The system
was run outside the hours it was tested on, and the loss was nearly attributed
to market regime instead.

## The rules that came out of this

1. Every P&L figure simulated one trade at a time. No exceptions.
2. No real money before ~50 closed trades.
3. Costs modelled by exit type, from reconciled fills — never a flat assumption.
4. Any parameter chosen by looking at the whole period is checked out-of-sample
   before it is believed. Most do not survive.
5. Production ledgers reject rows that fail a timestamp check.
6. State the timezone of every window, at measurement and at execution.
7. A grid search always yields a best cell. A plateau is a signal; a lone peak
   is noise.
