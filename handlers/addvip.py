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
            "Format salah.\n"
            "Gunakan: /addvip <user_id> <hari>",
            parse_mode="HTML"
        )
        return

    target_id = int(args[0])
    days      = int(args[1])

    if days < 1 or days > 365:
        await update.message.reply_text("Hari harus 1-365.")
        return

    expired_at = db.set_member_vip(target_id, days)
    exp        = datetime.fromisoformat(expired_at)

    await update.message.reply_text(
        f"VIP aktif.\n\n"
        f"ID: {target_id}\n"
        f"Durasi: {days} hari\n"
        f"Berakhir: {exp.strftime('%d/%m/%Y %H:%M')}",
        parse_mode="HTML"
    )

    # Beritahu user yang baru diaktifkan
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"VIP kamu aktif.\n"
                f"Durasi: {days} hari\n"
                f"Berakhir: {exp.strftime('%d/%m/%Y')}"
            )
        )
    except Exception as e:
        logger.warning("Notif VIP ke %s gagal: %s", target_id, e)
        await update.message.reply_text(
            f"VIP aktif, tapi notif ke {target_id} gagal."
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
            "Format salah.\n"
            "Gunakan: /delvip <user_id>"
        )
        return

    user_id = update.effective_user.id
    db.increment_usage(user_id)

    target_id = int(args[0])
    user = db.get_user(target_id)
    if not user or not user["is_member"]:
        await update.message.reply_text(f"User {target_id} bukan member.")
        return

    db.remove_member(target_id)
    await update.message.reply_text(
        f"VIP {target_id} dicabut."
    )
