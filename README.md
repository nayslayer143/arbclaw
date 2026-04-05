---
project: arbclaw
type: trading-agent
stack: [python, sqlite]
status: active
github: https://github.com/nayslayer143/arbclaw
gitlab: https://gitlab.com/jordan291/arbclaw
instance: ArbClaw
parent: openclaw
children: []
---

# ArbClaw

Minimal arbitrage bot — the speed and execution baseline for the OpenClaw ecosystem.

## What This Is

ArbClaw is a stripped-down arb execution agent. It exists to establish a performance baseline that RivalClaw and other trading agents are compared against. The simplest possible Polymarket arb bot — no AI, no agents, no dashboard. Just math. The control group for whether OpenClaw's architecture actually helps or hurts arb execution speed.

## Architecture

- **Minimal surface area** — smallest possible codebase for arb detection and execution
- **Metrics-compatible** — exports daily JSON matching the OpenClaw comparison contract
- **Sub-agent of Clawmpson** — runs within the OpenClaw orchestration layer

## Key Files

| File/Dir | Purpose |
|----------|---------|
| `CLAUDE.md` | Agent instructions (if exists) |
| `src/` | Core arbitrage logic |

## Quick Start

```bash
git clone https://github.com/nayslayer143/arbclaw.git
cd arbclaw
cat CLAUDE.md  # Architecture and constraints
```

## Related Projects

| Project | Relationship | Repo |
|---------|-------------|------|
| OpenClaw | Parent — orchestrator | [GitHub](https://github.com/nayslayer143/openclaw) |
| RivalClaw | Sibling — arb architecture comparison | [GitHub](https://github.com/nayslayer143/rivalclaw) |
| QuantumentalClaw | Sibling — signal fusion | [GitHub](https://github.com/nayslayer143/quantumentalclaw) |

## License

Private project.
