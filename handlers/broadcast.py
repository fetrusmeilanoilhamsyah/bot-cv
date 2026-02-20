from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_admin

STATE = "BROADCAST_WAIT_MSG"


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    user_id = update.effective_user.id
    db.set_session(user_id, STATE, {})
    await update.message.reply_text("Masukkan pesan broadcast:")


async def handle_broadcast_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != STATE:
        return

    message = update.message.text.strip()
    all_ids = db.get_all_user_ids()
    success = 0
    fail = 0

    await update.message.reply_text(f"Mengirim broadcast ke {len(all_ids)} user...")

    for uid in all_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=message)
            success += 1
        except Exception:
            fail += 1

    db.log_broadcast(user_id, message, success, fail)
    db.clear_session(user_id)

    await update.message.reply_text(
        f"Broadcast selesai.\nBerhasil: {success}\nGagal: {fail}"
    )