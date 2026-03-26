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
from handlers.count import (
    STATE as COUNT_STATE,
    cmd_count,
    handle_count_file,
    handle_count_done,
)
from handlers.xlsxtotxt import (
    STATE as XLSX2TXT_STATE,
    cmd_xlsxtotxt,
    handle_xlsxtotxt_file,
    handle_xlsxtotxt_done,
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
from handlers.del_member import (
    cmd_delmember,
    handle_delmember_id,
    STATE as DELMEMBER_STATE,
)
from handlers.daftar import cmd_daftar
from handlers.vip import cmd_vip
from handlers.addvip import cmd_addvip, cmd_delvip
from handlers.stat import cmd_stat

# Rate limiting imports
from asyncio import Semaphore
from collections import defaultdict

os.makedirs("logs", exist_ok=True)

# ===== OPTIMIZED LOGGING =====
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # Mencegah spam log getUpdates HTTP
logger = logging.getLogger(__name__)

# ===== RATE LIMITING =====
MAX_CONCURRENT_PER_USER = 2  # Max 2 operations per user at once
user_semaphores = defaultdict(lambda: Semaphore(MAX_CONCURRENT_PER_USER))


def rate_limiter(func):
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
    from telegram.error import NetworkError, TimedOut
    # NetworkError / TimedOut = koneksi putus sesaat — PTB auto-retry, tidak perlu crash
    if isinstance(context.error, (NetworkError, TimedOut)):
        logger.warning("Network error (akan auto-retry): %s", context.error)
        return

    logger.error("Exception saat handle update:", exc_info=context.error)

    # Kirim alert ke semua admin di Telegram
    from config import ADMIN_IDS
    import traceback
    tb = "".join(traceback.format_exception(type(context.error), context.error, context.error.__traceback__))
    short_tb = tb[-1500:] if len(tb) > 1500 else tb  # Telegram max 4096 chars
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"<b>ERROR BOT</b>\n<pre>{short_tb}</pre>",
                parse_mode="HTML"
            )
        except Exception:
            pass

    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            "Terjadi kesalahan. Ketik /reset untuk mereset sesi."
        )


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if not sess:
        return

    state = sess.get("state")

    if update.message and update.message.text and update.message.text.strip().lower() in ["selesai", "done"]:
        await done_router(update, context)
        return

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
    elif state == DELMEMBER_STATE:
        await handle_delmember_id(update, context)


async def file_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if not sess:
        return
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
    elif state == COUNT_STATE:
        await handle_count_file(update, context)
    elif state == XLSX2TXT_STATE:
        await handle_xlsxtotxt_file(update, context)

# The done_router function is now integrated into text_router for "selesai", "/done", "done" messages.
# However, the CommandHandler("done", ...) still needs a function.
# We can keep a simplified done_router for the /done command specifically.
async def done_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    if not sess:
        await update.message.reply_text("Tidak ada proses aktif.")
        return
    state = sess.get("state")

    if state == MERGE_STATE:
        await handle_merge_done(update, context)
    elif state == VCF2TXT_STATE:
        await handle_vcftotxt_done(update, context)
    elif state == S5:
        await handle_ttv_done(update, context)
    elif state == COUNT_STATE:
        await handle_count_done(update, context)
    elif state == XLSX2TXT_STATE:
        await handle_xlsxtotxt_done(update, context)
    else:
        await update.message.reply_text("Tidak ada proses aktif yang bisa diselesaikan.")


