#!/usr/bin/env python3
"""ArbClaw paper wallet -- SQLite-backed with signal-to-trade latency tracking."""
import sqlite3
import time
import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "arbclaw.db"
STARTING_CAPITAL = 1000.0
MAX_POSITION_PCT = 0.10
STOP_LOSS_PCT = -0.20
TAKE_PROFIT_PCT = 0.50


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT NOT NULL,
            question TEXT,
            direction TEXT,
            entry_price REAL,
            current_price REAL,
            shares REAL,
            amount_usd REAL,
            expected_edge REAL,
            signal_timestamp REAL,
            trade_timestamp REAL,
            signal_to_trade_latency_ms REAL,
            status TEXT DEFAULT 'open',
            opened_at TEXT,
            closed_at TEXT,
            exit_price REAL,
            pnl REAL
        );
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER,
            market_id TEXT,
            direction TEXT,
            entry_price REAL,
            exit_price REAL,
            shares REAL,
            pnl REAL,
            expected_edge REAL,
            signal_to_trade_latency_ms REAL,
            opened_at TEXT,
            closed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS daily_pnl (
            date TEXT PRIMARY KEY,
            balance REAL,
            total_pnl REAL,
            win_count INTEGER,
            loss_count INTEGER,
            avg_latency_ms REAL,
            edge_capture_rate REAL
        );
    """)
    return conn


def get_balance():
    conn = _get_conn()
    try:
        total_pnl = conn.execute("SELECT COALESCE(SUM(pnl), 0) FROM trades").fetchone()[0]
        locked = conn.execute("SELECT COALESCE(SUM(amount_usd), 0) FROM positions WHERE status = 'open'").fetchone()[0]
        return STARTING_CAPITAL + total_pnl - locked
    finally:
        conn.close()


def get_open_market_ids():
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT DISTINCT market_id FROM positions WHERE status = 'open'").fetchall()
        return {r["market_id"] for r in rows}
    finally:
        conn.close()


def open_position(signal):
    """Open a paper position from a Signal. Returns position id."""
    now = time.time()
    now_iso = datetime.datetime.utcnow().isoformat()
    latency_ms = (now - signal.timestamp) * 1000

    balance = get_balance()
    size = min(signal.size_usd, MAX_POSITION_PCT * balance)
    if size <= 0:
        return None
    shares = size / signal.entry_price if signal.entry_price > 0 else 0

    conn = _get_conn()
    try:
        cur = conn.execute("""
            INSERT INTO positions (market_id, question, direction, entry_price, current_price,
                shares, amount_usd, expected_edge, signal_timestamp, trade_timestamp,
                signal_to_trade_latency_ms, status, opened_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,'open',?)
        """, (signal.market_id, signal.question, signal.direction, signal.entry_price,
              signal.entry_price, shares, size, signal.expected_edge,
              signal.timestamp, now, latency_ms, now_iso))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def check_stops(current_prices):
    """Check stop-loss/take-profit on open positions. Returns count of closed positions."""
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT * FROM positions WHERE status = 'open'").fetchall()
        closed = 0
        for pos in rows:
            price_data = current_prices.get(pos["market_id"])
            if not price_data:
                continue

            current = price_data["yes_price"] if pos["direction"] == "YES" else price_data["no_price"]
            if not current or current <= 0:
                continue

            conn.execute("UPDATE positions SET current_price = ? WHERE id = ?", (current, pos["id"]))

            entry = pos["entry_price"]
            pnl_pct = (current - entry) / entry if entry > 0 else 0

            if pnl_pct <= STOP_LOSS_PCT or pnl_pct >= TAKE_PROFIT_PCT:
                pnl = (current - entry) * pos["shares"]
                now_iso = datetime.datetime.utcnow().isoformat()
                conn.execute(
                    "UPDATE positions SET status='closed', exit_price=?, pnl=?, closed_at=? WHERE id=?",
                    (current, pnl, now_iso, pos["id"]),
                )
                conn.execute("""
                    INSERT INTO trades (position_id, market_id, direction, entry_price, exit_price,
                        shares, pnl, expected_edge, signal_to_trade_latency_ms, opened_at, closed_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (pos["id"], pos["market_id"], pos["direction"], entry, current,
                      pos["shares"], pnl, pos["expected_edge"],
                      pos["signal_to_trade_latency_ms"], pos["opened_at"], now_iso))
                closed += 1

        conn.commit()
        return closed
    finally:
        conn.close()


def get_state():
    """Return current wallet state dict."""
    conn = _get_conn()
    try:
        balance = get_balance()
        open_count = conn.execute("SELECT COUNT(*) FROM positions WHERE status='open'").fetchone()[0]
        total_trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        wins = conn.execute("SELECT COUNT(*) FROM trades WHERE pnl > 0").fetchone()[0]
        avg_lat = conn.execute("SELECT AVG(signal_to_trade_latency_ms) FROM trades").fetchone()[0]
        total_expected = conn.execute("SELECT SUM(ABS(expected_edge * shares)) FROM trades").fetchone()[0] or 0
        total_realized = conn.execute("SELECT SUM(pnl) FROM trades").fetchone()[0] or 0
        ecr = total_realized / total_expected if total_expected > 0 else 0.0
        return {
            "balance": balance, "open_positions": open_count,
            "total_trades": total_trades,
            "win_rate": wins / total_trades if total_trades > 0 else 0.0,
            "avg_latency_ms": avg_lat or 0.0,
            "edge_capture_rate": ecr, "total_pnl": total_realized,
        }
    finally:
        conn.close()


def record_daily():
    """Record daily PnL snapshot."""
    state = get_state()
    today = datetime.date.today().isoformat()
    conn = _get_conn()
    try:
        wins = int(state["win_rate"] * state["total_trades"]) if state["total_trades"] > 0 else 0
        conn.execute("""
            INSERT OR REPLACE INTO daily_pnl (date, balance, total_pnl, win_count, loss_count, avg_latency_ms, edge_capture_rate)
            VALUES (?,?,?,?,?,?,?)
        """, (today, state["balance"], state["total_pnl"], wins,
              state["total_trades"] - wins, state["avg_latency_ms"], state["edge_capture_rate"]))
        conn.commit()
    finally:
        conn.close()
