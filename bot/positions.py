"""SQLite-backed open position tracker for matching Discord exits."""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Position:
    contract_key: str
    symbol: str
    option_type: str
    strike: float
    expiration: str
    quantity: int
    entry_price: float | None
    opened_at: float
    discord_message_id: str | None
    webull_order_id: str | None


class PositionStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS positions (
                    contract_key TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    option_type TEXT NOT NULL,
                    strike REAL NOT NULL,
                    expiration TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    entry_price REAL,
                    opened_at REAL NOT NULL,
                    discord_message_id TEXT,
                    webull_order_id TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_messages (
                    message_id TEXT PRIMARY KEY,
                    processed_at REAL NOT NULL
                )
                """
            )
            conn.commit()

    def already_processed(self, message_id: str) -> bool:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_messages WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            return row is not None

    def mark_processed(self, message_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO processed_messages(message_id, processed_at) VALUES (?, ?)",
                (message_id, time.time()),
            )
            conn.commit()

    def upsert_open(
        self,
        *,
        contract_key: str,
        symbol: str,
        option_type: str,
        strike: float,
        expiration: str,
        quantity: int,
        entry_price: float | None,
        discord_message_id: str | None,
        webull_order_id: str | None,
    ) -> None:
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT quantity FROM positions WHERE contract_key = ?",
                (contract_key,),
            ).fetchone()
            if existing:
                new_qty = int(existing["quantity"]) + quantity
                conn.execute(
                    """
                    UPDATE positions
                    SET quantity = ?, entry_price = COALESCE(?, entry_price),
                        discord_message_id = COALESCE(?, discord_message_id),
                        webull_order_id = COALESCE(?, webull_order_id)
                    WHERE contract_key = ?
                    """,
                    (
                        new_qty,
                        entry_price,
                        discord_message_id,
                        webull_order_id,
                        contract_key,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO positions(
                        contract_key, symbol, option_type, strike, expiration,
                        quantity, entry_price, opened_at, discord_message_id, webull_order_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        contract_key,
                        symbol,
                        option_type,
                        strike,
                        expiration,
                        quantity,
                        entry_price,
                        time.time(),
                        discord_message_id,
                        webull_order_id,
                    ),
                )
            conn.commit()

    def reduce_or_close(self, contract_key: str, quantity: int) -> Position | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM positions WHERE contract_key = ?",
                (contract_key,),
            ).fetchone()
            if not row:
                return None
            pos = Position(**dict(row))
            remaining = pos.quantity - quantity
            if remaining <= 0:
                conn.execute(
                    "DELETE FROM positions WHERE contract_key = ?", (contract_key,)
                )
            else:
                conn.execute(
                    "UPDATE positions SET quantity = ? WHERE contract_key = ?",
                    (remaining, contract_key),
                )
            conn.commit()
            return pos

    def get(self, contract_key: str) -> Position | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM positions WHERE contract_key = ?",
                (contract_key,),
            ).fetchone()
            return Position(**dict(row)) if row else None

    def list_open(self) -> list[Position]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM positions ORDER BY opened_at DESC"
            ).fetchall()
            return [Position(**dict(r)) for r in rows]
