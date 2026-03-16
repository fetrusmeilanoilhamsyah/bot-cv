"""
main.py - OPTIMIZED VERSION
Entry point DiBot CV FEE.

CHANGELOG:
- Set concurrent_updates = 8 (max 8 parallel processes)
- Naikin timeout configuration
- Add rate limiting middleware
- Fix logging level
"""
import logging
import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from config import BOT_TOKEN
from database import db

from handlers.start import cmd_start
from handlers.reset import cmd_reset
from handlers.admin_navy import (
    cmd_admin,
    handle_admin_navy,
    STATES as AN_STATES,
)
from handlers.merge import (
    cmd_merge,
    handle_merge_file,
    handle_merge_done,
    handle_merge_naming,
    STATE as MERGE_STATE,
    STATE_NAMING as MERGE_NAMING,
)
from handlers.vcftotxt import (
    cmd_vcftotxt,
    handle_vcftotxt_file,
    handle_vcftotxt_done,
    handle_vcftotxt_naming,
    STATE as VCF2TXT_STATE,
    STATE_NAMING as VCF2TXT_NAMING,
)
from handlers.pecahvcf import (
    cmd_pecahvcf,
    handle_pecah_per_file,
    handle_pecah_vcf_file,
    STATE_PER_FILE as PECAH_S1,
    STATE_WAIT_VCF as PECAH_S2,
)
from handlers.rename import (
    cmd_rename,
    handle_rename_name,
    handle_rename_file,
    STATE_NAME as RENAME_S1,
    STATE_FILE as RENAME_S2,
)
from handlers.txttovcf import (
    cmd_txttovcf,
    handle_ttv_contact_name,
    handle_ttv_per_file,
    handle_ttv_file_name,
    handle_ttv_awalan,
    handle_ttv_file,
    handle_ttv_done,
    S1, S2, S3, S4, S5,
)
from handlers.broadcast import (
    cmd_broadcast,
    handle_broadcast_msg,
    STATE as BROADCAST_STATE,
)
from handlers.new_member import (
    cmd_newmember,
    handle_newmember_id,
    STATE as NEWMEMBER_STATE,
)

# Rate limiting imports
from asyncio import Semaphore
from collections import defaultdict

os.makedirs("logs", exist_ok=True)

# ===== OPTIMIZED LOGGING =====
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,  # Changed from WARNING to INFO
    handlers=[
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ===== RATE LIMITING =====
MAX_CONCURRENT_PER_USER = 2  # Max 2 operations per user at once
user_semaphores = defaultdict(lambda: Semaphore(MAX_CONCURRENT_PER_USER))


async def rate_limiter(func):
    """Decorator untuk rate limiting per user"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text if update.message else "NON-TEXT"
        logger.info(f"Incoming: User {user_id} -> {text}")
        
        semaphore = user_semaphores[user_id]
        
        async with semaphore:
            return await func(update, context)
    
    return wrapper


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception saat handle update:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            "Terjadi kesalahan. Ketik /reset untuk mereset sesi."
        )


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    state = sess.get("state")

    if state in AN_STATES.values():
        await handle_admin_navy(update, context)
    elif state == MERGE_NAMING:
        await handle_merge_naming(update, context)
    elif state == VCF2TXT_NAMING:
        await handle_vcftotxt_naming(update, context)
    elif state == PECAH_S1:
        await handle_pecah_per_file(update, context)
    elif state == RENAME_S1:
        await handle_rename_name(update, context)
    elif state == S1:
        await handle_ttv_contact_name(update, context)
    elif state == S2:
        await handle_ttv_per_file(update, context)
    elif state == S3:
        await handle_ttv_file_name(update, context)
    elif state == S4:
        await handle_ttv_awalan(update, context)
    elif state == BROADCAST_STATE:
        await handle_broadcast_msg(update, context)
    elif state == NEWMEMBER_STATE:
        await handle_newmember_id(update, context)


async def file_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    state = sess.get("state")

    if state == MERGE_STATE:
        await handle_merge_file(update, context)
    elif state == VCF2TXT_STATE:
        await handle_vcftotxt_file(update, context)
    elif state == PECAH_S2:
        await handle_pecah_vcf_file(update, context)
    elif state == RENAME_S2:
        await handle_rename_file(update, context)
    elif state == S5:
        await handle_ttv_file(update, context)


async def done_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    state = sess.get("state")

    if state == MERGE_STATE:
        await handle_merge_done(update, context)
    elif state == VCF2TXT_STATE:
        await handle_vcftotxt_done(update, context)
    elif state == S5:
        await handle_ttv_done(update, context)
    else:
        await update.message.reply_text("Tidak ada proses aktif yang bisa diselesaikan.")


def main():
    """
    OPTIMIZED APPLICATION BUILDER
    
    Key changes:
    1. concurrent_updates = 8 (was True = unlimited)
    2. connection_pool_size = 32 (tetap)
    3. pool_timeout = 60 (was 30)
    4. read_timeout = 60 (was 30)
    5. write_timeout = 120 (was 60)
    6. connect_timeout = 30 (was 15)
    """
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(8)        # CHANGED: Max 8 concurrent (was True)
        .connection_pool_size(32)     # Keep as is
        .pool_timeout(60)             # CHANGED: 30 → 60
        .read_timeout(60)             # CHANGED: 30 → 60
        .write_timeout(120)           # CHANGED: 60 → 120
        .connect_timeout(30)          # CHANGED: 15 → 30
        .build()
    )

    # Command handlers
    app.add_handler(CommandHandler("start", await rate_limiter(cmd_start)))
    app.add_handler(CommandHandler("reset", await rate_limiter(cmd_reset)))
    app.add_handler(CommandHandler("admin", await rate_limiter(cmd_admin)))
    app.add_handler(CommandHandler("merge", await rate_limiter(cmd_merge)))
    app.add_handler(CommandHandler("vcftotxt", await rate_limiter(cmd_vcftotxt)))
    app.add_handler(CommandHandler("pecahvcf", await rate_limiter(cmd_pecahvcf)))
    app.add_handler(CommandHandler("rename", await rate_limiter(cmd_rename)))
    app.add_handler(CommandHandler("txttovcf", await rate_limiter(cmd_txttovcf)))
    app.add_handler(CommandHandler("broadcast", await rate_limiter(cmd_broadcast)))
    app.add_handler(CommandHandler("newmember", await rate_limiter(cmd_newmember)))
    app.add_handler(CommandHandler("done", await rate_limiter(done_router)))

    # Callback Query Handler (no rate limiter for callbacks yet)
    from handlers.reset import handle_reset_callback
    app.add_handler(CallbackQueryHandler(handle_reset_callback, pattern="^admin_db_reset"))

    # Message handlers (wrapped with rate limiter)
    app.add_handler(MessageHandler(filters.Document.ALL, await rate_limiter(file_router)))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, await rate_limiter(text_router)))

    # Error handler
    app.add_error_handler(error_handler)

    logger.info("🚀 DiBot CV FEE berjalan (OPTIMIZED VERSION)...")
    print("🚀 DiBot CV FEE berjalan (OPTIMIZED VERSION)...")
    print(f"📊 Max concurrent updates: 8")
    print(f"⏱️  Timeouts: pool=60s, read=60s, write=120s, connect=30s")
    print(f"🔐 Rate limit: Max {MAX_CONCURRENT_PER_USER} operations per user")
    
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
