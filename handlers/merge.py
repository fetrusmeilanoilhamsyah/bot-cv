"""
merge.py — Disk-based, terima paralel, urut by message_id, kirim 1 file output.
Mencegah OOM dengan menyimpan file ke disk.
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

STATE        = "MERGE_COLLECTING"
STATE_NAMING = "MERGE_NAMING"

MAX_FILES   = 40096
MAX_SIZE_MB = 500

_user_status_msg: dict = {}  # {user_id: message_id}
_user_bg_tasks: dict = {}   # {user_id: set(tasks)}
_user_last_edit: dict = {}  # {user_id: float}
_user_locks: dict = {}      # {user_id: Lock}

def get_user_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]

async def _bg_download(context, file_id: str, out_path: str, user_id: int):
    """Worker untuk download di background."""
    try:
        file_obj = await context.bot.get_file(file_id)
        await file_obj.download_to_drive(out_path)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"BG Download error user {user_id}: {e}")
    finally:
        # Hapus diri sendiri dari set task
        if user_id in _user_bg_tasks:
            _user_bg_tasks[user_id].discard(asyncio.current_task())

def _clear_buffers(user_id: int):
    user_dir = get_user_dir(user_id)
    merge_dir = os.path.join(user_dir, "merge")
    shutil.rmtree(merge_dir, ignore_errors=True)
    _user_status_msg.pop(user_id, None)
    _user_last_edit.pop(user_id, None)

async def cmd_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_member(update, context):
        return
    user_id = update.effective_user.id
    db.increment_usage(user_id)
    _clear_buffers(user_id)
    db.set_session(user_id, STATE, {"count": 0, "total_size": 0})
    await update.message.reply_text(
        "Kirim file VCF.\nKetik /done jika selesai."
    )

async def handle_merge_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    doc = update.message.document
    msg_id = update.message.message_id

    sess = db.get_session(user_id)
    if not sess or sess.get("state") != STATE:
        return

    # 1. Register background download
    user_dir = get_user_dir(user_id)
    merge_dir = os.path.join(user_dir, "merge")
    os.makedirs(merge_dir, exist_ok=True)
    out_path = os.path.join(merge_dir, f"{msg_id}.vcf")
    
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
        db.set_session(user_id, STATE, data)
        count = data["count"]

    # 3. Throttled UI Update (Instant Response for first file, then throttle)
    import time
    now = time.time()
    last = _user_last_edit.get(user_id, 0)
    
    if user_id not in _user_status_msg:
        # Pesan pertama: Kirim baru
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"Menerima file... ({count})",
            disable_notification=True
        )
        _user_status_msg[user_id] = msg.message_id
        _user_last_edit[user_id] = now
    elif now - last > 2.0 or count % 10 == 0:
        # Edit pesan yang sudah ada (Throttle 2 detik atau tiap 10 file)
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=_user_status_msg[user_id],
                text=f"Menerima file... ({count})\nKetik /done jika sudah semua."
            )
            _user_last_edit[user_id] = now
        except Exception:
            pass

async def handle_merge_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if not sess or sess.get("state") != STATE:
        return
    
    # Tunggu semua background download selesai
    tasks = _user_bg_tasks.get(user_id, set())
    if tasks:
        wait_msg = await update.message.reply_text("Menyelesaikan unduhan... Mohon tunggu.")
        await asyncio.gather(*tasks, return_exceptions=True)
        try: await wait_msg.delete() 
        except: pass
    
    _user_bg_tasks.pop(user_id, None)
    data = sess["data"]
    if data["count"] == 0:
        await update.message.reply_text("Belum ada file yang dikirim.")
        return

    db.set_session(user_id, STATE_NAMING, data)
    await update.message.reply_text(f"Berhasil menerima {data['count']} file. Berikan nama untuk file gabungan:")




async def handle_merge_naming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != STATE_NAMING:
        return
    data = dict(sess["data"])

    if data.get("is_processing"):
        return
    data["is_processing"] = True
    db.set_session(user_id, STATE_NAMING, data)

    file_name  = sanitize_filename(update.message.text.strip())
    total_files = data["count"]

    # Kirim progress awal
    progress_msg = await update.message.reply_text(
        f"Memproses {total_files} file... 0%"
    )

    user_dir  = get_user_dir(user_id)
    merge_dir = os.path.join(user_dir, "merge")

    # Kumpulkan file, urut berdasarkan message_id (DIJAMIN URUTAN)
    files = []
    if os.path.exists(merge_dir):
        files = sorted(
            [f for f in os.listdir(merge_dir) if f.endswith(".vcf")],
            key=lambda x: int(x.split(".")[0])
        )

    loop = asyncio.get_running_loop()

    def parse_one(fname):
        """Parse satu file VCF, return (index, contacts)"""
        import logging
        logger = logging.getLogger(__name__)
        path = os.path.join(merge_dir, fname)
        try:
            return parse_vcf_file(path)
        except Exception as e:
            logger.error("Merge parse error %s: %s", fname, e)
            return []

    def do_merge_parallel():
        """
        Parsing paralel dengan ThreadPoolExecutor (max 8 worker).
        Hasil dimasukkan ke dict {index: contacts} lalu digabung
        sesuai urutan asli (sudah sort by msg_id di atas).
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = {}  # {index: contacts}

        with ThreadPoolExecutor(max_workers=min(8, len(files) or 1)) as pool:
            future_to_idx = {pool.submit(parse_one, f): i for i, f in enumerate(files)}
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception:
                    results[idx] = []

        # Gabung sesuai urutan message_id (index 0,1,2,...)
        all_contacts = []
        for i in range(len(files)):
            all_contacts.extend(results.get(i, []))

        return all_contacts, contacts_to_vcf(all_contacts)

    # Edit progress tiap ~25% kalau file banyak
    async def update_progress(pct: int):
        try:
            await progress_msg.edit_text(f"Memproses {total_files} file... {pct}%")
        except Exception:
            pass

    if total_files > 10:
        await update_progress(10)

    all_contacts, vcf_output = await loop.run_in_executor(None, do_merge_parallel)

    await update_progress(90)

    if not all_contacts:
        try:
            await progress_msg.edit_text("Gagal. Kontak tidak ditemukan.")
        except Exception:
            await update.message.reply_text("Gagal. Kontak tidak ditemukan.")
        _clear_buffers(user_id)
        db.clear_session(user_id)
        return

    out_path = os.path.join(user_dir, f"{file_name}.vcf")
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(vcf_output)

        _clear_buffers(user_id)
        db.clear_session(user_id)

        await progress_msg.edit_text(
            f"Selesai. {len(all_contacts)} kontak dari {total_files} file."
        )
        with open(out_path, "rb") as f:
            await update.message.reply_document(document=f, filename=f"{file_name}.vcf")
    finally:
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass