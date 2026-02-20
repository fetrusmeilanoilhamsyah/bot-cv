import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "bot.db")

# ─── Persistent connection (jauh lebih cepat dari buka tutup tiap query) ──────
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
_conn.execute("PRAGMA journal_mode=WAL")  # tulis lebih cepat
_conn.execute("PRAGMA synchronous=NORMAL")


def init_db():
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY,
            username    TEXT    DEFAULT '',
            full_name   TEXT    DEFAULT '',
            is_member   INTEGER DEFAULT 0,
            joined_at   TEXT    DEFAULT (datetime('now')),
            last_active TEXT    DEFAULT (datetime('now'))
        )
    """)
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id      INTEGER,
            message       TEXT,
            success_count INTEGER DEFAULT 0,
            fail_count    INTEGER DEFAULT 0,
            sent_at       TEXT    DEFAULT (datetime('now'))
        )
    """)
    _conn.commit()

init_db()

# ─── IN-MEMORY SESSION CACHE ──────────────────────────────────────────────────
_session_cache: dict = {}
_all_buffers: dict = {}


# ─── USERS ────────────────────────────────────────────────────────────────────

def upsert_user(user_id: int, username: str, full_name: str):
    _conn.execute("""
        INSERT INTO users (id, username, full_name, last_active)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            username    = excluded.username,
            full_name   = excluded.full_name,
            last_active = excluded.last_active
    """, (user_id, username, full_name, datetime.now().isoformat()))
    _conn.commit()


def get_user(user_id: int):
    return _conn.execute(
        "SELECT id, username, full_name, is_member FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()


def is_member(user_id: int) -> bool:
    row = get_user(user_id)
    return row is not None and bool(row["is_member"])


def set_member(user_id: int, full_name: str = ""):
    _conn.execute("""
        INSERT INTO users (id, username, full_name, is_member)
        VALUES (?, '', ?, 1)
        ON CONFLICT(id) DO UPDATE SET is_member = 1
    """, (user_id, full_name))
    _conn.commit()


def get_all_member_ids():
    rows = _conn.execute("SELECT id FROM users WHERE is_member = 1").fetchall()
    return [r["id"] for r in rows]


def get_all_user_ids():
    rows = _conn.execute("SELECT id FROM users").fetchall()
    return [r["id"] for r in rows]


def clear_all_users():
    _conn.execute("DELETE FROM broadcast_log")
    _conn.execute("DELETE FROM users")
    _conn.commit()
    _session_cache.clear()
    _all_buffers.clear()


# ─── SESSIONS (IN-MEMORY) ─────────────────────────────────────────────────────

def get_session(user_id: int) -> dict:
    return _session_cache.get(user_id, {"state": None, "data": {}})


def set_session(user_id: int, state: str, data: dict):
    _session_cache[user_id] = {"state": state, "data": data}


def clear_session(user_id: int):
    _session_cache.pop(user_id, None)


def clear_user_ram(user_id: int):
    _session_cache.pop(user_id, None)
    _all_buffers.pop(user_id, None)


# ─── BROADCAST LOG ────────────────────────────────────────────────────────────

def log_broadcast(admin_id: int, message: str, success: int, fail: int):
    _conn.execute("""
        INSERT INTO broadcast_log (admin_id, message, success_count, fail_count)
        VALUES (?, ?, ?, ?)
    """, (admin_id, message, success, fail))
    _conn.commit()