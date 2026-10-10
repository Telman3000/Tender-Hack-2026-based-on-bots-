from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.config import DB_PATH, PROCESSED_DIR


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ktru (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            okpd2 TEXT,
            domain TEXT,
            okei TEXT,
            required_json TEXT,
            chars_json TEXT,
            name_norm TEXT,
            version INTEGER DEFAULT 0,
            update_date TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ktru_domain ON ktru(domain);
        CREATE INDEX IF NOT EXISTS idx_ktru_name ON ktru(name_norm);

        CREATE TABLE IF NOT EXISTS portal_ste (
            ste_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            domain TEXT,
            manufacturer TEXT,
            chars_raw TEXT,
            name_norm TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ste_domain ON portal_ste(domain);
        CREATE INDEX IF NOT EXISTS idx_ste_name ON portal_ste(name_norm);

        CREATE TABLE IF NOT EXISTS portal_chars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT,
            category TEXT,
            kpgz_code TEXT,
            char_name TEXT,
            char_type TEXT,
            unit TEXT,
            values_sample TEXT,
            UNIQUE(domain, category, char_name)
        );
        CREATE INDEX IF NOT EXISTS idx_pchars_name ON portal_chars(char_name);

        CREATE TABLE IF NOT EXISTS char_canon (
            alias TEXT PRIMARY KEY,
            canonical TEXT NOT NULL,
            source TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ktru_char_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            char_name TEXT NOT NULL,
            required INTEGER DEFAULT 0,
            kind TEXT,            -- enum | number | range | any
            value TEXT,
            vmin REAL,
            vmax REAL,
            min_op TEXT,
            max_op TEXT,
            unit TEXT,
            okei_code TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_kcv_code ON ktru_char_values(code);

        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    conn.commit()


def set_meta(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value),
    )
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return row["value"]


def db_ready(db_path: Path | None = None) -> bool:
    path = db_path or DB_PATH
    if not path.exists():
        return False
    conn = connect(path)
    try:
        n = conn.execute("SELECT COUNT(*) AS c FROM ktru").fetchone()["c"]
        return n > 0
    except Exception:
        return False
    finally:
        conn.close()


def ensure_processed_dir() -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    return PROCESSED_DIR
