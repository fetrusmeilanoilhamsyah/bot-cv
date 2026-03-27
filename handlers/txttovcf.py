"""
txttovcf.py — Disk-based, terima paralel, sort by message_id, tampilkan daftar file dulu, lalu kirim semua.
"""
import os
import shutil
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_member
from middleware.session import get_user_dir
from core.vcf_parser import add_plus, contacts_to_vcf
from core.utils import sanitize_filename, get_progress_bar

S1 = "TTV_CONTACT_NAME"
S2 = "TTV_PER_FILE"
S3 = "TTV_FILE_NAME"
S4 = "TTV_AWALAN"
S5 = "TTV_COLLECTING"

MAX_FILES   = 40096
MAX_SIZE_MB = 500

_user_status_msg: dict = {}
_user_bg_tasks: dict = {}
_user_last_edit: dict = {}
_user_locks: dict = {}

def get_user_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]

async def _bg_download(context, file_id: str, out_path: str, user_id: int):
    try:
        file_obj = await context.bot.get_file(file_id)
        await file_obj.download_to_drive(out_path)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"TTV BG Download error user {user_id}: {e}")
    finally:
        if user_id in _user_bg_tasks:
            _user_bg_tasks[user_id].discard(asyncio.current_task())

async def _delete_old_status(user_id: int, context):
    msg_id = _user_status_msg.pop(user_id, None)
    if msg_id:
        try: await context.bot.delete_message(chat_id=user_id, message_id=msg_id)
        except: pass

def _clear_buffers(user_id: int):
    user_dir = get_user_dir(user_id)
    ttv_dir = os.path.join(user_dir, "txttovcf")
    shutil.rmtree(ttv_dir, ignore_errors=True)
    _user_last_edit.pop(user_id, None)

async def cmd_txttovcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_member(update, context):
        return
    user_id = update.effective_user.id
    db.increment_usage(user_id)
    await _delete_old_status(user_id, context)
    _clear_buffers(user_id)
    db.set_session(user_id, S1, {})
    await update.message.reply_text("Nama kontak: (misal: FEE)")

async def handle_ttv_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    sess = db.get_session(user_id)
    if not sess or sess.get("state") != S5:
        return

    doc = update.message.document
    msg_id = update.message.message_id

    # 1. Register background download
    user_dir = get_user_dir(user_id)
    ttv_dir = os.path.join(user_dir, "txttovcf")
    os.makedirs(ttv_dir, exist_ok=True)
    out_path = os.path.join(ttv_dir, f"{msg_id}.txt")
    
    if user_id not in _user_bg_tasks:
        _user_bg_tasks[user_id] = set()
    
    task = asyncio.create_task(_bg_download(context, doc.file_id, out_path, user_id))
    _user_bg_tasks[user_id].add(task)

    # 2. Update Session (Locked)
    async with get_user_lock(user_id):
        sess = db.get_session(user_id)
        data = sess["data"]
        data["count"] += 1
        data["total_size"] += doc.file_size
        db.set_session(user_id, S5, data)
        count = data["count"]

    # 3. Throttled UI Update
    import time
    now = time.time()
    last = _user_last_edit.get(user_id, 0)
    received = len(_user_bg_tasks.get(user_id, set()))
    
    if user_id not in _user_status_msg:
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"📥 **Menerima file...** ({received})\n⚙️ Memproses... {get_progress_bar(count, received or 1)}",
            disable_notification=True
        )
        _user_status_msg[user_id] = msg.message_id
        _user_last_edit[user_id] = now
    elif now - last > 2.0 or count == received:
        try:
            bar = get_progress_bar(count, received or 1)
            status_text = (
                f"📥 **Menerima:** {received} file\n"
                f"⚙️ **Status:** {count}/{received} file terproses\n"
                f"{bar}\n\n"
            )
            if count == received and received > 0:
                status_text += "📂 **Siap!** Ketik /done untuk lanjut."
            else:
                status_text += "Ketik /done jika sudah semua."
                
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=_user_status_msg[user_id],
                text=status_text
            )
            _user_last_edit[user_id] = now
        except Exception:
            pass


async def handle_ttv_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != S1:
        return
    data = sess["data"]
    data["contact_name"] = update.message.text.strip()
    db.set_session(user_id, S2, data)
    await update.message.reply_text("Kontak per file: (misal: 50)")


async def handle_ttv_per_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != S2:
        return
    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text("Input angka valid.")
        return
    data = sess["data"]
    data["per_file"] = int(text)
    db.set_session(user_id, S3, data)
    await update.message.reply_text("Nama file: (misal: KONTAK)")


async def handle_ttv_file_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != S3:
        return
    data = sess["data"]
    data["file_name"] = sanitize_filename(update.message.text.strip())
    db.set_session(user_id, S4, data)
    await update.message.reply_text("Index mulai: (misal: 1)")


