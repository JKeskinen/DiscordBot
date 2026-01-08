#!/usr/bin/env python3
"""Simple migration: infer table schemas from JSON files and insert into SQLite.
Usage: python migrate_json_to_sqlite.py [--db data/discordbot.db] [--files file1.json file2.json ...]

It creates tables named after the JSON filename stems and stores nested structures as JSON strings.
"""
import argparse
import json
import os
import sqlite3
from typing import List

DEFAULT_FILES = [
    "CAPACITY_SCAN_RESULTS.json",
    "CAPACITY_ALERTS.json",
    "PUBLISHED_GAMES.json",
    "TJING_REGISTRATIONS.json",
    "PUBLISHED_GAMES.json",
]

ROOT = os.path.dirname(os.path.abspath(__file__))


def normalize_col(name: str) -> str:
    name = name.strip()
    allowed = []
    for c in name:
        if c.isalnum() or c == "_":
            allowed.append(c)
        else:
            allowed.append("_")
    col = "".join(allowed)
    if col == "":
        col = "col"
    return col.lower()


def load_json_file(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_list(obj):
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    return [obj]


def infer_columns(records: List[dict]):
    cols = set()
    for r in records:
        if not isinstance(r, dict):
            continue
        for k in r.keys():
            cols.add(k)
    return [normalize_col(c) for c in cols]


def create_table(conn: sqlite3.Connection, table: str, columns: List[str]):
    cols_sql = ", ".join([f'"{c}" TEXT' for c in columns])
    sql = f"CREATE TABLE IF NOT EXISTS \"{table}\" ( _rowid INTEGER PRIMARY KEY AUTOINCREMENT, {cols_sql} )"
    conn.execute(sql)


def insert_records(conn: sqlite3.Connection, table: str, columns: List[str], records: List[dict]):
    if not records:
        return 0
    cols_quoted = [f'"{c}"' for c in columns]
    placeholders = ",".join(["?" for _ in columns])
    sql = f"INSERT INTO \"{table}\" ({', '.join(cols_quoted)}) VALUES ({placeholders})"
    to_insert = []
    for r in records:
        row = []
        if isinstance(r, dict):
            for c in columns:
                # original key may differ in case/format; pick by normalized name
                # attempt to find original key
                val = None
                if c in r:
                    val = r.get(c)
                else:
                    # try to find matching original key by normalize
                    for k in r.keys():
                        if normalize_col(k) == c:
                            val = r.get(k)
                            break
                if isinstance(val, (dict, list)):
                    val = json.dumps(val, ensure_ascii=False)
                row.append(val)
        else:
            # non-dict values stored in single column named 'value' if present
            row = [json.dumps(r, ensure_ascii=False) if isinstance(r, (dict, list)) else r]
        to_insert.append(tuple(row))
    conn.executemany(sql, to_insert)
    return len(to_insert)


def process_file(conn: sqlite3.Connection, path: str):
    print(f"Processing {path}...")
    data = load_json_file(path)
    items = ensure_list(data)
    # if items is list of primitives, wrap as dict
    sample = items[0] if items else {}
    if isinstance(sample, dict):
        columns = infer_columns(items)
        if not columns:
            # fallback to single JSON column
            columns = ["value"]
        table = os.path.splitext(os.path.basename(path))[0]
        create_table(conn, table, columns)
        inserted = insert_records(conn, table, columns, items)
        print(f"Inserted {inserted} rows into {table}")
    else:
        # list of primitives
        table = os.path.splitext(os.path.basename(path))[0]
        create_table(conn, table, ["value"])
        inserted = insert_records(conn, table, ["value"], items)
        print(f"Inserted {inserted} rows into {table}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=os.path.join(ROOT, "data", "discordbot.db"))
    p.add_argument("--files", nargs="*", help="JSON files to migrate; defaults to common files")
    args = p.parse_args()

    files = args.files if args.files else DEFAULT_FILES
    files = [os.path.join(ROOT, f) if not os.path.isabs(f) else f for f in files]
    files = [f for f in files if os.path.exists(f)]
    if not files:
        print("No JSON files found to migrate. Provide --files or place files in project root.")
        return

    db_path = args.db
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        for f in files:
            try:
                process_file(conn, f)
            except Exception as e:
                print(f"Failed to process {f}: {e}")
        conn.commit()
        print(f"Migration completed. DB at: {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
