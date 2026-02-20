"""
pecahvcf.py — In-memory approach.
"""
from io import BytesIO
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_member
from core.vcf_parser import parse_vcf, contacts_to_vcf

STATE_PER_FILE = "PECAH_PER_FILE"
STATE_WAIT_VCF = "PECAH_WAIT_VCF"


async def cmd_pecahvcf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_member(update, context):
        return
    user_id = update.effective_user.id
    db.set_session(user_id, STATE_PER_FILE, {})
    await update.message.reply_text("Berapa kontak per file? (contoh: 50)")


async def handle_pecah_per_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != STATE_PER_FILE:
        return
    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text("Masukkan angka yang valid, contoh: 50")
        return
    db.set_session(user_id, STATE_WAIT_VCF, {"per_file": int(text)})
    await update.message.reply_text("Kirimkan file VCF yang ingin dipecah.")


async def handle_pecah_vcf_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if sess["state"] != STATE_WAIT_VCF:
        return
    data = sess["data"]
    per_file = data["per_file"]

    await update.message.reply_text("Sedang memproses, harap tunggu...")

    # Download ke RAM
    doc = update.message.document
    file_obj = await context.bot.get_file(doc.file_id)
    bio = BytesIO()
    await file_obj.download_to_memory(bio)
    content = bio.getvalue().decode("utf-8", errors="ignore")

    contacts = parse_vcf(content)
    db.clear_session(user_id)

    total_files = 0
    for i in range(0, len(contacts), per_file):
        chunk = contacts[i:i + per_file]
        vcf_bytes = contacts_to_vcf(chunk).encode("utf-8")
        total_files += 1
        await update.message.reply_document(
            document=vcf_bytes,
            filename=f"PECAHAN{total_files}.vcf"
        )

    await update.message.reply_text(f"✅ Selesai. {total_files} file pecahan.")