"""
merge.py — Mendukung VCF dan TXT.
- VCF input  → output 1 file VCF gabungan
- TXT input  → output 1 file TXT gabungan (deduplikasi nomor)
- Disk-based, sort by message_id, mencegah OOM.
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
ALLOWED_EXT = {".vcf", ".txt"}

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
            jumlah = sess["data"]["count"]
            mode   = sess["data"].get("mode", "vcf").upper()
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{jumlah} file {mode} diterima. /done jika selesai."
            )


def _reset_timer(user_id: int, context, chat_id: int):
    old = _user_timers.get(user_id)
    if old:
        old.cancel()
    _user_timers[user_id] = asyncio.ensure_future(
        _debounce_notify(user_id, context, chat_id)
    )


def _cancel_timer(user_id: int):
    old = _user_timers.pop(user_id, None)
    if old:
        old.cancel()


def _clear_buffers(user_id: int):
    user_dir = get_user_dir(user_id)
    merge_dir = os.path.join(user_dir, "merge")
    shutil.rmtree(merge_dir, ignore_errors=True)


async def cmd_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_member(update, context):
        return
    user_id = update.effective_user.id
    db.increment_usage(user_id)
    _cancel_timer(user_id)
    _clear_buffers(user_id)
    db.set_session(user_id, STATE, {"count": 0, "total_size": 0, "mode": None})
    await update.message.reply_text(
        "Kirim file VCF atau TXT.\n"
        "Ketik /done jika selesai."
    )


async def handle_merge_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    doc     = update.message.document
    msg_id  = update.message.message_id

    sess = db.get_session(user_id)
    if sess["state"] != STATE:
        return

    # Guard: jangan terima file saat proses sudah berjalan
    if sess["data"].get("is_processing"):
        return

    # Validasi ekstensi file
    if not doc or not doc.file_name:
        await update.message.reply_text("Kirim file VCF atau TXT yang valid.")
        return

    ext = os.path.splitext(doc.file_name)[1].lower()
    if ext not in ALLOWED_EXT:
        await update.message.reply_text(
            f"Format tidak didukung: {ext}\n"
            "Hanya file .vcf atau .txt."
        )
        return

    # Ambil mode dari file pertama yang diterima
    async with get_user_lock(user_id):
        sess = db.get_session(user_id)
        if sess["state"] != STATE:
            return
        data = sess["data"]

        if data.get("is_processing"):
            return

        current_mode = data.get("mode")
        file_mode    = "vcf" if ext == ".vcf" else "txt"

        # Tolak jika mencampur VCF dan TXT
        if current_mode and current_mode != file_mode:
            await update.message.reply_text(
                f"Tidak bisa campur VCF dan TXT.\n"
                f"Sesi ini hanya menerima file .{current_mode}."
            )
            return

        if data["count"] >= MAX_FILES:
            await update.message.reply_text(f"Batas {MAX_FILES} file. Ketik /done.")
            return

        if (data["total_size"] + doc.file_size) / (1024 * 1024) > MAX_SIZE_MB:
            await update.message.reply_text(f"Batas {MAX_SIZE_MB}MB. Ketik /done.")
            return

        # Set mode jika belum ada
        if not current_mode:
            data["mode"] = file_mode

        data["count"]      += 1
        data["total_size"] += doc.file_size
        db.set_session(user_id, STATE, data)

    # Download ke disk setelah lock dilepas
    file_obj  = await context.bot.get_file(doc.file_id)
    user_dir  = get_user_dir(user_id)
    merge_dir = os.path.join(user_dir, "merge")
    os.makedirs(merge_dir, exist_ok=True)

    # Simpan dengan ekstensi asli agar filter di bawah benar
    out_path = os.path.join(merge_dir, f"{msg_id}{ext}")
    await file_obj.download_to_drive(out_path)

    _reset_timer(user_id, context, chat_id)


async def handle_merge_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    _cancel_timer(user_id)

    sess = db.get_session(user_id)
    if sess["state"] != STATE:
        return
    data = sess["data"]

    if data["count"] == 0:
        await update.message.reply_text("Belum ada file yang dikirim.")
        return

    mode = data.get("mode", "vcf")
    db.set_session(user_id, STATE_NAMING, data)
    await update.message.reply_text(
        f"{data['count']} file {mode.upper()} diterima.\n"
        "Nama file output:"
    )


async def handle_merge_naming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import logging
    logger = logging.getLogger(__name__)

    user_id = update.effective_user.id
    sess    = db.get_session(user_id)
    if sess["state"] != STATE_NAMING:
        return
    data = dict(sess["data"])

    if data.get("is_processing"):
        return
    data["is_processing"] = True
    db.set_session(user_id, STATE_NAMING, data)

    file_name   = sanitize_filename(update.message.text.strip())
    total_files = data["count"]
    mode        = data.get("mode", "vcf")   # "vcf" atau "txt"

    progress_msg = await update.message.reply_text(
        f"Menggabungkan {total_files} file {mode.upper()}... 0%"
    )

    user_dir  = get_user_dir(user_id)
    merge_dir = os.path.join(user_dir, "merge")

    # Kumpulkan file sesuai mode, urut by msg_id
    ext_filter = f".{mode}"
    files = []
    if os.path.exists(merge_dir):
        files = sorted(
            [f for f in os.listdir(merge_dir) if f.endswith(ext_filter)],
            key=lambda x: int(os.path.splitext(x)[0])
        )

    loop = asyncio.get_running_loop()

    async def update_progress(pct: int):
        try:
            await progress_msg.edit_text(
                f"Menggabungkan {total_files} file {mode.upper()}... {pct}%"
            )
        except Exception:
            pass

    out_path = None
    try:
        if mode == "vcf":
            # ── Mode VCF: parse & gabung semua kontak ──────────────────────
            def parse_one(fname):
                path = os.path.join(merge_dir, fname)
                try:
                    return parse_vcf_file(path)
                except Exception as e:
                    logger.error("Merge VCF parse error %s: %s", fname, e)
                    return []

            def do_merge_vcf():
                from concurrent.futures import ThreadPoolExecutor, as_completed
                results = {}
                with ThreadPoolExecutor(max_workers=min(8, len(files) or 1)) as pool:
                    future_to_idx = {pool.submit(parse_one, f): i for i, f in enumerate(files)}
                    for future in as_completed(future_to_idx):
                        idx = future_to_idx[future]
                        try:
                            results[idx] = future.result()
                        except Exception:
                            results[idx] = []

                all_contacts = []
                for i in range(len(files)):
                    all_contacts.extend(results.get(i, []))
                return all_contacts

            if total_files > 10:
                await update_progress(10)

            all_contacts = await loop.run_in_executor(None, do_merge_vcf)

            await update_progress(90)

            if not all_contacts:
                await progress_msg.edit_text("Gagal. Kontak tidak ditemukan di file VCF.")
                return

            out_path = os.path.join(user_dir, f"{file_name}.vcf")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(contacts_to_vcf(all_contacts))

            _clear_buffers(user_id)
            db.clear_session(user_id)

            await progress_msg.edit_text(
                f"Proses selesai.\n"
                f"Total file input : {total_files} VCF\n"
                f"Total kontak     : {len(all_contacts)} kontak"
            )
            with open(out_path, "rb") as f:
                await update.message.reply_document(
                    document=f, filename=f"{file_name}.vcf",
                    read_timeout=120, write_timeout=120, connect_timeout=60
                )

        else:
            # ── Mode TXT: gabung semua baris nomor, dedup ──────────────────
            def do_merge_txt():
                seen    = set()
                numbers = []
                for fname in files:
                    path = os.path.join(merge_dir, fname)
                    try:
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            for line in f:
                                num = line.strip()
                                if num and num not in seen:
                                    seen.add(num)
                                    numbers.append(num)
                    except Exception as e:
                        logger.error("Merge TXT read error %s: %s", fname, e)
                return numbers

            if total_files > 10:
                await update_progress(10)

            numbers = await loop.run_in_executor(None, do_merge_txt)

            await update_progress(90)

            if not numbers:
                await progress_msg.edit_text("Gagal. Nomor tidak ditemukan di file TXT.")
                return

            out_path = os.path.join(user_dir, f"{file_name}.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n".join(numbers))

            _clear_buffers(user_id)
            db.clear_session(user_id)

            await progress_msg.edit_text(
                f"Proses selesai.\n"
                f"Total file input : {total_files} TXT\n"
                f"Total nomor      : {len(numbers)} nomor (sudah deduplikasi)"
            )
            with open(out_path, "rb") as f:
                await update.message.reply_document(
                    document=f, filename=f"{file_name}.txt",
                    read_timeout=120, write_timeout=120, connect_timeout=60
                )

    finally:
        _clear_buffers(user_id)
        db.clear_session(user_id)
        if out_path:
            try:
                if os.path.exists(out_path):
                    os.remove(out_path)
            except Exception:
                pass