"""
rename.py — Disk-based approach with batch support.
"""
import os
import shutil
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_member
from middleware.session import get_user_dir
from core.utils import sanitize_filename

STATE_NAME = "RENAME_WAIT_NAME"
STATE_FILE = "RENAME_WAIT_FILE"

_user_timers: dict = {}


def _cancel_timer(user_id):
    timer = _user_timers.pop(user_id, None)
    if timer:
        timer.cancel()


async def _auto_clear_session(user_id: int):
    """Otomatis bersihkan sesi rename setelah 5 detik diam."""
    await asyncio.sleep(5)
    if _user_timers.get(user_id) is asyncio.current_task():
        db.clear_session(user_id)
        _user_timers.pop(user_id, None)


def _reset_timer(user_id):
    _cancel_timer(user_id)
    _user_timers[user_id] = asyncio.create_task(_auto_clear_session(user_id))


async def cmd_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_member(update, context):
        return
    user_id = update.effective_user.id
    db.increment_usage(user_id)
    _cancel_timer(user_id)
    db.set_session(user_id, STATE_NAME, {})
    await update.message.reply_text("Nama file:")


async def handle_rename_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != STATE_NAME:
        return
    file_name = sanitize_filename(update.message.text.strip())
    db.set_session(user_id, STATE_FILE, {"file_name": file_name})
    await update.message.reply_text(f"Nama diset: {file_name}\nSilakan kirim file VCF (Bisa banyak sekaligus).")


async def handle_rename_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != STATE_FILE:
        return
    data = sess["data"]

    # Reset timer setiap kali ada file masuk
    _reset_timer(user_id)

    # Download ke disk
    try:
        doc = update.message.document
        file_obj = await context.bot.get_file(doc.file_id)
        user_dir = get_user_dir(user_id)
        
        # Gunakan file_id unik agar tidak crash jika download berbarengan
        out_path = os.path.join(user_dir, f"rename_{doc.file_id}.vcf")
        
        await file_obj.download_to_drive(out_path)

        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            with open(out_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"{data['file_name']}.vcf"
                )
        
        if os.path.exists(out_path):
            os.remove(out_path)
            
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Rename error: {e}")