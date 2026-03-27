"""
vcftotxt.py — Disk-based approach to prevent OOM.
"""
import os
import shutil
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_member
from middleware.session import get_user_dir
from core.vcf_parser import parse_vcf_file
from core.utils import sanitize_filename, get_progress_bar

STATE        = "VCF2TXT_COLLECTING"
STATE_NAMING = "VCF2TXT_NAMING"

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
        logging.getLogger(__name__).error(f"V2T BG Download error user {user_id}: {e}")
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
    v2t_dir = os.path.join(user_dir, "vcftotxt")
    shutil.rmtree(v2t_dir, ignore_errors=True)
    _user_last_edit.pop(user_id, None)




async def cmd_vcftotxt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_member(update, context):
        return
    user_id = update.effective_user.id
    db.increment_usage(user_id)
    await _delete_old_status(user_id, context)
    _clear_buffers(user_id)
    db.set_session(user_id, STATE, {"count": 0, "total_size": 0})
    await update.message.reply_text(
        "📂 **MODE VCF KE TXT AKTIF**\nKirim file VCF.\nKetik /done jika selesai."
    )


async def handle_vcftotxt_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    sess = db.get_session(user_id)
    if not sess or sess.get("state") != STATE:
        return

    doc = update.message.document
    msg_id = update.message.message_id
    
    # 1. Register background download
    user_dir = get_user_dir(user_id)
    v2t_dir = os.path.join(user_dir, "vcftotxt")
    os.makedirs(v2t_dir, exist_ok=True)
    out_path = os.path.join(v2t_dir, f"{msg_id}.vcf")
    
    if user_id not in _user_bg_tasks:
        _user_bg_tasks[user_id] = set()
    
    task = asyncio.create_task(_bg_download(context, doc.file_id, out_path, user_id))
    _user_bg_tasks[user_id].add(task)

    # 2. Update Session (Locked)
    async with get_user_lock(user_id):
        sess = db.get_session(user_id)
        data = sess["data"]
        data["count"] += 1
        data["total_size"] = data.get("total_size", 0) + doc.file_size
        db.set_session(user_id, STATE, data)
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


async def handle_vcftotxt_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await _delete_old_status(user_id, context)
    
    data = sess["data"]
    if data["count"] == 0:
        await update.message.reply_text("🚫 Belum ada file yang dikirim.")
        return

    db.set_session(user_id, STATE_NAMING, data)
    await update.message.reply_text(f"✅ Berhasil menerima {data['count']} file.\nBerikan nama untuk hasil TXT:")


async def handle_vcftotxt_naming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != STATE_NAMING:
        return
    data = dict(sess["data"])  # copy — avoid mutating shared session cache object
    if data.get("is_processing"):
        return
    data["is_processing"] = True
    db.set_session(user_id, STATE_NAMING, data)

    file_name   = sanitize_filename(update.message.text.strip())
    total_files = data["count"]

    progress_msg = await update.message.reply_text(
        f"Memproses {total_files} file... 0%"
    )

    user_dir = get_user_dir(user_id)
    v2t_dir  = os.path.join(user_dir, "vcftotxt")

    # Sorted by message_id — URUTAN terjamin
    files = []
    if os.path.exists(v2t_dir):
        files = sorted(
            [f for f in os.listdir(v2t_dir) if f.endswith(".vcf")],
            key=lambda x: int(x.split(".")[0])
        )

    loop = asyncio.get_running_loop()

    def parse_one_vcf(fname):
        import logging
        logger = logging.getLogger(__name__)
        path = os.path.join(v2t_dir, fname)
        try:
            contacts = parse_vcf_file(path)
            return [c["tel"] for c in contacts]
        except Exception as e:
            logger.error("vcftotxt parse error %s: %s", fname, e)
            return []

    def do_export_parallel():
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = {}

        with ThreadPoolExecutor(max_workers=min(8, len(files) or 1)) as pool:
            future_to_idx = {pool.submit(parse_one_vcf, f): i for i, f in enumerate(files)}
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception:
                    results[idx] = []

        # Gabung nomor sesuai urutan file asli
        numbers = []
        for i in range(len(files)):
            numbers.extend(results.get(i, []))

        out_txt = os.path.join(user_dir, f"{file_name}.txt")
        with open(out_txt, "w", encoding="utf-8") as file_out:
            file_out.write("\n".join(numbers))

        return numbers, out_txt

    async def update_progress(pct: int):
        try:
            await progress_msg.edit_text(f"Memproses {total_files} file... {pct}%")
        except Exception:
            pass

    if total_files > 10:
        await update_progress(10)

    numbers, out_txt = await loop.run_in_executor(None, do_export_parallel)

    await update_progress(90)

    try:
        if not numbers:
            await progress_msg.edit_text("Gagal. Nomor tidak ditemukan.")
            _clear_buffers(user_id)
            try:
                if os.path.exists(out_txt):
                    os.remove(out_txt)
            except Exception:
                pass
            return

        await progress_msg.edit_text(
            f"Selesai. {len(numbers)} nomor dari {total_files} file."
        )
        with open(out_txt, "rb") as f:
            await update.message.reply_document(document=f, filename=f"{file_name}.txt")
    finally:
        db.clear_session(user_id)
        _clear_buffers(user_id)
        try:
            if os.path.exists(out_txt):
                os.remove(out_txt)
        except Exception:
            pass