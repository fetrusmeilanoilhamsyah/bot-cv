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

STATE        = "VCF2TXT_COLLECTING"
STATE_NAMING = "VCF2TXT_NAMING"

MAX_FILES   = 40096
MAX_SIZE_MB = 500

_user_locks: dict = {}
_user_timers: dict = {}


def get_user_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]


async def _debounce_notify(user_id: int, context, chat_id: int):
    await asyncio.sleep(3)
    if _user_timers.get(user_id) is asyncio.current_task():
        sess = db.get_session(user_id)
        if sess and sess.get("state") == STATE:
            jumlah = sess["data"]["count"]
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{jumlah} file diterima. /done untuk selesai."
            )


def _reset_timer(user_id, context, chat_id):
    old = _user_timers.get(user_id)
    if old:
        old.cancel()
    _user_timers[user_id] = asyncio.ensure_future(
        _debounce_notify(user_id, context, chat_id)
    )


def _cancel_timer(user_id):
    old = _user_timers.pop(user_id, None)
    if old:
        old.cancel()


def _clear_buffers(user_id: int):
    user_dir = get_user_dir(user_id)
    v2t_dir = os.path.join(user_dir, "vcftotxt")
    shutil.rmtree(v2t_dir, ignore_errors=True)


async def cmd_vcftotxt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_member(update, context):
        return
    user_id = update.effective_user.id
    _cancel_timer(user_id)
    _clear_buffers(user_id)
    db.set_session(user_id, STATE, {"count": 0, "total_size": 0})
    await update.message.reply_text(
        "Kirim file VCF yang ingin dikonversi ke TXT. Boleh sekaligus banyak.\n"
        "/done setelah semua terkirim."
    )


async def handle_vcftotxt_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    sess = db.get_session(user_id)
    if sess["state"] != STATE:
        return

    doc = update.message.document
    msg_id = update.message.message_id
    
    file_obj = await context.bot.get_file(doc.file_id)
    user_dir = get_user_dir(user_id)
    v2t_dir = os.path.join(user_dir, "vcftotxt")
    os.makedirs(v2t_dir, exist_ok=True)
    out_path = os.path.join(v2t_dir, f"{msg_id}.vcf")
    
    await file_obj.download_to_drive(out_path)

    async with get_user_lock(user_id):
        sess = db.get_session(user_id)
        if sess["state"] != STATE:
            return
            
        data = sess["data"]
        
        if data.get("is_processing"):
            return
        if data["count"] >= MAX_FILES:
            await update.message.reply_text(f"Batas {MAX_FILES} file. Ketik /done.")
            return
        if (data.get("total_size", 0) + doc.file_size) / (1024 * 1024) > MAX_SIZE_MB:
            await update.message.reply_text(f"Batas {MAX_SIZE_MB}MB. Ketik /done.")
            return

        data["count"] += 1
        data["total_size"] = data.get("total_size", 0) + doc.file_size
        db.set_session(user_id, STATE, data)

    _reset_timer(user_id, context, chat_id)


async def handle_vcftotxt_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    _cancel_timer(user_id)

    sess = db.get_session(user_id)
    if sess["state"] != STATE:
        return
    if sess["data"]["count"] == 0:
        await update.message.reply_text("Belum ada file yang dikirim.")
        return

    db.set_session(user_id, STATE_NAMING, sess["data"])
    await update.message.reply_text(
        f"{sess['data']['count']} file diterima. Nama file output:"
    )


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

    file_name   = update.message.text.strip()
    total_files = data["count"]

    progress_msg = await update.message.reply_text(
        f"⚙️ Memproses {total_files} file... 0%"
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
            await progress_msg.edit_text(f"⚙️ Memproses {total_files} file... {pct}%")
        except Exception:
            pass

    if total_files > 10:
        await update_progress(10)

    numbers, out_txt = await loop.run_in_executor(None, do_export_parallel)

    await update_progress(90)

    try:
        if not numbers:
            await progress_msg.edit_text("❌ Gagal. Tidak ada nomor yang ditemukan.")
            _clear_buffers(user_id)
            try:
                if os.path.exists(out_txt):
                    os.remove(out_txt)
            except Exception:
                pass
            return

        await progress_msg.edit_text(
            f"✅ {len(numbers)} nomor diekstrak dari {total_files} file — urutan terjamin."
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