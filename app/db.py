from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from app.config import settings


def _connect() -> sqlite3.Connection:
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_key TEXT UNIQUE,
                status TEXT NOT NULL,
                source TEXT,
                total_count INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TEXT NOT NULL,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                rank INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                sctr REAL,
                perf_1d REAL,
                perf_5d REAL,
                perf_20d REAL,
                perf_60d REAL,
                rsi_14 REAL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(id)
            );

            CREATE INDEX IF NOT EXISTS idx_picks_run_id ON picks(run_id);
            CREATE INDEX IF NOT EXISTS idx_picks_symbol ON picks(symbol);
            CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);

            CREATE TABLE IF NOT EXISTS convert_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_key TEXT UNIQUE,
                source_text TEXT NOT NULL,
                status TEXT NOT NULL,
                total_symbols INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TEXT NOT NULL,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS convert_symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                source_url TEXT,
                image_path TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES convert_runs(id)
            );

            CREATE INDEX IF NOT EXISTS idx_convert_runs_created_at ON convert_runs(created_at);
            CREATE INDEX IF NOT EXISTS idx_convert_symbols_run_id ON convert_symbols(run_id);
            CREATE INDEX IF NOT EXISTS idx_convert_symbols_symbol ON convert_symbols(symbol);

            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL UNIQUE,
                source_url TEXT,
                image_path TEXT,
                added_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_watchlist_added_at ON watchlist(added_at);

            CREATE TABLE IF NOT EXISTS saved_lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                run_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES convert_runs(id)
            );

            CREATE TABLE IF NOT EXISTS saved_list_symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                saved_list_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(saved_list_id) REFERENCES saved_lists(id)
            );

            CREATE INDEX IF NOT EXISTS idx_saved_lists_created_at ON saved_lists(created_at);
            CREATE INDEX IF NOT EXISTS idx_saved_list_symbols_saved_list_id ON saved_list_symbols(saved_list_id);
            """
        )
        conn.commit()
    finally:
        conn.close()


def create_run(run_key: str, source: str) -> int:
    conn = _connect()
    now = datetime.utcnow().isoformat()
    try:
        conn.execute(
            "INSERT INTO runs(run_key, status, source, created_at) VALUES(?, 'running', ?, ?)",
            (run_key, source, now),
        )
        conn.commit()
        row = conn.execute("SELECT id FROM runs WHERE run_key=?", (run_key,)).fetchone()
        return int(row["id"])
    finally:
        conn.close()


def has_running_run() -> bool:
    conn = _connect()
    try:
        row = conn.execute("SELECT id FROM runs WHERE status='running' LIMIT 1").fetchone()
        return bool(row)
    finally:
        conn.close()


def save_picks(run_id: int, rows: list[dict[str, Any]]) -> None:
    conn = _connect()
    now = datetime.utcnow().isoformat()
    try:
        conn.execute("DELETE FROM picks WHERE run_id=?", (run_id,))
        conn.executemany(
            """
            INSERT INTO picks(
                run_id, rank, symbol, sctr, perf_1d, perf_5d, perf_20d, perf_60d, rsi_14, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    r["rank"],
                    r["symbol"],
                    r.get("sctr"),
                    r.get("perf_1d"),
                    r.get("perf_5d"),
                    r.get("perf_20d"),
                    r.get("perf_60d"),
                    r.get("rsi_14"),
                    now,
                )
                for r in rows
            ],
        )
        conn.commit()
    finally:
        conn.close()


def finish_run(run_id: int, status: str, total_count: int, error_message: str = "") -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE runs SET status=?, total_count=?, error_message=?, finished_at=? WHERE id=?",
            (status, total_count, error_message, datetime.utcnow().isoformat(), run_id),
        )
        conn.commit()
    finally:
        conn.close()


