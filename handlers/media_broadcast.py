"""
media_broadcast.py — Admin-only: kirim iklan berupa foto atau video ke semua user.
"""
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_admin
from config import ADMIN_IDS

STATE = "WAIT_BROADCAST_MEDIA"

async def cmd_media_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    db.set_session(update.effective_user.id, STATE, {})
    await update.message.reply_text("Kirim Foto atau Video yang akan di-broadcast:")

async def handle_broadcast_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if not sess or sess.get("state") != STATE:
        return

    # Deteksi jenis media
    media = None
    media_type = None
    
    if update.message.photo:
        media = update.message.photo[-1].file_id
        media_type = "photo"
    elif update.message.video:
        media = update.message.video.file_id
        media_type = "video"
    else:
        await update.message.reply_text("Gagal. Kirim foto atau video.")
        return

    caption = update.message.caption or ""
    db.clear_session(user_id)

    # Ambil semua user
    users = db.get_all_users()
    await update.message.reply_text(f"Memulai broadcast media ke {len(users)} user...")

    success = 0
    fail = 0
    for u in users:
        uid = u["id"]
        try:
            if media_type == "photo":
                await context.bot.send_photo(chat_id=uid, photo=media, caption=caption)
            else:
                await context.bot.send_video(chat_id=uid, video=media, caption=caption)
            success += 1
        except Exception:
            fail += 1
            
    await update.message.reply_text(f"Broadcast Selesai.\nBerhasil: {success}\nGagal: {fail}")
