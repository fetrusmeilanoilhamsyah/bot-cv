import os
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.session import get_user_dir, clear_user_dir

logger = logging.getLogger(__name__)

STATE = "COUNT_COLLECTING"

def _count_contacts_sync(filepath: str, ext: str) -> int:
    """Fungsi sync untuk menghitung baris (TXT) atau VCARD (VCF)"""
    count = 0
    try:
        if ext == ".txt":
            # Hitung baris non-kosong
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.strip():
                        count += 1
        elif ext == ".vcf":
            # Hitung BEGIN:VCARD (Paling cepat untuk VCF)
            with open(filepath, 'rb') as f:
                content = f.read()
                count = content.count(b"BEGIN:VCARD")
    except Exception as e:
        logger.error("Error menghitung %s: %s", filepath, e)
    return count

async def cmd_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from middleware.auth import require_member
    if not await require_member(update, context):
        return
        
    user_id = update.effective_user.id
    db.increment_usage(user_id)
    
    # Bersihkan sisa direktori sisa proses sebelumnya
    clear_user_dir(user_id)
    
    db.set_session(user_id, STATE, {"total_kontak": 0, "total_file": 0})
    
    await update.message.reply_text(
        "Kirim file TXT atau VCF.\n"
        "Klik /done jika selesai."
    )

async def handle_count_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    
    if not sess or sess.get("state") != STATE:
        return
        
    doc = update.message.document
    if not doc:
        await update.message.reply_text("Kirim dokumen berupa file TXT atau VCF.")
        return
        
    ext = os.path.splitext(doc.file_name)[1].lower()
    if ext not in [".txt", ".vcf"]:
        await update.message.reply_text("Hanya file TXT/VCF.")
        return
        
    file_id = doc.file_id
    user_dir = get_user_dir(user_id)
    file_path = os.path.join(user_dir, doc.file_name)
    
    # Handle filename conflics
    base_name, ex = os.path.splitext(doc.file_name)
    counter = 1
    while os.path.exists(file_path):
        file_path = os.path.join(user_dir, f"{base_name}_{counter}{ex}")
        counter += 1
        
    try:
        tg_file = await context.bot.get_file(file_id)
        await tg_file.download_to_drive(file_path)
    except Exception as e:
        logger.error("Download error user %s: %s", user_id, e)
        await update.message.reply_text("Gagal mengunduh file. Coba kirim ulang.")
        return

    # Hitung di background (parallel, no blocking)
    loop = asyncio.get_running_loop()
    count = await loop.run_in_executor(None, _count_contacts_sync, file_path, ext)
    
    # Update state
    data = sess["data"]
    data["total_kontak"] += count
    data["total_file"] += 1
    db.set_session(user_id, STATE, data)
    
    await update.message.reply_text(
        f"{doc.file_name}: {count} kontak.\n"
        f"Total: {data['total_kontak']} ({data['total_file']} file)."
    )

async def handle_count_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    
    if not sess or sess.get("state") != STATE:
        return
        
    data = sess["data"]
    total_kontak = data.get("total_kontak", 0)
    total_file = data.get("total_file", 0)
    
    await update.message.reply_text(
        f"Selesai.\n"
        f"File: {total_file}\n"
        f"Kontak: {total_kontak}"
    )
    
    db.clear_session(user_id)
    clear_user_dir(user_id)
