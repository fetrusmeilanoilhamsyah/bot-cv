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
    await cancel_all(user_id, context)
    db.clear_session(user_id)
    clear_user_dir(user_id)

    await update.message.reply_text(
        "Sesi dibersihkan."
    )

    # Menu Tambahan buat Admin
    from config import ADMIN_IDS
    if user_id in ADMIN_IDS:
        keyboard = [
            [InlineKeyboardButton("⚠️ RESET TOTAL DATABASE", callback_data="admin_db_reset_confirm")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "ADMIN MENU\n"
            "Reset total database.",
            reply_markup=reply_markup
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
            "KONFIRMASI\n"
            "Hapus semua data permanent?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "admin_db_reset_final":
        # Eksekusi Reset Total
        db.clear_all_db()
        clear_all_sessions()
        await query.edit_message_text(
            "Database berhasil direset."
        )

    elif data == "admin_db_reset_cancel":
        await query.edit_message_text("Reset dibatalkan.")