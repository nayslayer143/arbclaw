#!/usr/bin/env python3
"""ArbClaw feed -- fetches Polymarket markets via gamma API, caches to SQLite."""
import json
import sqlite3
import datetime
import requests
from pathlib import Path

GAMMA_API = "https://gamma-api.polymarket.com/markets"
DB_PATH = Path(__file__).parent / "arbclaw.db"
MIN_VOLUME = 10_000


def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS market_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        market_id TEXT NOT NULL,
        question TEXT,
        yes_price REAL,
        no_price REAL,
        volume REAL,
        fetched_at TEXT
    )""")
    return conn


def _parse_json(val):
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (ValueError, TypeError):
            pass
    return []


def fetch():
    """Fetch active markets from Polymarket, cache to DB, return list of dicts."""
    now = datetime.datetime.utcnow().isoformat()
    try:
        resp = requests.get(
            GAMMA_API,
            params={"active": "true", "closed": "false", "limit": 100},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()
        markets_raw = raw if isinstance(raw, list) else raw.get("data", raw.get("markets", []))
    except Exception as e:
        print(f"[arbclaw/feed] API error: {e}")
        return []

    markets = []
    conn = _get_conn()
    try:
        for m in markets_raw:
            volume = float(m.get("volume", 0) or 0)
            if volume < MIN_VOLUME:
                continue

            yes_price = no_price = None
            outcome_prices = _parse_json(m.get("outcomePrices"))
            outcomes = _parse_json(m.get("outcomes"))
            if outcome_prices and outcomes:
                for label, price_str in zip(outcomes, outcome_prices):
                    try:
                        price = float(price_str)
                    except (ValueError, TypeError):
                        continue
                    if (label or "").lower() == "yes":
                        yes_price = price
                    elif (label or "").lower() == "no":
                        no_price = price

            if yes_price is None or no_price is None:
                for tok in (m.get("tokens") or []):
                    outcome = (tok.get("outcome") or "").upper()
                    try:
                        price = float(tok.get("price", 0) or 0)
                    except (ValueError, TypeError):
                        continue
                    if outcome == "YES":
                        yes_price = price
                    elif outcome == "NO":
                        no_price = price

            if yes_price is None or no_price is None:
                continue

            market_id = m.get("conditionId") or m.get("id") or ""
            question = m.get("question", "")
            if not market_id or not question:
                continue

            conn.execute(
                "INSERT INTO market_snapshots (market_id, question, yes_price, no_price, volume, fetched_at) VALUES (?,?,?,?,?,?)",
                (market_id, question, yes_price, no_price, volume, now),
            )
            markets.append({
                "market_id": market_id, "question": question,
                "yes_price": yes_price, "no_price": no_price, "volume": volume,
            })
        conn.commit()
    finally:
        conn.close()

    print(f"[arbclaw/feed] Fetched {len(markets)} markets")
    return markets
