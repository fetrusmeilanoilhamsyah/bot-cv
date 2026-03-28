"""
pecahvcf.py — Disk-based approach to prevent OOM, with batch support.
"""
import os
import shutil
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_member
from middleware.session import get_user_dir
from core.vcf_parser import parse_vcf_file, contacts_to_vcf
from core.utils import sanitize_filename

STATE_PER_FILE = "PECAH_PER_FILE"
STATE_WAIT_VCF = "PECAH_WAIT_VCF"

_user_timers: dict = {}


def _cancel_timer(user_id):
    timer = _user_timers.pop(user_id, None)
    if timer:
        timer.cancel()


async def _auto_clear_session(user_id: int):
    """Otomatis bersihkan sesi pecahvcf setelah 5 detik diam."""
    await asyncio.sleep(5)
    if _user_timers.get(user_id) is asyncio.current_task():
        db.clear_session(user_id)
        _user_timers.pop(user_id, None)


def _reset_timer(user_id):
    _cancel_timer(user_id)
    _user_timers[user_id] = asyncio.create_task(_auto_clear_session(user_id))


async def cmd_pecahvcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_member(update, context):
        return
    user_id = update.effective_user.id
    db.increment_usage(user_id)
    _cancel_timer(user_id)
    db.set_session(user_id, STATE_PER_FILE, {})
    await update.message.reply_text("Kontak per file: (misal: 50)")


async def handle_pecah_per_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != STATE_PER_FILE:
        return
    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text("Input angka valid.")
        return
    db.set_session(user_id, STATE_WAIT_VCF, {"per_file": int(text)})
    await update.message.reply_text("Kirim file VCF (Bisa banyak sekaligus).")


async def handle_pecah_vcf_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != STATE_WAIT_VCF:
        return
    data = sess["data"]
    per_file = data["per_file"]

    # Reset timer setiap kali ada file masuk
    _reset_timer(user_id)

    doc = update.message.document
    file_obj = await context.bot.get_file(doc.file_id)
    user_dir = get_user_dir(user_id)
    
    # Gunakan subfolder unik per file agar tidak tabrakan
    pecah_dir = os.path.join(user_dir, f"pecah_{doc.file_id}")
    os.makedirs(pecah_dir, exist_ok=True)
    input_path = os.path.join(pecah_dir, "input.vcf")
    
    try:
        await file_obj.download_to_drive(input_path)

        loop = asyncio.get_running_loop()

        def process_pecah():
            contacts = parse_vcf_file(input_path)
            output_files = []
            total_files = 0
            for i in range(0, len(contacts), per_file):
                chunk = contacts[i:i + per_file]
                total_files += 1
                out_path = os.path.join(pecah_dir, f"PECAHAN{total_files}.vcf")
                with open(out_path, "w", encoding="utf-8") as f_out:
                    f_out.write(contacts_to_vcf(chunk))
                output_files.append(out_path)
            return output_files

        output_files = await loop.run_in_executor(None, process_pecah)
        
        for idx, out_path in enumerate(output_files, 1):
            with open(out_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=os.path.basename(out_path)
                )
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"PecahVCF error: {e}")
    finally:
        shutil.rmtree(pecah_dir, ignore_errors=True)