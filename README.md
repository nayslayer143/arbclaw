# ArbClaw

Lean arbitrage validation experiment — 14-day paper trading test to determine whether Clawmpson's full trading stack introduces execution lag on prediction market arb opportunities.

## Hypothesis

Clawmpson runs 5 strategies, 5 feeds, LLM analysis, and a graduation engine on a 30-minute cron cycle. For cross-outcome arb where mispricing windows close in minutes, that machinery may cost alpha through execution lag. ArbClaw tests this by running a single strategy on a 5-minute cycle with zero overhead.

## Architecture

| File | Purpose | Lines |
|------|---------|-------|
| `feed.py` | Polymarket gamma API fetch + SQLite cache | 112 |
| `arb_strategy.py` | Cross-outcome arb detection + Kelly sizing | 77 |
| `wallet.py` | Paper wallet with signal-to-trade latency tracking | 192 |
| `run.py` | Entry point chaining feed -> strategy -> wallet | 60 |

**Total: 441 lines.** No LLM. No OSINT. No momentum. No agents. No dashboard.

## Strategy

Pure cross-outcome arb only: detect when YES + NO prices for the same Polymarket market sum to less than 1.0 after accounting for 2% taker fees per leg. Kelly criterion sizes positions. Buy the underpriced side.

## Paper Wallet Rules

- Starting capital: $1,000
- Max position: 10% of balance
- Stop-loss: -20%
- Take-profit: +50%
- Key metric: `signal_to_trade_latency_ms`

## Cron

Runs every 5 minutes (vs Clawmpson's 30-minute cycle).

## Comparison (after 14 days)

| Metric | ArbClaw Target | Clawmpson Baseline |
|--------|---------------|-------------------|
| Signal-to-trade latency | <30s | ~30min cycle |
| Win rate | Track | Track |
| Edge capture rate | Track | Track |
| Total PnL | Track | Track |

## Outcome

- If ArbClaw captures more edge -> build fast-path mode into Clawmpson
- If Clawmpson wins anyway -> architecture validated, delete ArbClaw
- Either way, we learn something

## Daily Reports

Auto-generated daily performance reports are posted to `daily/` by cron at 11:50 PM.

## Status

**Experiment start:** 2026-03-24
**Experiment end:** 2026-04-07
