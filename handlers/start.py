from telegram import Update
from telegram.ext import ContextTypes
from database import db
from config import ADMIN_CONTACT, GROUP_LINK, HARGA_MEMBER
from middleware.session import clear_user_dir
from handlers.cancel_helper import cancel_all


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Cancel semua proses aktif user saat /start
    cancel_all(user.id)
    db.clear_session(user.id)
    clear_user_dir(user.id)

    # Daftarkan user ke database
    db.upsert_user(user.id, user.username or "", user.full_name or "")

    await update.message.reply_text(
        f"<b>DIBOT CV FEE</b>\n"
        f"────────────────────\n"
        f"Sistem pengolah file VCF otomatis untuk optimasi database kontak Anda.\n\n"
        f"<b>Akses & Layanan:</b>\n"
        f"• Admin: {ADMIN_CONTACT}\n"
        f"• Community: {GROUP_LINK}\n"
        f"• Membership: {HARGA_MEMBER}\n\n"
        f"Gunakan menu perintah untuk memulai.",
        parse_mode="HTML"
    )