def main():
    """
    OPTIMIZED APPLICATION BUILDER UNTUK 50-100 USER BERSAMAAN
    """
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(32)       # Max 32 request diproses paralel bersamaan
        .connection_pool_size(100)    # Naikkan pool network request ke Telegram API
        .pool_timeout(60)
        .read_timeout(60)
        .write_timeout(120)
        .connect_timeout(30)
        .build()
    )

    # Command handlers
    app.add_handler(CommandHandler("start", rate_limiter(cmd_start)))
    app.add_handler(CommandHandler(["reset", "resetdatabase"], rate_limiter(cmd_reset)))
    app.add_handler(CommandHandler(["admin", "Admin"], rate_limiter(cmd_admin)))
    app.add_handler(CommandHandler("txttovcf", rate_limiter(cmd_txttovcf)))
    app.add_handler(CommandHandler("xlsxtotxt", rate_limiter(cmd_xlsxtotxt)))
    app.add_handler(CommandHandler("merge", rate_limiter(cmd_merge)))
    app.add_handler(CommandHandler("vcftotxt", rate_limiter(cmd_vcftotxt)))
    app.add_handler(CommandHandler("pecahvcf", rate_limiter(cmd_pecahvcf)))
    app.add_handler(CommandHandler("rename", rate_limiter(cmd_rename)))
    app.add_handler(CommandHandler("count", rate_limiter(cmd_count)))
    app.add_handler(CommandHandler(["broadcast", "brodcast", "Brodcast"], rate_limiter(cmd_broadcast)))
    app.add_handler(CommandHandler("newmember", rate_limiter(cmd_newmember)))
    app.add_handler(CommandHandler(["delmember", "copotmember"], rate_limiter(cmd_delmember)))
    app.add_handler(CommandHandler("daftar", rate_limiter(cmd_daftar)))
    app.add_handler(CommandHandler("vip", rate_limiter(cmd_vip)))
    app.add_handler(CommandHandler("addvip", rate_limiter(cmd_addvip)))
    app.add_handler(CommandHandler("delvip", rate_limiter(cmd_delvip)))
    app.add_handler(CommandHandler("stat", rate_limiter(cmd_stat)))
    app.add_handler(CommandHandler("done", rate_limiter(done_router)))

    # Callback Query Handlers
    from handlers.reset import handle_reset_callback

    async def cb_show_vip_menu(update, context):
        query = update.callback_query
        await query.answer()
        # Fake update object for cmd_vip since it expects a message
        class FakeUpdate:
            message = query.message
            effective_user = update.effective_user
        await cmd_vip(FakeUpdate(), context)

    app.add_handler(CallbackQueryHandler(cb_show_vip_menu, pattern="^show_vip_menu$"))
    app.add_handler(CallbackQueryHandler(handle_reset_callback, pattern="^admin_db_reset"))

    # Message handlers (wrapped with rate limiter)
    app.add_handler(MessageHandler(filters.Document.ALL, rate_limiter(file_router)))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, rate_limiter(text_router)))

    # Error handler
    app.add_error_handler(error_handler)

    logger.info("🚀 DiBot CV FEE berjalan (OPTIMIZED VERSION)...")
    print("🚀 DiBot CV FEE berjalan (OPTIMIZED VERSION)...")
    print(f"📊 Max concurrent updates: 8")
    print(f"⏱️  Timeouts: pool=60s, read=60s, write=120s, connect=30s")
    print(f"🔐 Rate limit: Max {MAX_CONCURRENT_PER_USER} operations per user")

    # Auto-expire VIP members on startup
    expired_count = db.expire_vip_members()
    if expired_count:
        logger.info("%d VIP member expired direset saat startup", expired_count)

    # ── Scheduled jobs via PTB JobQueue ────────────────────────────────────────
    async def job_expire_vip(context):
        """Setiap 1 jam — expire VIP yang habis masa berlaku"""
        count = db.expire_vip_members()
        if count:
            logger.info("[JOB] %d VIP member expired", count)

    async def job_cleanup_sessions(context):
        """Setiap 30 menit — hapus direktori tmp sesi yang stuck > 4 jam"""
        import time
        from middleware.session import clear_user_dir
        tmp_base = os.path.join("tmp", "sessions")
        if not os.path.exists(tmp_base):
            return
        now   = time.time()
        limit = 4 * 3600
        cleaned = 0
        try:
            for uid_str in os.listdir(tmp_base):
                if not uid_str.isdigit():
                    continue
                path = os.path.join(tmp_base, uid_str)
                try:
                    if os.path.isdir(path) and (now - os.path.getmtime(path)) > limit:
                        sess = db.get_session(int(uid_str))
                        if not sess or sess.get("state") is None:
                            clear_user_dir(int(uid_str))
                            cleaned += 1
                except Exception:
                    pass
        except Exception:
            pass
        if cleaned:
            logger.info("[JOB] Cleaned %d stuck session dirs", cleaned)

    app.job_queue.run_repeating(job_expire_vip,    interval=3600, first=60)
    app.job_queue.run_repeating(job_cleanup_sessions, interval=1800, first=120)
    # ───────────────────────────────────────────────────────────────────────────

    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
