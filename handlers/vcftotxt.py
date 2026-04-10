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
from core.utils import sanitize_filename

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
    await asyncio.sleep(1)
    if _user_timers.get(user_id) is asyncio.current_task():
        sess = db.get_session(user_id)
        if sess and sess.get("state") == STATE:
            jumlah_file = sess["data"]["count"]
            jumlah_kontak = sess["data"].get("total_contacts", 0)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{jumlah_file} file diterima ({jumlah_kontak} kontak). /done jika selesai."
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
    db.increment_usage(user_id)
    _cancel_timer(user_id)
    _clear_buffers(user_id)
    db.set_session(user_id, STATE, {"count": 0, "total_size": 0, "total_contacts": 0})
    await update.message.reply_text(
        "Kirim file VCF.\nKetik /done jika selesai."
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
    
    orig_name = doc.file_name if doc.file_name else f"{msg_id}.vcf"
    safe_name = sanitize_filename(orig_name)
    out_path = os.path.join(v2t_dir, f"{msg_id}____{safe_name}")
    
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
        
        # Hitung jumlah kontak (BEGIN:VCARD)
        try:
            with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
                c = 0
                for line in f:
                    if "BEGIN:VCARD" in line.upper():
                        c += 1
                data["total_contacts"] = data.get("total_contacts", 0) + c
        except Exception:
            pass

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
        f"{sess['data']['count']} file diterima ({sess['data'].get('total_contacts', 0)} kontak). Nama file:"
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

    file_name   = sanitize_filename(update.message.text.strip())
    total_files = data["count"]

    progress_msg = await update.message.reply_text(
        f"Memproses {total_files} file... 0%"
    )

    user_dir = get_user_dir(user_id)
    v2t_dir  = os.path.join(user_dir, "vcftotxt")

    # Sorted by msg_id (prefix sebelum ____) — URUTAN DIJAMIN, tidak bergantung nama file
    files = []
    if os.path.exists(v2t_dir):
        raw_files = [f for f in os.listdir(v2t_dir) if f.endswith(".vcf")]
        
        def extract_msg_id(f_name):
            # Format simpan: {msg_id}____{safe_name}.vcf — ambil msg_id sebagai int
            try:
                return int(f_name.split("____")[0])
            except (ValueError, IndexError):
                return 0
            
        files = sorted(raw_files, key=extract_msg_id)

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

        # Pisahkan output menjadi 1 TXT per VCF
        results_files = []
        out_temp_dir = os.path.join(user_dir, "txt_reports")
        import shutil
        shutil.rmtree(out_temp_dir, ignore_errors=True)
        os.makedirs(out_temp_dir, exist_ok=True)

        for i, fname in enumerate(files):
            nums = results.get(i, [])
            
            label = f"{file_name} {i+1}"
            out_txt = os.path.join(out_temp_dir, f"{label}.txt")
            with open(out_txt, "w", encoding="utf-8") as file_out:
                file_out.write("\n".join(nums))
            results_files.append((label, out_txt))

        return results_files, out_temp_dir

    async def update_progress(pct: int):
        try:
            await progress_msg.edit_text(f"Memproses {total_files} file... {pct}%")
        except Exception:
            pass

    if total_files > 10:
        await update_progress(10)

    results_files, out_temp_dir = await loop.run_in_executor(None, do_export_parallel)

    await update_progress(90)

    try:
        from telegram import InputMediaDocument
        
        chunk_size = 10
        total_created = len(results_files)
        
        if total_created == 0:
            await progress_msg.edit_text("Gagal. Nomor tidak ditemukan.")
            return

        for i in range(0, total_created, chunk_size):
            chunk = results_files[i:i + chunk_size]
            
            media_group = []
            open_files = []
            for label, out_txt in chunk:
                f = open(out_txt, "rb")
                open_files.append(f)
                media_group.append(
                    InputMediaDocument(media=f, filename=f"{label}.txt")
                )
            
            try:
                if len(media_group) == 1:
                    # Kirim dengan reply_document, pastikan pakai string filename eksplisit
                    label_name, _ = chunk[0]
                    f_handle = open_files[0]
                    f_handle.seek(0)  # pastikan pointer di awal
                    await update.message.reply_document(
                        document=f_handle,
                        filename=f"{label_name}.txt",
                        read_timeout=120, connect_timeout=60, write_timeout=120
                    )
                else:
                    await update.message.reply_media_group(
                        media=media_group,
                        read_timeout=120, connect_timeout=60, write_timeout=120
                    )
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Gagal kirim media group vcftotxt: {e}")
            finally:
                for f in open_files:
                    try: f.close()
                    except: pass

        await progress_msg.edit_text(f"Selesai! {total_created} file TXT dikirim.")
    finally:
        db.clear_session(user_id)
        _clear_buffers(user_id)
        try:
            shutil.rmtree(out_temp_dir, ignore_errors=True)
        except Exception:
            pass