async def handle_ttv_awalan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != S4:
        return
    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text("Input angka valid.")
        return
    data = sess["data"]
    data["awalan"] = int(text)
    data["count"] = 0
    data["total_size"] = 0
    _clear_buffers(user_id)
    db.set_session(user_id, S5, data)
    await update.message.reply_text(
        "Kirim file TXT.\n"
        "Ketik /done jika selesai."
    )


# handle_ttv_file moved to top with background task logic


async def handle_ttv_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if not sess or sess.get("state") != S5:
        return
        
    # Tunggu semua background download selesai
    tasks = _user_bg_tasks.get(user_id, set())
    if tasks:
        wait_msg = await update.message.reply_text("Menyelesaikan unduhan... Mohon tunggu.")
        await asyncio.gather(*tasks, return_exceptions=True)
        try: await wait_msg.delete() 
        except: pass
    
    _user_bg_tasks.pop(user_id, None)
    await _delete_old_status(user_id, context)
    
    data = sess["data"]
    if data["count"] == 0:
        await update.message.reply_text("🚫 Belum ada file yang dikirim.")
        return
    if data.get("is_processing"):
        return

    data["is_processing"] = True
    db.set_session(user_id, S5, data)
    await update.message.reply_text("Memproses...")

    user_dir = get_user_dir(user_id)
    ttv_dir = os.path.join(user_dir, "txttovcf")
    
    files = []
    if os.path.exists(ttv_dir):
        files = [f for f in os.listdir(ttv_dir) if f.endswith('.txt')]
        files.sort(key=lambda x: int(x.split('.')[0]))

    contact_name = data["contact_name"]
    file_name    = data["file_name"]
    per_file     = data["per_file"]
    awalan       = data["awalan"]

    loop = asyncio.get_running_loop()

    def do_build():
        all_numbers = []
        for f in files:
            path = os.path.join(ttv_dir, f)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as file_in:
                    for line in file_in:
                        num = line.strip()
                        if num:
                            all_numbers.append(add_plus(num))
            except Exception:
                pass

        results = []
        contact_counter = 1
        file_counter = awalan
        
        # Simpan sementara di disk untuk per-file biar aman RAM nya
        out_temp_dir = os.path.join(user_dir, "txttovcf_out")
        os.makedirs(out_temp_dir, exist_ok=True)
        
        for i in range(0, len(all_numbers), per_file):
            chunk = all_numbers[i:i + per_file]
            contacts = [
                {"name": f"{contact_name}{contact_counter + j}", "tel": num}
                for j, num in enumerate(chunk)
            ]
            contact_counter += len(chunk)
            label = f"{file_name} {file_counter}"
            
            out_file = os.path.join(out_temp_dir, f"{label}.vcf")
            with open(out_file, "w", encoding="utf-8") as out_f:
                out_f.write(contacts_to_vcf(contacts))
            
            results.append((label, out_file))
            file_counter += 1
            
        return all_numbers, results, out_temp_dir

    all_numbers, results, out_temp_dir = await loop.run_in_executor(None, do_build)

    try:
        if not results:
            await update.message.reply_text("Gagal. Data tidak ditemukan.")
            return

        total_files = len(results)

        # ── Tampilkan ringkasan nama file dulu ───────────────────────────────
        header = f"{len(all_numbers)} kontak -> {total_files} file\n"
        lines  = [f"{file_name} {awalan + i}.vcf" for i in range(total_files)]

        CHUNK = 50
        for i in range(0, len(lines), CHUNK):
            msg = (header if i == 0 else "") + "\n".join(lines[i:i + CHUNK])
            await update.message.reply_text(msg)

        send_status = await update.message.reply_text(
            f"Menyiapkan {total_files} file..."
        )

        def read_bytes(path: str) -> bytes:
            with open(path, "rb") as f:
                return f.read()

        # asyncio.gather baca semua file bersamaan di thread pool
        file_bytes_list = await asyncio.gather(*[
            loop.run_in_executor(None, read_bytes, out_file)
            for _, out_file in results
        ])

        # ── STEP 2: Kirim SATU PER SATU dari memori — ORDER 100% TERJAMIN ──
        # Tidak ada disk I/O saat kirim, jadi tetap cepat
        import io
        for idx, ((label, _), file_bytes) in enumerate(zip(results, file_bytes_list), 1):
            await update.message.reply_document(
                document=io.BytesIO(file_bytes),
                filename=f"{label}.vcf"
            )
            # Update counter setiap 5 file
            if idx % 5 == 0 or idx == total_files:
                try:
                    await send_status.edit_text(
                        f"Mengirim {total_files} file... {idx}/{total_files}"
                    )
                except Exception:
                    pass

        try:
            await send_status.edit_text(f"Selesai. {total_files} file terkirim.")
        except Exception:
            pass

    finally:
        db.clear_session(user_id)
        _clear_buffers(user_id)
        try:
            shutil.rmtree(out_temp_dir, ignore_errors=True)
        except Exception:
            pass