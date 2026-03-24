#!/usr/bin/env python3
"""ArbClaw runner -- chains feed -> strategy -> wallet. Entry point for cron."""
import sys
import time
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import feed
import arb_strategy
import wallet

LOG_FILE = Path(__file__).parent / "runs.log"


def run():
    start = time.time()
    ts = datetime.datetime.utcnow().isoformat()

    # 1. Fetch markets
    markets = feed.fetch()

    # 2. Check stops on existing positions
    prices = {m["market_id"]: m for m in markets}
    closed = wallet.check_stops(prices)

    # 3. Scan for arb signals
    balance = wallet.get_balance()
    signals = arb_strategy.scan(markets, balance)

    # 4. Execute signals -- skip markets with existing open positions
    open_ids = wallet.get_open_market_ids()
    trades_made = 0
    for sig in signals:
        if sig.market_id in open_ids:
            continue
        pos_id = wallet.open_position(sig)
        if pos_id:
            open_ids.add(sig.market_id)
            trades_made += 1

    # 5. Record daily snapshot
    wallet.record_daily()

    # 6. Log
    elapsed_ms = (time.time() - start) * 1000
    state = wallet.get_state()
    log_line = (
        f"{ts} | markets={len(markets)} signals={len(signals)} "
        f"trades={trades_made} closed={closed} latency={elapsed_ms:.0f}ms "
        f"bal=${state['balance']:.2f} pnl=${state['total_pnl']:.2f}\n"
    )
    with open(LOG_FILE, "a") as f:
        f.write(log_line)
    print(f"[arbclaw] {log_line.strip()}")


if __name__ == "__main__":
    run()
