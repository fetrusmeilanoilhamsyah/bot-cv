import os
import re
import csv
import logging
import asyncio
from io import BytesIO
from telegram import Update, Document
from telegram.ext import ContextTypes
from database import db
from middleware.session import get_user_dir, clear_user_dir
from core.utils import sanitize_filename

logger = logging.getLogger(__name__)

STATE = "XLSX2TXT_COLLECTING"

_user_status_msg: dict = {}
_user_bg_tasks: dict = {}
_user_last_edit: dict = {}
_user_locks: dict = {}

def get_user_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]

# Regex cerdas untuk menangkap format Internasional (+593, 1, 60, dll) maupun Lokal (08xx)
# Didukung penangkapan spasi, strip, atau kurung (misal: +593 99-341-1006)
PHONE_REGEX = re.compile(r'\+?(?:\d[\s\-\(\)\.]*){8,16}')

def _extract_numbers_sync(filepath: str, ext: str) -> list:
    """Ekstrak nomor HP dari Excel/CSV secara sinkron via openpyxl/csv (BERURUTAN)"""
    numbers = []
    seen = set()
    try:
        def process_cell(cell_value):
            if not cell_value: return
            text = str(cell_value)
            for m in PHONE_REGEX.findall(text):
                clean_num = re.sub(r'[^0-9]', '', m)
                if clean_num.startswith("08"):
                    clean_num = "62" + clean_num[1:]
                if 8 <= len(clean_num) <= 15 and clean_num not in seen:
                    seen.add(clean_num)
                    numbers.append(clean_num)

        if ext == ".csv":
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                for row in reader:
                    for cell in row:
                        process_cell(cell)
        else:
            import openpyxl
            wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True)
            for sheet in wb.sheetnames:
                ws = wb[sheet]
                for row in ws.iter_rows(values_only=True):
                    for cell in row:
                        process_cell(cell)
            wb.close()
            
    except Exception as e:
        logger.error("Error ekstrak %s: %s", filepath, e)
    return numbers

async def _bg_process_xlsx(context, file_id: str, file_path: str, ext: str, user_id: int):
    """Worker untuk download dan ekstrak nomor di background."""
    try:
        # 1. Download
        file_obj = await context.bot.get_file(file_id)
        await file_obj.download_to_drive(file_path)
        
        # 2. Extract
        loop = asyncio.get_running_loop()
        found_numbers = await loop.run_in_executor(None, _extract_numbers_sync, file_path, ext)
        
        # 3. Update Master File & DB (Locked)
        async with get_user_lock(user_id):
            user_dir = get_user_dir(user_id)
            master_txt = os.path.join(user_dir, "extracted_numbers.txt")
            
            with open(master_txt, 'r', encoding='utf-8', errors='ignore') as f:
                existing = f.read().splitlines()
            
            seen = set(existing)
            combined = list(existing)
            new_additions = 0
            for num in found_numbers:
                if num not in seen:
                    seen.add(num)
                    combined.append(num)
                    new_additions += 1
            
            with open(master_txt, 'w', encoding='utf-8') as f:
                f.write("\n".join(combined))
                
            sess = db.get_session(user_id)
            if sess and sess.get("state") == STATE:
                data = sess["data"]
                data["total_file"] += 1
                data["total_kontak"] = len(combined)
                db.set_session(user_id, STATE, data)
                
    except Exception as e:
        logger.error(f"XLSX BG process error user {user_id}: {e}")
    finally:
        if user_id in _user_bg_tasks:
            _user_bg_tasks[user_id].discard(asyncio.current_task())

async def cmd_xlsxtotxt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.increment_usage(user_id)
    clear_user_dir(user_id)
    _user_status_msg.pop(user_id, None)
    _user_last_edit.pop(user_id, None)
    _user_bg_tasks.pop(user_id, None)
    
    user_dir = get_user_dir(user_id)
    master_txt = os.path.join(user_dir, "extracted_numbers.txt")
    os.makedirs(user_dir, exist_ok=True)
    open(master_txt, 'w').close()
    
    db.set_session(user_id, STATE, {"total_kontak": 0, "total_file": 0})
    await update.message.reply_text(
        "Kirim file Excel (.xlsx) atau CSV (.csv).\n"
        "Klik /done jika selesai."
    )

async def handle_xlsxtotxt_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    sess = db.get_session(user_id)
    if not sess or sess.get("state") != STATE:
        return
        
    doc = update.message.document
    if not doc or not doc.file_name:
        return
        
    ext = os.path.splitext(doc.file_name)[1].lower()
    if ext not in [".xlsx", ".xls", ".csv"]:
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
    
    task = asyncio.create_task(_bg_process_xlsx(context, doc.file_id, file_path, ext, user_id))
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
    elif now - last > 2.0 or len(_user_bg_tasks[user_id]) % 5 == 0:
        try:
            curr_data = db.get_session(user_id)["data"]
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=_user_status_msg[user_id],
                text=f"Menerima & Ekstrak... ({curr_data['total_file']} file, {curr_data['total_kontak']} kontak unik)\nKetik /done jika sudah semua."
            )
            _user_last_edit[user_id] = now
        except Exception:
            pass

async def handle_xlsxtotxt_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if not sess or sess.get("state") != STATE:
        return
        
    # Tunggu semua task selesai
    tasks = _user_bg_tasks.get(user_id, set())
    if tasks:
        wait_msg = await update.message.reply_text("Menyelesaiakan ekstraksi terakhir...")
        await asyncio.gather(*tasks, return_exceptions=True)
        try: await wait_msg.delete() 
        except: pass
    
    _user_bg_tasks.pop(user_id, None)
    data = db.get_session(user_id)["data"] # Ambil data terupdate
    total = data.get("total_kontak", 0)
    
    if total == 0:
        await update.message.reply_text("Nomor tidak ditemukan.")
        db.clear_session(user_id)
        clear_user_dir(user_id)
        return
        
    user_dir = get_user_dir(user_id)
    master_txt = os.path.join(user_dir, "extracted_numbers.txt")
    
    try:
        with open(master_txt, 'rb') as f:
            buffer = BytesIO(f.read())
            buffer.name = "Hasil_Ekstrak_Excel.txt"
            
        await update.message.reply_document(
            document=buffer,
            caption=f"HASIL AKHIR:\nTotal File: {data['total_file']}\nTotal Kontak Unik: {total}"
        )
    except Exception as e:
        logger.error("Error kirim hasil xlsx: %s", e)
        await update.message.reply_text("Gagal mengirim hasil.")
        
    finally:
        db.clear_session(user_id)
        clear_user_dir(user_id)
        _user_status_msg.pop(user_id, None)
        _user_last_edit.pop(user_id, None)
