"""
rename.py — Disk-based approach
"""
import os
from io import BytesIO
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_member
from middleware.session import get_user_dir

STATE_NAME = "RENAME_WAIT_NAME"
STATE_FILE = "RENAME_WAIT_FILE"


async def cmd_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_member(update, context):
        return
    user_id = update.effective_user.id
    db.set_session(user_id, STATE_NAME, {})
    await update.message.reply_text("Nama file yang diinginkan:")


async def handle_rename_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != STATE_NAME:
        return
    file_name = update.message.text.strip()
    db.set_session(user_id, STATE_FILE, {"file_name": file_name})
    await update.message.reply_text("Kirim file VCF yang ingin diganti namanya.")


async def handle_rename_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != STATE_FILE:
        return
    data = sess["data"]

    # Download ke disk
    file_obj = await context.bot.get_file(update.message.document.file_id)
    user_dir = get_user_dir(user_id)
    out_path = os.path.join(user_dir, "temp_rename.vcf")
    
    await file_obj.download_to_drive(out_path)

    db.clear_session(user_id)

    if os.path.exists(out_path) and os.path.getsize(out_path) == 0:
        await update.message.reply_text("File yang dikirim kosong (0 bytes).")
        try:
            os.remove(out_path)
        except Exception:
            pass
        return

    try:
        with open(out_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"{data['file_name']}.vcf"
            )
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)