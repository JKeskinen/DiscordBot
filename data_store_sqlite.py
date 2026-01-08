"""Minimal SQLite data-store wrapper for the DiscordBotProject.
Provides a tiny API: `get_conn()`, `init_db(schema_path=None)`, `insert(table, row)` and `fetch_all(sql, params)`.
The goal is to be a drop-in utility to start switching callers from JSON files to SQLite.
"""
import os
import sqlite3
from contextlib import contextmanager

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(ROOT, "data", "discordbot.db")

DB_PATH = os.environ.get("DISCORDBOT_DB") or DEFAULT_DB


@contextmanager
def get_conn(path: str = None):
    path = path or DB_PATH
    conn = sqlite3.connect(path)
    try:
        yield conn
    finally:
        conn.close()


def init_db(schema_path: str = None, db_path: str = None):
    db_path = db_path or DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        if schema_path and os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8") as f:
                sql = f.read()
            conn.executescript(sql)
            conn.commit()
    finally:
        conn.close()


def insert(table: str, row: dict, db_path: str = None):
    db_path = db_path or DB_PATH
    cols = list(row.keys())
    placeholders = ",".join(["?" for _ in cols])
    cols_quoted = ",".join([f'"{c}"' for c in cols])
    sql = f'INSERT INTO "{table}" ({cols_quoted}) VALUES ({placeholders})'
    values = [json_serialize(v) for v in row.values()]
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute(sql, values)
        conn.commit()
        return cur.lastrowid


def fetch_all(sql: str, params=(), db_path: str = None):
    db_path = db_path or DB_PATH
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()


def json_serialize(v):
    # Delay importing json until needed to keep module lightweight
    import json

    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v
