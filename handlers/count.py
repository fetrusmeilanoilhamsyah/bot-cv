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

_user_status_msg: dict = {}
_user_bg_tasks: dict = {}
_user_last_edit: dict = {}
_user_locks: dict = {}

def get_user_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]

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

async def _bg_process(context, file_id: str, file_path: str, ext: str, user_id: int):
    """Worker untuk download dan hitung di background."""
    try:
        # 1. Download
        file_obj = await context.bot.get_file(file_id)
        await file_obj.download_to_drive(file_path)
        
        # 2. Count
        loop = asyncio.get_running_loop()
        count = await loop.run_in_executor(None, _count_contacts_sync, file_path, ext)
        
        # 3. Update DB
        async with get_user_lock(user_id):
            sess = db.get_session(user_id)
            if sess and sess.get("state") == STATE:
                data = sess["data"]
                data["total_kontak"] += count
                data["total_file"] += 1
                db.set_session(user_id, STATE, data)
                
    except Exception as e:
        logger.error(f"Count BG process error user {user_id}: {e}")
    finally:
        if user_id in _user_bg_tasks:
            _user_bg_tasks[user_id].discard(asyncio.current_task())

async def cmd_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.increment_usage(user_id)
    clear_user_dir(user_id)
    _user_status_msg.pop(user_id, None)
    _user_last_edit.pop(user_id, None)
    _user_bg_tasks.pop(user_id, None)
    
    db.set_session(user_id, STATE, {"total_kontak": 0, "total_file": 0})
    await update.message.reply_text(
        "Kirim file TXT atau VCF.\nKlik /done jika selesai."
    )

async def handle_count_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    sess = db.get_session(user_id)
    if not sess or sess.get("state") != STATE:
        return
        
    doc = update.message.document
    if not doc:
        return
        
    ext = os.path.splitext(doc.file_name)[1].lower()
    if ext not in [".txt", ".vcf"]:
        return
        
    user_dir = get_user_dir(user_id)
    file_path = os.path.join(user_dir, doc.file_name)
    
    # Handle conflicts
    base_name, ex = os.path.splitext(doc.file_name)
    counter = 1
    while os.path.exists(file_path):
        file_path = os.path.join(user_dir, f"{base_name}_{counter}{ex}")
        counter += 1
        
    # Kick off background task
    if user_id not in _user_bg_tasks:
        _user_bg_tasks[user_id] = set()
    
    task = asyncio.create_task(_bg_process(context, doc.file_id, file_path, ext, user_id))
    _user_bg_tasks[user_id].add(task)

    # Throttled status edit
    import time
    now = time.time()
    last = _user_last_edit.get(user_id, 0)
    
    if user_id not in _user_status_msg:
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"Menerima file... ({len(_user_bg_tasks[user_id])})",
            disable_notification=True
        )
        _user_status_msg[user_id] = msg.message_id
        _user_last_edit[user_id] = now
    elif now - last > 2.0 or len(_user_bg_tasks[user_id]) % 10 == 0:
        try:
            curr_data = db.get_session(user_id)["data"]
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=_user_status_msg[user_id],
                text=f"Menerima & Menghitung... ({curr_data['total_file']} file, {curr_data['total_kontak']} kontak)\nKetik /done jika sudah semua."
            )
            _user_last_edit[user_id] = now
        except Exception:
            pass

async def handle_count_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if not sess or sess.get("state") != STATE:
        return
        
    # Tunggu semua task selesai
    tasks = _user_bg_tasks.get(user_id, set())
    if tasks:
        wait_msg = await update.message.reply_text("Menyelesaikan perhitungan terakhir...")
        await asyncio.gather(*tasks, return_exceptions=True)
        try: await wait_msg.delete() 
        except: pass
    
    _user_bg_tasks.pop(user_id, None)
    data = db.get_session(user_id)["data"]
    
    await update.message.reply_text(
        f"HASIL AKHIR:\n"
        f"Total File: {data['total_file']}\n"
        f"Total Kontak: {data['total_kontak']}"
    )
    
    db.clear_session(user_id)
    clear_user_dir(user_id)
    _user_status_msg.pop(user_id, None)
    _user_last_edit.pop(user_id, None)
