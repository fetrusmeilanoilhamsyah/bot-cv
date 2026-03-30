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
from core.utils import sanitize_filename

S0 = "TTV_WAIT_FILE"
S1 = "TTV_CONTACT_NAME"
S2 = "TTV_PER_FILE"
S3 = "TTV_FILE_NAME"
S4 = "TTV_AWALAN"
S5 = "TTV_COLLECTING"  # Will still keep this for backward compatibility if needed, but primary flow uses S0

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
        if sess and sess.get("state") in [S0, S5]:
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
    ttv_dir = os.path.join(user_dir, "txttovcf")
    shutil.rmtree(ttv_dir, ignore_errors=True)


async def cmd_txttovcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_member(update, context):
        return
    user_id = update.effective_user.id
    db.increment_usage(user_id)
    _cancel_timer(user_id)
    _clear_buffers(user_id)
    db.set_session(user_id, S0, {"count": 0, "total_size": 0, "total_contacts": 0})
    await update.message.reply_text(
        "Silakan kirim file TXT.\n"
        "Ketik /done jika sudah selesai mengirim semua file."
    )


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
    db.set_session(user_id, S4, data) # Keep S4 but trigger processing
    
    # Trigger processing immediately
    await handle_ttv_process(update, context)


async def handle_ttv_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    sess = db.get_session(user_id)
    if sess["state"] not in [S0, S5]:
        return

    doc = update.message.document
    msg_id = update.message.message_id

    # Download ke disk
    file_obj = await context.bot.get_file(doc.file_id)
    user_dir = get_user_dir(user_id)
    ttv_dir = os.path.join(user_dir, "txttovcf")
    os.makedirs(ttv_dir, exist_ok=True)
    out_path = os.path.join(ttv_dir, f"{msg_id}.txt")
    
    await file_obj.download_to_drive(out_path)

    async with get_user_lock(user_id):
        sess = db.get_session(user_id)
        if sess["state"] not in [S0, S5]:
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

        data["count"] += 1
        data["total_size"] += doc.file_size
        
        # Hitung jumlah kontak di file ini secara cerdas
        try:
            # We don't want to read the whole file if it's huge just for counting,
            # but for TXT to VCF we usually need to know how many lines.
            with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = 0
                for line in f:
                    if line.strip():
                        lines += 1
                data["total_contacts"] = data.get("total_contacts", 0) + lines
        except Exception:
            pass
            
        db.set_session(user_id, sess["state"], data)

    _reset_timer(user_id, context, chat_id)


async def handle_ttv_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    _cancel_timer(user_id)

    sess = db.get_session(user_id)
    if sess["state"] == S0:
        data = sess["data"]
        if data["count"] == 0:
            await update.message.reply_text("Belum ada file yang dikirim.")
            return
        
        db.set_session(user_id, S1, data)
        await update.message.reply_text(f"Total: {data.get('total_contacts', 0)} kontak.\n\nNama kontak: (misal: FEE)")
        return

    if sess["state"] not in [S0, S5]:
        return
    
    data = sess["data"]
    if data["count"] == 0:
        await update.message.reply_text("Belum ada file yang dikirim.")
        return
    if data.get("is_processing"):
        return

    data["is_processing"] = True
    db.set_session(user_id, sess["state"], data)
    await handle_ttv_process(update, context)

async def handle_ttv_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    data = sess["data"]
    
    # Check if already processing
    if data.get("is_processing_final"):
        return
    data["is_processing_final"] = True
    db.set_session(user_id, sess["state"], data)
    
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
        header = f"{header if 'header' in locals() else ''}{len(all_numbers)} kontak -> {total_files} file\n"
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