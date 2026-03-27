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
                last_active TEXT    DEFAULT (datetime('now')),
                expired_at  TEXT    DEFAULT NULL,
                referred_by INTEGER DEFAULT NULL,
                usage_count INTEGER DEFAULT 0,
                expiry_notified INTEGER DEFAULT 0
            )
        """)
        
        # Safe migration: add expired_at if db already exists without it
        try:
            conn.execute("ALTER TABLE users ADD COLUMN expired_at TEXT DEFAULT NULL")
            conn.commit()
            print("✅ Migrated: added expired_at column")
        except Exception:
            pass  # Column already exists
            
        try:
            conn.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER DEFAULT NULL")
            conn.execute("ALTER TABLE users ADD COLUMN usage_count INTEGER DEFAULT 0")
            conn.execute("ALTER TABLE users ADD COLUMN expiry_notified INTEGER DEFAULT 0")
            conn.commit()
            print("✅ Migrated: added referral and analytics columns")
        except Exception:
            pass
        
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_expiry ON users(expired_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_ref ON users(referred_by)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_usage ON users(usage_count)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_broadcast_admin ON broadcast_log(admin_id)")
        
        conn.commit()
        print(f"✅ Database tables and indexes initialized")

    # Auto-register ADMIN_IDS from config as members (INSIDE init_db)
    from config import ADMIN_IDS
    for admin_id in ADMIN_IDS:
        if admin_id > 0:
            set_member(admin_id, "System Admin")
            print(f"👑 Admin {admin_id} auto-registered as member")



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

def increment_usage(user_id: int):
    """Increment user activity counter"""
    with get_connection() as conn:
        conn.execute("UPDATE users SET usage_count = usage_count + 1, last_active = ? WHERE id = ?", 
                    (datetime.now().isoformat(), user_id))
        conn.commit()

def set_referrer(user_id: int, referrer_id: int):
    """Set who referred this user (only once)"""
    if user_id == referrer_id: return
    with get_connection() as conn:
        conn.execute("UPDATE users SET referred_by = ? WHERE id = ? AND referred_by IS NULL", (referrer_id, user_id))
        conn.commit()

def get_referrer(user_id: int):
    """Get the ID of the person who referred this user"""
    with get_connection() as conn:
        row = conn.execute("SELECT referred_by FROM users WHERE id = ?", (user_id,)).fetchone()
        return row["referred_by"] if row else None

def get_top_users(limit=5):
    """Get top active users for leaderboard"""
    with get_connection() as conn:
        rows = conn.execute("SELECT full_name, usage_count FROM users ORDER BY usage_count DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

def get_users_for_expiry_notif():
    """Get users who expire in ~24 hours and haven't been notified"""
    # Mencari yang expired_at antara 23 jam sampai 25 jam ke depan
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, expired_at FROM users 
            WHERE is_member = 1 
              AND expiry_notified = 0 
              AND expired_at IS NOT NULL
              AND expired_at BETWEEN datetime('now', '+23 hours') AND datetime('now', '+25 hours')
        """).fetchall()
        return [dict(r) for r in rows]

def mark_expiry_notified(user_id: int):
    """Mark that user has been notified about expiry"""
    with get_connection() as conn:
        conn.execute("UPDATE users SET expiry_notified = 1 WHERE id = ?", (user_id,))
        conn.commit()


def get_user(user_id: int):
    """Get user by ID"""
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, username, full_name, is_member FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()


def is_member(user_id: int) -> bool:
    """Check if user is an active member (auto-expires if past due)"""
    from datetime import datetime
    row = get_user(user_id)
    if row is None or not bool(row["is_member"]):
        return False
    # Check VIP expiry — admins have no expiry (expired_at = NULL)
    expired_at = dict(row).get("expired_at")
    if expired_at is None:
        return True  # Permanent member (admin or manually added)
    if datetime.fromisoformat(expired_at) < datetime.now():
        # Auto-revoke expired VIP
        remove_member(user_id)
        return False
    return True


def remove_member(user_id: int):
    """Remove user from membership status"""
    with get_connection() as conn:
        conn.execute("UPDATE users SET is_member = 0, expired_at = NULL WHERE id = ?", (user_id,))
        conn.commit()


def set_member(user_id: int, full_name: str = ""):
    """Set user as permanent member (no expiry — for admins / manual grant)"""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO users (id, username, full_name, is_member, expired_at)
            VALUES (?, '', ?, 1, NULL)
            ON CONFLICT(id) DO UPDATE SET is_member = 1, expired_at = NULL
        """, (user_id, full_name))
        conn.commit()


def set_member_vip(user_id: int, days: int, full_name: str = ""):
    """Set user as VIP member with expiry date. Admins are forced to NULL (permanent)."""
    from datetime import datetime, timedelta
    from config import ADMIN_IDS
    
    if user_id in ADMIN_IDS:
        set_member(user_id, full_name)
        return None

    expired_at = (datetime.now() + timedelta(days=days)).isoformat()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO users (id, username, full_name, is_member, expired_at)
            VALUES (?, '', ?, 1, ?)
            ON CONFLICT(id) DO UPDATE SET
                is_member  = 1,
                expired_at = CASE
                    WHEN expired_at IS NOT NULL AND expired_at > datetime('now')
                    THEN datetime(expired_at, '+{} days')
                    ELSE ?
                END
        """.format(days), (user_id, full_name, expired_at, expired_at))
        conn.commit()
    return expired_at


def get_vip_expiry(user_id: int):
    """Returns ISO expiry string or None if permanent/not found"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT expired_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row)["expired_at"] if row else None


def expire_vip_members():
    """Batch expire all VIP members whose time has passed. Called on startup/periodic."""
    with get_connection() as conn:
        result = conn.execute("""
            UPDATE users SET is_member = 0, expired_at = NULL
            WHERE is_member = 1
              AND expired_at IS NOT NULL
              AND expired_at < datetime('now')
        """)
        conn.commit()
        return result.rowcount


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


def get_all_users_detail():
    """Get all users with full details for /daftar command"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, username, full_name, is_member, joined_at, expired_at FROM users ORDER BY joined_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def clear_all_db():
    """Smart Reset: Clear logs and sessions but preserve users and premium status"""
    with get_connection() as conn:
        # Clear broadcast history
        conn.execute("DELETE FROM broadcast_log")
        conn.commit()
    
    # Clear in-memory buffers
    _session_cache.clear()
    _all_buffers.clear()
    
    # Clear on-disk temporary files via session middleware (if possible)
    try:
        from middleware.session import clear_all_sessions
        clear_all_sessions()
    except ImportError:
        pass
        
    print("⚠️ SMART RESET: Logs and sessions cleared. Users and Premium status preserved.")


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

# Initialize on module import
init_db()
