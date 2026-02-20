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
        f"Selamat datang di DiBot CV FEE.\n\n"
        f"Bot ini membantu Anda mengolah file VCF secara otomatis.\n\n"
        f"Untuk menjadi member dan mengakses semua fitur, silakan hubungi:\n"
        f"{ADMIN_CONTACT}\n\n"
        f"Bergabung ke grup kami: {GROUP_LINK}\n\n"
        f"Harga member: {HARGA_MEMBER}"
    )