def latest_run() -> sqlite3.Row | None:
    conn = _connect()
    try:
        return conn.execute(
            "SELECT * FROM runs WHERE status='ok' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()


def latest_runs(limit: int = 20) -> list[sqlite3.Row]:
    conn = _connect()
    try:
        return conn.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()


def fetch_picks(
    run_id: int, q: str = "", offset: int = 0, limit: int = 50
) -> tuple[int, list[sqlite3.Row]]:
    conn = _connect()
    q = q.strip().upper()
    where = "WHERE run_id=?"
    params: list[Any] = [run_id]
    if q:
        where += " AND symbol LIKE ?"
        params.append(f"%{q}%")
    try:
        count = conn.execute(
            f"SELECT COUNT(*) AS n FROM picks {where}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"SELECT * FROM picks {where} ORDER BY rank ASC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return int(count), rows
    finally:
        conn.close()


def create_convert_run(run_key: str, source_text: str, symbols: list[str]) -> int:
    conn = _connect()
    now = datetime.utcnow().isoformat()
    try:
        cur = conn.execute(
            """
            INSERT INTO convert_runs(run_key, source_text, status, total_symbols, created_at)
            VALUES(?, ?, 'queued', ?, ?)
            """,
            (run_key, source_text, len(symbols), now),
        )
        run_id = int(cur.lastrowid)
        conn.executemany(
            """
            INSERT INTO convert_symbols(
                run_id, position, symbol, status, created_at, updated_at
            ) VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            [(run_id, index + 1, symbol, now, now) for index, symbol in enumerate(symbols)],
        )
        conn.commit()
        return run_id
    finally:
        conn.close()


def update_convert_run_status(run_id: int, status: str, error_message: str = "") -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE convert_runs SET status=?, error_message=? WHERE id=?",
            (status, error_message, run_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_convert_symbol_status(
    symbol_id: int,
    *,
    status: str,
    source_url: str | None = None,
    image_path: str | None = None,
    error_message: str | None = None,
) -> None:
    conn = _connect()
    now = datetime.utcnow().isoformat()
    try:
        conn.execute(
            """
            UPDATE convert_symbols
            SET status=?, source_url=COALESCE(?, source_url), image_path=COALESCE(?, image_path),
                error_message=?, updated_at=?
            WHERE id=?
            """,
            (status, source_url, image_path, error_message, now, symbol_id),
        )
        conn.commit()
    finally:
        conn.close()


def finish_convert_run(run_id: int, status: str, success_count: int, error_message: str = "") -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE convert_runs
            SET status=?, success_count=?, error_message=?, finished_at=?
            WHERE id=?
            """,
            (status, success_count, error_message, datetime.utcnow().isoformat(), run_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_convert_run(run_id: int) -> sqlite3.Row | None:
    conn = _connect()
    try:
        return conn.execute("SELECT * FROM convert_runs WHERE id=?", (run_id,)).fetchone()
    finally:
        conn.close()


def list_convert_runs(limit: int = 20) -> list[sqlite3.Row]:
    conn = _connect()
    try:
        return conn.execute(
            "SELECT * FROM convert_runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()


def list_convert_symbols(run_id: int) -> list[sqlite3.Row]:
    conn = _connect()
    try:
        return conn.execute(
            "SELECT * FROM convert_symbols WHERE run_id=? ORDER BY position ASC",
            (run_id,),
        ).fetchall()
    finally:
        conn.close()


def upsert_watchlist_symbol(symbol: str, source_url: str = "", image_path: str = "") -> int:
    conn = _connect()
    now = datetime.utcnow().isoformat()
    symbol = symbol.strip().upper()
    try:
        existing = conn.execute(
            "SELECT id FROM watchlist WHERE symbol=?",
            (symbol,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE watchlist
                SET source_url=?, image_path=?, updated_at=?
                WHERE symbol=?
                """,
                (source_url or None, image_path or None, now, symbol),
            )
            conn.commit()
            return int(existing["id"])

        cur = conn.execute(
            """
            INSERT INTO watchlist(symbol, source_url, image_path, added_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (symbol, source_url or None, image_path or None, now, now),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_watchlist_symbols() -> list[sqlite3.Row]:
    conn = _connect()
    try:
        return conn.execute(
            "SELECT * FROM watchlist ORDER BY added_at DESC, symbol ASC"
        ).fetchall()
    finally:
        conn.close()


def delete_watchlist_symbol(symbol: str) -> bool:
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM watchlist WHERE symbol=?",
            (symbol.strip().upper(),),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def create_saved_list(name: str, run_id: int, symbols: list[str]) -> int:
    conn = _connect()
    now = datetime.utcnow().isoformat()
    clean_name = name.strip()
    clean_symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
    try:
        cur = conn.execute(
            """
            INSERT INTO saved_lists(name, run_id, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (clean_name, run_id, now, now),
        )
        saved_list_id = int(cur.lastrowid)
        conn.executemany(
            """
            INSERT INTO saved_list_symbols(saved_list_id, position, symbol, created_at)
            VALUES (?, ?, ?, ?)
            """,
            [(saved_list_id, index + 1, symbol, now) for index, symbol in enumerate(clean_symbols)],
        )
        conn.commit()
        return saved_list_id
    finally:
        conn.close()


def list_saved_lists() -> list[sqlite3.Row]:
    conn = _connect()
    try:
        return conn.execute(
            """
            SELECT
                sl.*,
                COUNT(sls.id) AS symbol_count,
                GROUP_CONCAT(sls.symbol, ', ') AS symbols
            FROM saved_lists sl
            LEFT JOIN saved_list_symbols sls ON sls.saved_list_id = sl.id
            GROUP BY sl.id
            ORDER BY sl.created_at DESC, sl.id DESC
            """
        ).fetchall()
    finally:
        conn.close()


def get_saved_list(saved_list_id: int) -> sqlite3.Row | None:
    conn = _connect()
    try:
        return conn.execute(
            "SELECT * FROM saved_lists WHERE id=?",
            (saved_list_id,),
        ).fetchone()
    finally:
        conn.close()


def list_saved_list_symbols(saved_list_id: int) -> list[sqlite3.Row]:
    conn = _connect()
    try:
        return conn.execute(
            """
            SELECT * FROM saved_list_symbols
            WHERE saved_list_id=?
            ORDER BY position ASC, id ASC
            """,
            (saved_list_id,),
        ).fetchall()
    finally:
        conn.close()
