from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from middleware.session import clear_user_dir, clear_all_sessions
from middleware.auth import require_member, require_admin
from handlers.cancel_helper import cancel_all


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_member(update, context):
        return
    user_id = update.effective_user.id

    # Cancel semua proses aktif + bersihkan RAM
    cancel_all(user_id)
    db.clear_session(user_id)
    clear_user_dir(user_id)

    await update.message.reply_text(
        "✅ Sesi dan data sementara Anda berhasil dibersihkan.\n"
        "Gunakan /reset setiap selesai konversi agar RAM tetap bersih."
    )

    # Menu Tambahan buat Admin
    from config import ADMIN_IDS
    if user_id in ADMIN_IDS:
        keyboard = [
            [InlineKeyboardButton("⚠️ RESET TOTAL DATABASE", callback_data="admin_db_reset_confirm")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🛠 **ADMIN MENU**\n"
            "Anda dapat melakukan reset total database dan semua sesi user.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )


async def handle_reset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle konfirmasi reset dari admin"""
    query = update.callback_query

    # Safe admin check for callback queries (update.message is None for callbacks)
    from config import ADMIN_IDS
    if update.effective_user.id not in ADMIN_IDS:
        await query.answer("Akses ditolak.", show_alert=True)
        return

    await query.answer()  # Always answer immediately to dismiss spinner

    data = query.data

    if data == "admin_db_reset_confirm":
        keyboard = [
            [
                InlineKeyboardButton("✅ YA, HAPUS SEMUA", callback_data="admin_db_reset_final"),
                InlineKeyboardButton("❌ BATAL", callback_data="admin_db_reset_cancel")
            ]
        ]
        await query.edit_message_text(
            "❓ **KONFIRMASI AKHIR**\n"
            "Semua data user, member, dan log broadcast akan DIHAPUS PERMANEN.\n"
            "Tindakan ini tidak bisa dibatalkan!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data == "admin_db_reset_final":
        # Eksekusi Reset Total
        db.clear_all_db()
        clear_all_sessions()
        await query.edit_message_text(
            "🚀 **DATABASE RESET BERHASIL!**\nSistem kembali ke kondisi awal.",
            parse_mode="Markdown"
        )

    elif data == "admin_db_reset_cancel":
        await query.edit_message_text("❌ Reset dibatalkan.")