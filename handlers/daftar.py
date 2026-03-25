"""
daftar.py — Tampilkan daftar semua pengguna bot.
Hanya bisa diakses oleh admin.
"""
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_admin

CHUNK = 30  # Jumlah user per pesan (hindari pesan terlalu panjang)


async def cmd_daftar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return

    users = db.get_all_users_detail()

    if not users:
        await update.message.reply_text("Belum ada pengguna yang terdaftar.")
        return

    total       = len(users)
    total_member = sum(1 for u in users if u["is_member"])
    total_non   = total - total_member

    header = (
        f"📋 <b>DAFTAR PENGGUNA BOT</b>\n"
        f"Total: {total} user  |  Member: {total_member}  |  Non-member: {total_non}\n"
        f"{'─' * 30}\n"
    )

    # Kirim dalam chunks agar tidak melebihi batas 4096 karakter Telegram
    for i in range(0, total, CHUNK):
        chunk = users[i:i + CHUNK]
        lines = []
        for u in chunk:
            icon     = "⭐" if u["is_member"] else "👤"
            username = f"@{u['username']}" if u["username"] else "—"
            name     = u["full_name"] or "—"
            uid      = u["id"]
            lines.append(f"{icon} <b>{name}</b> ({username})\n    ID: <code>{uid}</code>")

        msg = (header if i == 0 else "") + "\n\n".join(lines)
        await update.message.reply_text(msg, parse_mode="HTML")
