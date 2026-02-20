"""
merge.py — In-memory, terima paralel, urut by message_id, kirim 1 file output.
"""
import os
import asyncio
from io import BytesIO
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_member
from middleware.session import get_user_dir
from core.vcf_parser import parse_vcf, contacts_to_vcf

STATE        = "MERGE_COLLECTING"
STATE_NAMING = "MERGE_NAMING"

MAX_FILES   = 40096
MAX_SIZE_MB = 500

_user_locks: dict = {}
_user_timers: dict = {}
_user_buffers: dict = {}  # {user_id: [(message_id, bytes)]}


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
                text=f"✅ {jumlah} file diterima. Ketik /done jika sudah selesai."
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
    _user_buffers.pop(user_id, None)


async def cmd_merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_member(update, context):
        return
    user_id = update.effective_user.id
    _cancel_timer(user_id)
    _clear_buffers(user_id)
    _user_buffers[user_id] = []
    db.set_session(user_id, STATE, {"count": 0, "total_size": 0})
    await update.message.reply_text(
        "Kirimkan semua file VCF yang ingin digabung.\n"
        "Boleh kirim sekaligus banyak, lalu ketik /done setelah selesai."
    )


async def handle_merge_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    doc = update.message.document
    msg_id = update.message.message_id  # ← urutan Telegram, selalu naik

    sess = db.get_session(user_id)
    if sess["state"] != STATE:
        return

    # Download paralel — tidak perlu lock
    file_obj = await context.bot.get_file(doc.file_id)
    bio = BytesIO()
    await file_obj.download_to_memory(bio)
    content_bytes = bio.getvalue()

    # Lock hanya saat update session
    async with get_user_lock(user_id):
        sess = db.get_session(user_id)
        if sess["state"] != STATE:
            return
        data = sess["data"]

        if data["count"] >= MAX_FILES:
            await update.message.reply_text(f"Batas {MAX_FILES} file. Ketik /done.")
            return

        if (data["total_size"] + doc.file_size) / (1024 * 1024) > MAX_SIZE_MB:
            await update.message.reply_text(f"Batas {MAX_SIZE_MB}MB. Ketik /done.")
            return

        if user_id not in _user_buffers:
            _user_buffers[user_id] = []
        _user_buffers[user_id].append((msg_id, content_bytes))  # ← simpan dengan msg_id

        data["count"] += 1
        data["total_size"] += doc.file_size
        db.set_session(user_id, STATE, data)

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

    db.set_session(user_id, STATE_NAMING, data)
    await update.message.reply_text(
        f"{data['count']} file diterima.\nMasukkan nama file output:"
    )


async def handle_merge_naming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != STATE_NAMING:
        return
    data = sess["data"]

    if data.get("is_processing"):
        return
    data["is_processing"] = True
    db.set_session(user_id, STATE_NAMING, data)

    file_name = update.message.text.strip()
    await update.message.reply_text("Sedang menggabungkan, harap tunggu...")

    # Ambil buffer, sort by message_id → urutan benar
    raw = _user_buffers.pop(user_id, [])
    raw.sort(key=lambda x: x[0])
    buffers = [b for _, b in raw]

    loop = asyncio.get_event_loop()

    def do_merge():
        all_contacts = []
        for b in buffers:
            all_contacts.extend(parse_vcf(b.decode("utf-8", errors="ignore")))
        return all_contacts, contacts_to_vcf(all_contacts)

    all_contacts, vcf_output = await loop.run_in_executor(None, do_merge)

    out_dir = get_user_dir(user_id)
    out_path = os.path.join(out_dir, f"{file_name}.vcf")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(vcf_output)

    db.clear_session(user_id)

    await update.message.reply_text(
        f"✅ {len(all_contacts)} kontak dari {data['count']} file."
    )
    with open(out_path, "rb") as f:
        await update.message.reply_document(document=f, filename=f"{file_name}.vcf")

    try:
        os.remove(out_path)
    except Exception:
        pass