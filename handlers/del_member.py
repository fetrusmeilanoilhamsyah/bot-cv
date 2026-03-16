from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_admin

STATE = "DELMEMBER_WAIT_ID"

async def cmd_delmember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    user_id = update.effective_user.id
    db.set_session(user_id, STATE, {})
    await update.message.reply_text(
        "Berikan Telegram ID user yang akan dicopot status membernya:"
    )

async def handle_delmember_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    # Check if user exists
    user = db.get_user(target_id)
    if not user:
        await update.message.reply_text(f"User {target_id} tidak ditemukan di database.")
        db.clear_session(user_id)
        return

    db.remove_member(target_id)
    db.clear_session(user_id)
    await update.message.reply_text(
        f"Akses Premium untuk User {target_id} ({user['full_name']}) telah DICOPOT."
    )
