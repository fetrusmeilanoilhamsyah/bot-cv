"""
auth.py
Validasi membership user dan hak akses admin.
"""
import logging
from database import db
from config import ADMIN_IDS, ADMIN_CONTACT

logger = logging.getLogger(__name__)


async def require_member(update, context) -> bool:
    """
    Cek apakah user adalah member.
    Jika bukan, kirim pesan + tombol VIP dan kembalikan False.
    """
    user_id = update.effective_user.id
    if not db.is_member(user_id):
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        admin_url = f"https://t.me/{ADMIN_CONTACT.lstrip('@')}"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👑 Daftar VIP Sekarang", url=admin_url)],
            [InlineKeyboardButton("Lihat Paket & Harga", callback_data="show_vip_menu")],
        ])
        await update.message.reply_text(
            "Fitur ini eksklusif untuk member VIP.\n"
            "Harga terjangkau, mulai Rp 5.000 saja!",
            reply_markup=keyboard
        )
        return False
    return True


def is_admin(user_id: int) -> bool:
    logger.debug("Checking is_admin for %s", user_id)
    return user_id in ADMIN_IDS


async def require_admin(update, context) -> bool:
    """
    Cek apakah user adalah admin.
    Jika bukan, kirim pesan dan kembalikan False.
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Perintah ini hanya untuk admin.")
        return False
    return True
