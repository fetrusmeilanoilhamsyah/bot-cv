from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.session import clear_user_dir
from middleware.auth import require_member
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
        "✅ Sesi dan data sementara berhasil dibersihkan.\n"
        "Gunakan /reset setiap selesai konversi agar RAM tetap bersih."
    )