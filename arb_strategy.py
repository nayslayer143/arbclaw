#!/usr/bin/env python3
"""ArbClaw strategy -- pure cross-outcome arb with Kelly sizing."""
import time
from dataclasses import dataclass

POLYMARKET_FEE_RATE = 0.02  # 2% taker fee per leg
MIN_EDGE = 0.005            # minimum edge after fees to trade (0.5%)
MAX_POSITION_PCT = 0.10     # 10% max position


@dataclass
class Signal:
    market_id: str
    question: str
    direction: str      # YES or NO (buy the underpriced side)
    size_usd: float
    expected_edge: float
    entry_price: float
    timestamp: float    # time.time() when signal was generated


def _fee(price):
    """Polymarket fee: 2% of min(price, 1-price)."""
    return POLYMARKET_FEE_RATE * min(price, 1.0 - price)


def _kelly(edge, entry_price, balance):
    """Kelly criterion for prediction markets. Returns dollar amount or None."""
    if entry_price <= 0 or entry_price >= 1:
        return None
    b = (1.0 / entry_price) - 1.0
    confidence = min(entry_price + edge, 0.99)
    kelly = (confidence * b - (1.0 - confidence)) / b
    if kelly <= 0:
        return None
    return min(kelly * balance, MAX_POSITION_PCT * balance)


def scan(markets, balance):
    """Scan markets for cross-outcome arb opportunities. Returns list of Signals.
    Uses learned thresholds per market category when available."""
    try:
        import learner
        use_learner = True
    except ImportError:
        use_learner = False

    signals = []
    now = time.time()

    for m in markets:
        yes_p = m.get("yes_price", 0) or 0
        no_p = m.get("no_price", 0) or 0
        if yes_p <= 0 or no_p <= 0:
            continue

        # Skip penny contracts
        if yes_p < 0.03 and no_p < 0.03:
            continue

        # Check learned blacklist/thresholds
        if use_learner:
            cat = learner.categorize(m.get("market_id", ""), m.get("question", ""))
            if learner.is_blacklisted(cat):
                continue
            min_edge = learner.get_min_edge(cat)
        else:
            min_edge = MIN_EDGE

        # Cost to buy both sides (1 share each) including fees
        total_cost = yes_p + no_p + _fee(yes_p) + _fee(no_p)
        edge = 1.0 - total_cost

        if edge <= min_edge:
            continue

        # Buy the underpriced side
        if no_p < (1.0 - yes_p):
            direction, entry_price = "NO", no_p
        else:
            direction, entry_price = "YES", yes_p

        amount = _kelly(edge, entry_price, balance)
        if amount is None:
            continue

        signals.append(Signal(
            market_id=m["market_id"],
            question=m.get("question", ""),
            direction=direction,
            size_usd=amount,
            expected_edge=edge,
            entry_price=entry_price,
            timestamp=now,
        ))

    return sorted(signals, key=lambda s: s.expected_edge, reverse=True)
