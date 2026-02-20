"""
database/db.py - OPTIMIZED VERSION with Connection Pool

Key improvements:
1. Connection pool (10 connections) untuk concurrent operations
2. Timeout 30 seconds
3. Better error handling
4. Database indexes for faster queries
"""
import sqlite3
import os
from datetime import datetime
import queue
from contextlib import contextmanager
import threading

DB_PATH = os.path.join(os.path.dirname(__file__), "bot.db")

# ─── CONNECTION POOL ──────────────────────────────────────────────────────────
_conn_pool = queue.Queue(maxsize=10)
_pool_initialized = False
_pool_lock = threading.Lock()


def _init_connection():
    """Create a new database connection with optimized settings"""
    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,  # 30 seconds timeout (was default 5s)
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
    conn.execute("PRAGMA temp_store=MEMORY")   # Use memory for temp tables
    return conn


def init_connection_pool():
    """Initialize connection pool with 10 connections"""
    global _pool_initialized
    
    with _pool_lock:
        if _pool_initialized:
            return
            
        for _ in range(10):
            conn = _init_connection()
            _conn_pool.put(conn)
        
        _pool_initialized = True
        print(f"✅ Database connection pool initialized (10 connections)")


@contextmanager
def get_connection():
    """
    Get connection from pool using context manager
    
    Usage:
        with get_connection() as conn:
            conn.execute("SELECT * FROM users")
    """
    conn = _conn_pool.get()
    try:
        yield conn
    finally:
        _conn_pool.put(conn)


# ─── DATABASE INITIALIZATION ──────────────────────────────────────────────────

def init_db():
    """Initialize database tables and indexes"""
    init_connection_pool()
    
    with get_connection() as conn:
        # Create tables
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY,
                username    TEXT    DEFAULT '',
                full_name   TEXT    DEFAULT '',
                is_member   INTEGER DEFAULT 0,
                joined_at   TEXT    DEFAULT (datetime('now')),
                last_active TEXT    DEFAULT (datetime('now'))
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS broadcast_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id      INTEGER,
                message       TEXT,
                success_count INTEGER DEFAULT 0,
                fail_count    INTEGER DEFAULT 0,
                sent_at       TEXT    DEFAULT (datetime('now'))
            )
        """)
        
        # Create indexes for better performance
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_member ON users(is_member)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_active ON users(last_active)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_broadcast_admin ON broadcast_log(admin_id)")
        
        conn.commit()
        print(f"✅ Database tables and indexes initialized")


# Initialize on module import
init_db()


# ─── IN-MEMORY SESSION CACHE ──────────────────────────────────────────────────
_session_cache: dict = {}
_all_buffers: dict = {}


# ─── USERS ────────────────────────────────────────────────────────────────────

def upsert_user(user_id: int, username: str, full_name: str):
    """Insert or update user information"""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO users (id, username, full_name, last_active)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username    = excluded.username,
                full_name   = excluded.full_name,
                last_active = excluded.last_active
        """, (user_id, username, full_name, datetime.now().isoformat()))
        conn.commit()


def get_user(user_id: int):
    """Get user by ID"""
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, username, full_name, is_member FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()


def is_member(user_id: int) -> bool:
    """Check if user is a member"""
    row = get_user(user_id)
    return row is not None and bool(row["is_member"])


def set_member(user_id: int, full_name: str = ""):
    """Set user as member"""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO users (id, username, full_name, is_member)
            VALUES (?, '', ?, 1)
            ON CONFLICT(id) DO UPDATE SET is_member = 1
        """, (user_id, full_name))
        conn.commit()


def get_all_member_ids():
    """Get all member IDs"""
    with get_connection() as conn:
        rows = conn.execute("SELECT id FROM users WHERE is_member = 1").fetchall()
        return [r["id"] for r in rows]


def get_all_user_ids():
    """Get all user IDs"""
    with get_connection() as conn:
        rows = conn.execute("SELECT id FROM users").fetchall()
        return [r["id"] for r in rows]


def clear_all_users():
    """Clear all users and broadcast logs"""
    with get_connection() as conn:
        conn.execute("DELETE FROM broadcast_log")
        conn.execute("DELETE FROM users")
        conn.commit()
    
    _session_cache.clear()
    _all_buffers.clear()


# ─── BATCH OPERATIONS (NEW) ───────────────────────────────────────────────────

def batch_update_users(users: list):
    """
    Update multiple users in a single transaction
    
    Args:
        users: List of (user_id, username, full_name) tuples
    """
    with get_connection() as conn:
        for user_id, username, full_name in users:
            conn.execute("""
                INSERT INTO users (id, username, full_name, last_active)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    username = excluded.username,
                    full_name = excluded.full_name,
                    last_active = excluded.last_active
            """, (user_id, username, full_name, datetime.now().isoformat()))
        conn.commit()


# ─── SESSIONS (IN-MEMORY) ─────────────────────────────────────────────────────

def get_session(user_id: int) -> dict:
    """Get user session (in-memory)"""
    return _session_cache.get(user_id, {"state": None, "data": {}})


def set_session(user_id: int, state: str, data: dict):
    """Set user session (in-memory)"""
    _session_cache[user_id] = {"state": state, "data": data}


def clear_session(user_id: int):
    """Clear user session"""
    _session_cache.pop(user_id, None)


def clear_user_ram(user_id: int):
    """Clear user RAM data (session and buffers)"""
    _session_cache.pop(user_id, None)
    _all_buffers.pop(user_id, None)


# ─── BROADCAST LOG ────────────────────────────────────────────────────────────

def log_broadcast(admin_id: int, message: str, success: int, fail: int):
    """Log broadcast message"""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO broadcast_log (admin_id, message, success_count, fail_count)
            VALUES (?, ?, ?, ?)
        """, (admin_id, message, success, fail))
        conn.commit()


# ─── HEALTH CHECK (NEW) ───────────────────────────────────────────────────────

def get_db_stats():
    """Get database statistics for monitoring"""
    with get_connection() as conn:
        user_count = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]
        member_count = conn.execute("SELECT COUNT(*) as count FROM users WHERE is_member = 1").fetchone()["count"]
        broadcast_count = conn.execute("SELECT COUNT(*) as count FROM broadcast_log").fetchone()["count"]
        
        return {
            "total_users": user_count,
            "total_members": member_count,
            "total_broadcasts": broadcast_count,
            "session_cache_size": len(_session_cache),
            "buffer_cache_size": len(_all_buffers),
        }
