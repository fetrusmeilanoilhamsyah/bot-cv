"""
txttovcf.py — Terima paralel, sort by message_id, tampilkan daftar file dulu, lalu kirim semua.
"""
import asyncio
from io import BytesIO
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_member
from core.vcf_parser import add_plus, contacts_to_vcf

S1 = "TTV_CONTACT_NAME"
S2 = "TTV_PER_FILE"
S3 = "TTV_FILE_NAME"
S4 = "TTV_AWALAN"
S5 = "TTV_COLLECTING"

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
        if sess and sess.get("state") == S5:
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


async def cmd_txttovcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_member(update, context):
        return
    user_id = update.effective_user.id
    _cancel_timer(user_id)
    _user_buffers.pop(user_id, None)
    db.set_session(user_id, S1, {})
    await update.message.reply_text("Masukkan nama kontak:\n(contoh: FEE)")


async def handle_ttv_contact_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != S1:
        return
    data = sess["data"]
    data["contact_name"] = update.message.text.strip()
    db.set_session(user_id, S2, data)
    await update.message.reply_text("Berapa kontak per file? (contoh: 50)")


async def handle_ttv_per_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != S2:
        return
    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text("Masukkan angka yang valid, contoh: 50")
        return
    data = sess["data"]
    data["per_file"] = int(text)
    db.set_session(user_id, S3, data)
    await update.message.reply_text("Masukkan nama file output:\n(contoh: AYAM GORENG)")


async def handle_ttv_file_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != S3:
        return
    data = sess["data"]
    data["file_name"] = update.message.text.strip()
    db.set_session(user_id, S4, data)
    await update.message.reply_text("Nomor file diawali nomor berapa?\n(contoh: 1)")


async def handle_ttv_awalan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != S4:
        return
    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text("Masukkan angka yang valid, contoh: 1")
        return
    data = sess["data"]
    data["awalan"] = int(text)
    data["count"] = 0
    data["total_size"] = 0
    _user_buffers[user_id] = []
    db.set_session(user_id, S5, data)
    await update.message.reply_text(
        "Kirimkan semua file TXT Anda.\n"
        "Boleh kirim sekaligus banyak, ketik /done setelah selesai."
    )


async def handle_ttv_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    sess = db.get_session(user_id)
    if sess["state"] != S5:
        return

    doc = update.message.document
    msg_id = update.message.message_id

    # Download paralel tanpa lock
    file_obj = await context.bot.get_file(doc.file_id)
    bio = BytesIO()
    await file_obj.download_to_memory(bio)
    content = bio.getvalue()

    async with get_user_lock(user_id):
        sess = db.get_session(user_id)
        if sess["state"] != S5:
            return
        data = sess["data"]

        if data.get("is_processing"):
            return
        if data["count"] >= MAX_FILES:
            await update.message.reply_text(f"Batas {MAX_FILES} file. Ketik /done.")
            return
        if (data["total_size"] + doc.file_size) / (1024 * 1024) > MAX_SIZE_MB:
            await update.message.reply_text(f"Batas {MAX_SIZE_MB}MB. Ketik /done.")
            return

        if user_id not in _user_buffers:
            _user_buffers[user_id] = []
        _user_buffers[user_id].append((msg_id, content))
        data["count"] += 1
        data["total_size"] += doc.file_size
        db.set_session(user_id, S5, data)

    _reset_timer(user_id, context, chat_id)


async def handle_ttv_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    _cancel_timer(user_id)

    sess = db.get_session(user_id)
    if sess["state"] != S5:
        return
    data = sess["data"]

    if data["count"] == 0:
        await update.message.reply_text("Belum ada file yang dikirim.")
        return
    if data.get("is_processing"):
        return

    data["is_processing"] = True
    db.set_session(user_id, S5, data)
    await update.message.reply_text("⏳ Menyusun file, harap tunggu...")

    # Sort by message_id → urutan benar
    raw = _user_buffers.pop(user_id, [])
    raw.sort(key=lambda x: x[0])
    buffers = [c for _, c in raw]

    contact_name = data["contact_name"]
    file_name    = data["file_name"]
    per_file     = data["per_file"]
    awalan       = data["awalan"]

    loop = asyncio.get_event_loop()

    def do_build():
        all_numbers = []
        for b in buffers:
            for line in b.decode("utf-8", errors="ignore").splitlines():
                num = line.strip()
                if num:
                    all_numbers.append(add_plus(num))

        results = []
        contact_counter = 1
        file_counter = awalan
        for i in range(0, len(all_numbers), per_file):
            chunk = all_numbers[i:i + per_file]
            contacts = [
                {"name": f"{contact_name}{contact_counter + j}", "tel": num}
                for j, num in enumerate(chunk)
            ]
            contact_counter += len(chunk)
            label = f"{file_name} {file_counter}"
            vcf_bytes = contacts_to_vcf(contacts).encode("utf-8")
            results.append((label, vcf_bytes))
            file_counter += 1
        return all_numbers, results

    all_numbers, results = await loop.run_in_executor(None, do_build)
    db.clear_session(user_id)

    # ── Tampilkan daftar semua nama file dulu ──────────────────────────────
    # Kirim per 50 baris biar tidak kena batas pesan Telegram
    header = f"✅ {len(all_numbers)} kontak → {len(results)} file\n\n"
    lines = [f"{file_name} {awalan + i}.vcf" for i in range(len(results))]

    CHUNK = 50
    for i in range(0, len(lines), CHUNK):
        chunk_lines = lines[i:i + CHUNK]
        msg = (header if i == 0 else "") + "\n".join(chunk_lines)
        await update.message.reply_text(msg)

    # ── Baru kirim semua file setelah daftar selesai dikirim ───────────────
    await update.message.reply_text("📤 Mengirim file...")
    for label, vcf_bytes in results:
        await update.message.reply_document(
            document=vcf_bytes,
            filename=f"{label}.vcf"
        )