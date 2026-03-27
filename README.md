# ArbClaw

The simplest possible Polymarket arb bot. 441 lines of Python. No AI, no agents, no dashboard. Just math.

I built this as a speed baseline for an experiment: my main system ([OpenClaw](https://gitlab.com/jordan291/openclaw)) has a lot of moving parts, and I wanted to know if all that architecture was actually slowing down arb execution. ArbClaw is the control group — what happens when you strip everything away and just run the arb logic?

## How it works

Every 5 minutes:
1. Fetch all active Polymarket markets
2. Check if YES + NO prices sum to less than 1.0 (after 2% taker fees per leg)
3. Size with Kelly criterion
4. Paper trade the underpriced side

That's it. Four files, one strategy, zero overhead.

| File | What it does | Lines |
|------|-------------|-------|
| `feed.py` | Polymarket API fetch + SQLite cache | 112 |
| `arb_strategy.py` | Cross-outcome arb detection + Kelly sizing | 77 |
| `wallet.py` | Paper wallet with latency tracking | 192 |
| `run.py` | Entry point | 60 |

## The experiment

Three systems running the same arb logic on the same machine:

| System | Complexity | Cycle |
|--------|-----------|-------|
| **ArbClaw** (this) | 4 files, 441 lines | 5 min |
| **RivalClaw** | Full architecture, arb only | 5 min |
| **Clawmpson** | Full system, 5 strategies | 30 min |

Key metric: `signal_to_trade_latency_ms` — how long from spotting an opportunity to placing the trade?

## Outcome logic

- If ArbClaw captures more edge → build a fast-path mode into Clawmpson
- If Clawmpson wins anyway → architecture validated, ArbClaw gets retired
- Either way, I learn something

## Status

Paper trading experiment running March 24 – April 7, 2026. Daily reports auto-generated in `daily/`.

Part of the [OpenClaw](https://gitlab.com/jordan291/openclaw) ecosystem.
