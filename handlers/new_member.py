from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_admin

STATE = "NEWMEMBER_WAIT_ID"


async def cmd_newmember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    user_id = update.effective_user.id
    db.set_session(user_id, STATE, {})
    await update.message.reply_text(
        "Berikan Telegram ID user yang akan diaktifkan sebagai member:"
    )


async def handle_newmember_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != STATE:
        return
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text(
            "ID tidak valid. Masukkan angka Telegram ID, contoh: 123456789"
        )
        return
    target_id = int(text)
    db.set_member(target_id)
    db.clear_session(user_id)
    await update.message.reply_text(
        f"User {target_id} berhasil diaktifkan sebagai member."
    )
