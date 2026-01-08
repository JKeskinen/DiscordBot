import os
import json
import sqlite3
import datetime
from typing import Optional


def _base_dir(provided: Optional[str] = None) -> str:
    if provided is not None and provided != '':
        return provided
    # default to project root (parent of this module)
    return os.path.abspath(os.path.join(os.path.dirname(__file__) or '', '..'))


def _db_path() -> str:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__) or '', '..'))
    db_dir = os.path.join(root, 'data')
    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, 'discordbot.db')


def _ensure_table(conn: sqlite3.Connection):
    conn.execute(
        'CREATE TABLE IF NOT EXISTS json_store (name TEXT PRIMARY KEY, content TEXT NOT NULL)'
    )
    # Table for marking published items (idempotency for postings)
    conn.execute(
        '''CREATE TABLE IF NOT EXISTS PUBLISHED_GAMES (
               id TEXT PRIMARY KEY,
               title TEXT,
               published TEXT,
               url TEXT,
               meta TEXT
           )'''
    )


def save_category(name: str, entries, out_path: Optional[str] = None, base_dir: Optional[str] = None):
    """Save entries for a named category into SQLite `json_store` table.
    Keeps the same signature as before; if DB write fails, falls back to file write.
    """
    # normalize filename keys: allow callers to pass 'CAPACITY_ALERTS.json' or 'CAPACITY_ALERTS'
    name = os.path.splitext(name)[0]
    db = _db_path()
    try:
        with sqlite3.connect(db) as conn:
            _ensure_table(conn)
            content = json.dumps(entries, ensure_ascii=False)
            conn.execute('REPLACE INTO json_store (name, content) VALUES (?, ?)', (name, content))
            conn.commit()
        try:
            print(f"Saved {len(entries) if hasattr(entries, '__len__') else 'items'} to sqlite:{db} as {name}")
        except Exception:
            print(f"Saved to sqlite:{db} as {name}")
        # remove any legacy JSON file at project root to avoid duplicate on-disk artifacts
        try:
            root = _base_dir(base_dir)
            file_path = os.path.join(str(root), f"{name}.json")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
        except Exception:
            pass
        return
    except Exception as e:
        print(f"SQLite save failed for {name}: {e}; falling back to file")

    # fallback to file-based storage
    bd = _base_dir(base_dir)
    if out_path:
        path = out_path
    else:
        path = os.path.join(str(bd), f"{name}.json")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(entries) if hasattr(entries, '__len__') else 'items'} {name} entries to {path}")
    except Exception as e:
        print(f"Failed to save {name} JSON: {e}")


def load_category(name: str, path: Optional[str] = None, base_dir: Optional[str] = None):
    """Load entries for a named category. Returns list or parsed JSON object.
    First tries SQLite `json_store`, then falls back to file lookup at project root.
    """
    # normalize filename keys: allow callers to pass 'CAPACITY_ALERTS.json' or 'CAPACITY_ALERTS'
    name = os.path.splitext(name)[0]
    db = _db_path()
    try:
        with sqlite3.connect(db) as conn:
            _ensure_table(conn)
            cur = conn.execute('SELECT content FROM json_store WHERE name = ?', (name,))
            row = cur.fetchone()
            if row and row[0]:
                parsed = json.loads(row[0])
                # Backwards-compatibility: many callers expect CAPACITY_SCAN_RESULTS
                # to be a list of items. If stored object wraps results under
                # a top-level 'results' key, return that list for convenience.
                if isinstance(parsed, dict) and 'results' in parsed and isinstance(parsed.get('results'), (list, tuple)):
                    return parsed.get('results')
                return parsed
    except Exception as e:
        # continue to file fallback
        print(f"SQLite load failed for {name}: {e}; falling back to file")

    bd = _base_dir(base_dir)
    p = path or os.path.join(str(bd), f"{name}.json")
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def is_published(game_id: str) -> bool:
    """Return True if `game_id` is present in PUBLISHED_GAMES."""
    if not game_id:
        return False
    db = _db_path()
    try:
        with sqlite3.connect(db) as conn:
            _ensure_table(conn)
            cur = conn.execute('SELECT 1 FROM PUBLISHED_GAMES WHERE id = ? LIMIT 1', (str(game_id),))
            return cur.fetchone() is not None
    except Exception:
        return False


def mark_published(game_id: str, title: Optional[str] = None, url: Optional[str] = None, meta: Optional[dict] = None):
    """Insert or update a published marker for `game_id`.
    `meta` will be stored as JSON in the `meta` column if provided.
    """
    if not game_id:
        return False
    db = _db_path()
    try:
        with sqlite3.connect(db) as conn:
            _ensure_table(conn)
            js = None
            if meta is not None:
                try:
                    js = json.dumps(meta, ensure_ascii=False)
                except Exception:
                    js = None
            now = datetime.datetime.utcnow().isoformat() + 'Z' if 'datetime' in globals() else None
            conn.execute('REPLACE INTO PUBLISHED_GAMES (id, title, published, url, meta) VALUES (?, ?, ?, ?, ?)',
                         (str(game_id), title, now, url, js))
            conn.commit()
        return True
    except Exception:
        return False


def list_published(limit: int = 100):
    """Return a list of published entries (dicts)."""
    db = _db_path()
    out = []
    try:
        with sqlite3.connect(db) as conn:
            _ensure_table(conn)
            cur = conn.execute('SELECT id, title, published, url, meta FROM PUBLISHED_GAMES ORDER BY published DESC LIMIT ?', (limit,))
            for r in cur.fetchall():
                rec = {'id': r[0], 'title': r[1], 'published': r[2], 'url': r[3]}
                try:
                    rec['meta'] = json.loads(r[4]) if r[4] else None
                except Exception:
                    rec['meta'] = r[4]
                out.append(rec)
    except Exception:
        pass
    return out
