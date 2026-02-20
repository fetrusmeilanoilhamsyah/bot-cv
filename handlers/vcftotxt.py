"""
vcftotxt.py — In-memory approach.
"""
import asyncio
from io import BytesIO
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_member
from core.vcf_parser import parse_vcf

STATE        = "VCF2TXT_COLLECTING"
STATE_NAMING = "VCF2TXT_NAMING"

_user_locks: dict = {}
_user_timers: dict = {}
_user_buffers: dict = {}


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


async def cmd_vcftotxt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_member(update, context):
        return
    user_id = update.effective_user.id
    _cancel_timer(user_id)
    _user_buffers[user_id] = []
    db.set_session(user_id, STATE, {"count": 0})
    await update.message.reply_text(
        "Kirimkan semua file VCF yang ingin dikonversi ke TXT.\n"
        "Boleh kirim sekaligus banyak, lalu ketik /done setelah selesai."
    )


async def handle_vcftotxt_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    sess = db.get_session(user_id)
    if sess["state"] != STATE:
        return

    file_obj = await context.bot.get_file(update.message.document.file_id)
    bio = BytesIO()
    await file_obj.download_to_memory(bio)

    async with get_user_lock(user_id):
        sess = db.get_session(user_id)
        if sess["state"] != STATE:
            return
        if user_id not in _user_buffers:
            _user_buffers[user_id] = []
        _user_buffers[user_id].append(bio.getvalue())
        data = sess["data"]
        data["count"] += 1
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
        f"{sess['data']['count']} file diterima.\nMasukkan nama file output:"
    )


async def handle_vcftotxt_naming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != STATE_NAMING:
        return
    if sess["data"].get("is_processing"):
        return

    sess["data"]["is_processing"] = True
    db.set_session(user_id, STATE_NAMING, sess["data"])

    file_name = update.message.text.strip()
    buffers = _user_buffers.pop(user_id, [])

    loop = asyncio.get_event_loop()

    def do_export():
        numbers = []
        for raw in buffers:
            contacts = parse_vcf(raw.decode("utf-8", errors="ignore"))
            numbers.extend(c["tel"] for c in contacts)
        return numbers

    numbers = await loop.run_in_executor(None, do_export)
    db.clear_session(user_id)

    txt_bytes = "\n".join(numbers).encode("utf-8")
    await update.message.reply_text(f"✅ {len(numbers)} nomor diekstrak.")
    await update.message.reply_document(
        document=txt_bytes,
        filename=f"{file_name}.txt"
    )