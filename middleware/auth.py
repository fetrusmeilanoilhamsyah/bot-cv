"""
auth.py
Validasi membership user dan hak akses admin.
"""
from database import db
from config import ADMIN_IDS, ADMIN_CONTACT


async def require_member(update, context) -> bool:
    """
    Cek apakah user adalah member.
    Jika bukan, kirim pesan dan kembalikan False.
    """
    user_id = update.effective_user.id
    if not db.is_member(user_id):
        await update.message.reply_text(
            f"Anda belum menjadi member.\n"
            f"Hubungi {ADMIN_CONTACT} untuk mendaftar."
        )
        return False
    return True


def is_admin(user_id: int) -> bool:
    print(f"DEBUG: Checking is_admin for {user_id}. ADMIN_IDS: {ADMIN_IDS}")
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
