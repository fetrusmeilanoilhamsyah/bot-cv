"""
stat.py — Admin dashboard: statistik bot realtime.
"""
import os
import time
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_admin

# Waktu startup bot (diset saat import)
_START_TIME = time.time()


def _uptime_str() -> str:
    secs = int(time.time() - _START_TIME)
    h, rem = divmod(secs, 3600)
    m, s   = divmod(rem, 60)
    if h:
        return f"{h}j {m}m {s}d"
    return f"{m}m {s}d"


async def cmd_stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return

    users    = db.get_all_users_detail()
    total    = len(users)
    members  = sum(1 for u in users if u["is_member"])
    non_mem  = total - members
    vip_timed = sum(1 for u in users if u["is_member"] and u.get("expired_at"))

    # Hitung file temp yang masih tersisa (sesi mungkin nyangkut)
    tmp_dir    = os.path.join("tmp", "sessions")
    tmp_count  = 0
    tmp_size   = 0
    if os.path.exists(tmp_dir):
        for root, dirs, files in os.walk(tmp_dir):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    tmp_size += os.path.getsize(fp)
                    tmp_count += 1
                except Exception:
                    pass

    tmp_size_mb = tmp_size / (1024 * 1024)

    await update.message.reply_text(
        f"<b>STATISTIK BOT</b>\n"
        f"{'─'*28}\n"
        f"Uptime      : {_uptime_str()}\n"
        f"{'─'*28}\n"
        f"Total user  : {total}\n"
        f"Member aktif: {members}\n"
        f"  - VIP timed : {vip_timed}\n"
        f"  - Permanen  : {members - vip_timed}\n"
        f"Non-member  : {non_mem}\n"
        f"{'─'*28}\n"
        f"Tmp files   : {tmp_count} file ({tmp_size_mb:.2f} MB)",
        parse_mode="HTML"
    )
