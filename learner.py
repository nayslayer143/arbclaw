#!/usr/bin/env python3
"""
ArbClaw learning loop — tracks what works, adjusts thresholds per market category.

After each resolved trade:
  1. Categorize by market type (crypto_bracket, crypto_15m, sports, finance, cpi, weather, other)
  2. Log gap size, entry price, direction, P&L
  3. Compute rolling win rate + avg P&L per category

After N trades:
  4. Increase MIN_GAP for categories with <30% win rate
  5. Decrease MIN_GAP for categories with >60% win rate
  6. Blacklist categories with <20% win rate over 10+ trades

The scan() function in arb_strategy.py reads these thresholds.
"""
import json
import sqlite3
import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "arbclaw.db"
THRESHOLDS_FILE = Path(__file__).parent / "learned_thresholds.json"

# Defaults
DEFAULT_MIN_EDGE = 0.005
LEARN_AFTER_N_TRADES = 5  # re-evaluate after this many resolved trades per category
BLACKLIST_THRESHOLD = 0.20  # blacklist below 20% win rate
TIGHTEN_THRESHOLD = 0.30   # increase min_edge below 30% WR
LOOSEN_THRESHOLD = 0.60    # decrease min_edge above 60% WR
EDGE_STEP = 0.005          # how much to adjust per learning cycle


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS trade_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        market_id TEXT,
        question TEXT,
        category TEXT,
        direction TEXT,
        entry_price REAL,
        exit_price REAL,
        gap_size REAL,
        pnl REAL,
        status TEXT,
        resolved_at TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS category_stats (
        category TEXT PRIMARY KEY,
        total_trades INTEGER DEFAULT 0,
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        win_rate REAL DEFAULT 0,
        avg_pnl REAL DEFAULT 0,
        total_pnl REAL DEFAULT 0,
        current_min_edge REAL,
        blacklisted INTEGER DEFAULT 0,
        updated_at TEXT
    )""")
    return conn


def categorize(market_id: str, question: str) -> str:
    """Categorize a market for learning purposes."""
    mid = (market_id or "").upper()
    q = (question or "").lower()

    if "15m" in mid or "15 min" in q:
        return "crypto_15m"
    if any(k in mid for k in ["KXBTC", "KXETH", "KXDOGE", "KXBNB", "KXADA", "KXBCH"]):
        return "crypto_bracket"
    if any(k in mid for k in ["KXNBA", "KXMLB", "KXNFL", "KXNCAA", "KXSOCCER"]):
        return "sports"
    if "cpi" in q or "inflation" in q:
        return "cpi"
    if any(k in q for k in ["treasury", "yield", "usd/jpy", "gold", "silver"]):
        return "finance"
    if any(k in q for k in ["temperature", "weather", "hurricane"]):
        return "weather"
    if "pope" in q:
        return "politics"
    if "president" in q or "election" in q or "trump" in q:
        return "politics"
    return "other"


def log_trade(market_id, question, direction, entry_price, exit_price, gap_size, pnl, status):
    """Log a resolved trade for learning."""
    cat = categorize(market_id, question)
    conn = _get_conn()
    conn.execute("""
        INSERT INTO trade_log (market_id, question, category, direction, entry_price,
                               exit_price, gap_size, pnl, status, resolved_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (market_id, question, cat, direction, entry_price, exit_price,
          gap_size, pnl, status, datetime.datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()


def learn():
    """Re-evaluate thresholds based on accumulated trade data."""
    conn = _get_conn()

    # Get stats per category
    rows = conn.execute("""
        SELECT category,
               COUNT(*) as total,
               SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losses,
               AVG(pnl) as avg_pnl,
               SUM(pnl) as total_pnl
        FROM trade_log
        GROUP BY category
    """).fetchall()

    thresholds = load_thresholds()
    now = datetime.datetime.utcnow().isoformat()

    for r in rows:
        cat = r["category"]
        total = r["total"]
        wins = r["wins"]
        wr = wins / total if total > 0 else 0
        current_edge = thresholds.get(cat, {}).get("min_edge", DEFAULT_MIN_EDGE)
        blacklisted = False

        if total >= LEARN_AFTER_N_TRADES:
            if wr < BLACKLIST_THRESHOLD:
                blacklisted = True
                print(f"[learner] BLACKLIST {cat}: {wr:.0%} WR over {total} trades")
            elif wr < TIGHTEN_THRESHOLD:
                current_edge = min(current_edge + EDGE_STEP, 0.10)
                print(f"[learner] TIGHTEN {cat}: WR={wr:.0%}, new min_edge={current_edge:.3f}")
            elif wr > LOOSEN_THRESHOLD:
                current_edge = max(current_edge - EDGE_STEP, 0.001)
                print(f"[learner] LOOSEN {cat}: WR={wr:.0%}, new min_edge={current_edge:.3f}")
            else:
                print(f"[learner] HOLD {cat}: WR={wr:.0%}, min_edge={current_edge:.3f}")

        thresholds[cat] = {
            "min_edge": current_edge,
            "blacklisted": blacklisted,
            "win_rate": wr,
            "total_trades": total,
            "total_pnl": r["total_pnl"],
        }

        # Update DB
        conn.execute("""
            INSERT OR REPLACE INTO category_stats
            (category, total_trades, wins, losses, win_rate, avg_pnl, total_pnl,
             current_min_edge, blacklisted, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (cat, total, wins, r["losses"], wr, r["avg_pnl"], r["total_pnl"],
              current_edge, 1 if blacklisted else 0, now))

    conn.commit()
    conn.close()
    save_thresholds(thresholds)
    return thresholds


def load_thresholds() -> dict:
    if THRESHOLDS_FILE.exists():
        try:
            return json.loads(THRESHOLDS_FILE.read_text())
        except Exception:
            pass
    return {}


def save_thresholds(thresholds: dict):
    THRESHOLDS_FILE.write_text(json.dumps(thresholds, indent=2))


def get_min_edge(category: str) -> float:
    """Get the learned minimum edge for a category."""
    thresholds = load_thresholds()
    cat_data = thresholds.get(category, {})
    if cat_data.get("blacklisted"):
        return 999.0  # effectively blocks all trades
    return cat_data.get("min_edge", DEFAULT_MIN_EDGE)


def is_blacklisted(category: str) -> bool:
    thresholds = load_thresholds()
    return thresholds.get(category, {}).get("blacklisted", False)


def get_summary() -> str:
    """Human-readable summary of learned state."""
    thresholds = load_thresholds()
    if not thresholds:
        return "No learning data yet."
    lines = ["Category Performance:"]
    for cat, data in sorted(thresholds.items(), key=lambda x: x[1].get("total_pnl", 0)):
        status = "BLOCKED" if data.get("blacklisted") else f"edge>={data.get('min_edge', 0):.3f}"
        lines.append(
            f"  {cat:18s} WR={data.get('win_rate', 0):.0%} "
            f"trades={data.get('total_trades', 0)} "
            f"PnL=${data.get('total_pnl', 0):.2f} [{status}]"
        )
    return "\n".join(lines)
