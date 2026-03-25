"""
addvip.py — Admin command untuk mengaktifkan VIP manual.
Usage: /addvip <user_id> <hari>
  /addvip 123456789 7   → aktifkan 7 hari
  /addvip 123456789 30  → aktifkan 30 hari
  /delvip 123456789     → cabut VIP
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_admin
from datetime import datetime

logger = logging.getLogger(__name__)


async def cmd_addvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Guard: hanya proses jika ada message (bukan channel post / edited msg)
    if not update.message:
        return
    if not await require_admin(update, context):
        return

    args = context.args  # Telegram sudah strip whitespace antar arg
    if len(args) != 2 or not args[0].lstrip("-").isdigit() or not args[1].isdigit():
        await update.message.reply_text(
            "❌ Format salah.\n"
            "Gunakan: <code>/addvip &lt;user_id&gt; &lt;hari&gt;</code>\n\n"
            "Contoh:\n"
            "<code>/addvip 123456789 7</code>  → 1 minggu\n"
            "<code>/addvip 123456789 14</code> → 2 minggu\n"
            "<code>/addvip 123456789 21</code> → 3 minggu\n"
            "<code>/addvip 123456789 30</code> → 1 bulan",
            parse_mode="HTML"
        )
        return

    target_id = int(args[0])
    days      = int(args[1])

    if days < 1 or days > 365:
        await update.message.reply_text("❌ Hari harus antara 1 sampai 365.")
        return

    expired_at = db.set_member_vip(target_id, days)
    exp        = datetime.fromisoformat(expired_at)

    await update.message.reply_text(
        f"✅ VIP diaktifkan!\n\n"
        f"👤 User ID : <code>{target_id}</code>\n"
        f"⏱ Durasi  : <b>{days} hari</b>\n"
        f"📅 Berakhir: <b>{exp.strftime('%d %b %Y, %H:%M')}</b>",
        parse_mode="HTML"
    )

    # Beritahu user yang baru diaktifkan
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"🎉 <b>Selamat! Akses VIP kamu sudah aktif!</b>\n\n"
                f"⏱ Durasi  : <b>{days} hari</b>\n"
                f"📅 Berakhir: <b>{exp.strftime('%d %b %Y')}</b>\n\n"
                f"Gunakan /vip untuk cek status kapan saja."
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning("Notif VIP ke %s gagal: %s", target_id, e)
        await update.message.reply_text(
            f"⚠️ VIP aktif, tapi notif ke user <code>{target_id}</code> gagal "
            f"(user belum pernah start bot).",
            parse_mode="HTML"
        )


async def cmd_delvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cabut VIP dari user"""
    if not update.message:
        return
    if not await require_admin(update, context):
        return

    args = context.args
    if len(args) != 1 or not args[0].lstrip("-").isdigit():
        await update.message.reply_text(
            "❌ Format salah.\n"
            "Gunakan: <code>/delvip &lt;user_id&gt;</code>",
            parse_mode="HTML"
        )
        return

    target_id = int(args[0])
    user = db.get_user(target_id)
    if not user or not user["is_member"]:
        await update.message.reply_text(f"ℹ️ User <code>{target_id}</code> bukan member aktif.", parse_mode="HTML")
        return

    db.remove_member(target_id)
    await update.message.reply_text(
        f"✅ VIP user <code>{target_id}</code> berhasil dicabut.",
        parse_mode="HTML"
    )
