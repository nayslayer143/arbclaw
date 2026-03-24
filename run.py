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
import learner

LOG_FILE = Path(__file__).parent / "runs.log"
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


def run():
    start = time.time()
    ts = datetime.datetime.utcnow().isoformat()

    # 1. Fetch markets
    markets = feed.fetch()

    # 2. Check stops on existing positions + log resolved trades for learning
    prices = {m["market_id"]: m for m in markets}
    closed = wallet.check_stops(prices)

    # Log each closed trade for the learning loop
    if closed > 0:
        try:
            import sqlite3
            conn = sqlite3.connect(str(Path(__file__).parent / "arbclaw.db"))
            conn.row_factory = sqlite3.Row
            recent = conn.execute("""
                SELECT market_id, question, direction, entry_price, exit_price, pnl,
                       expected_edge, status
                FROM positions WHERE status != 'open'
                ORDER BY closed_at DESC LIMIT ?
            """, (closed,)).fetchall()
            for r in recent:
                learner.log_trade(
                    r["market_id"], r["question"], r["direction"],
                    r["entry_price"], r["exit_price"] or r["entry_price"],
                    r["expected_edge"] or 0, r["pnl"] or 0, r["status"],
                )
            conn.close()
        except Exception as e:
            print(f"[arbclaw] Learner log error: {e}")

    # 3. Scan for arb signals
    balance = wallet.get_balance()
    signals = arb_strategy.scan(markets, balance)

    # 4. Execute signals -- skip markets with existing open positions
    MAX_TRADES_PER_RUN = 5
    open_ids = wallet.get_open_market_ids()
    trades_made = 0
    for sig in signals:
        if trades_made >= MAX_TRADES_PER_RUN:
            break
        if sig.market_id in open_ids:
            continue
        # Skip if balance is too low
        if wallet.get_balance() < sig.size_usd:
            continue
        pos_id = wallet.open_position(sig)
        if pos_id:
            open_ids.add(sig.market_id)
            trades_made += 1

    # 5. Record daily snapshot
    wallet.record_daily()

    # 6. Run learning loop (adjust thresholds based on results)
    try:
        thresholds = learner.learn()
        if thresholds:
            learned_summary = learner.get_summary()
        else:
            learned_summary = ""
    except Exception as e:
        learned_summary = f"learn error: {e}"

    # 7. Log
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

    # Detailed log to daily file
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    daily_log = LOGS_DIR / f"arbclaw-{today}.log"
    with open(daily_log, "a") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"Run: {ts}\n")
        f.write(log_line)
        if learned_summary:
            f.write(f"\n{learned_summary}\n")
        f.write(f"{'='*60}\n")


if __name__ == "__main__":
    run()
