"""
rename.py — In-memory approach.
"""
from io import BytesIO
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_member

STATE_NAME = "RENAME_WAIT_NAME"
STATE_FILE = "RENAME_WAIT_FILE"


async def cmd_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_member(update, context):
        return
    user_id = update.effective_user.id
    db.set_session(user_id, STATE_NAME, {})
    await update.message.reply_text("Masukkan nama file yang diinginkan:")


async def handle_rename_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != STATE_NAME:
        return
    file_name = update.message.text.strip()
    db.set_session(user_id, STATE_FILE, {"file_name": file_name})
    await update.message.reply_text("Kirimkan file VCF yang ingin diganti namanya.")


async def handle_rename_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != STATE_FILE:
        return
    data = sess["data"]

    # Download ke RAM, langsung kirim balik dengan nama baru
    file_obj = await context.bot.get_file(update.message.document.file_id)
    bio = BytesIO()
    await file_obj.download_to_memory(bio)

    db.clear_session(user_id)

    await update.message.reply_document(
        document=bio.getvalue(),
        filename=f"{data['file_name']}.vcf"
    )