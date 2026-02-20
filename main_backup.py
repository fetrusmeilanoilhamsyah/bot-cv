"""
main.py
Entry point DiBot CV FEE.
Jalankan: python main.py
"""
import logging
import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
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

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.WARNING,
    handlers=[
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


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
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)   # ← True: terima semua file paralel = cepat
        .connection_pool_size(32)
        .pool_timeout(30)
        .read_timeout(30)
        .write_timeout(60)
        .connect_timeout(15)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("Admin", cmd_admin))
    app.add_handler(CommandHandler("merge", cmd_merge))
    app.add_handler(CommandHandler("vcftotxt", cmd_vcftotxt))
    app.add_handler(CommandHandler("pecahvcf", cmd_pecahvcf))
    app.add_handler(CommandHandler("rename", cmd_rename))
    app.add_handler(CommandHandler("txttovcf", cmd_txttovcf))
    app.add_handler(CommandHandler("Brodcast", cmd_broadcast))
    app.add_handler(CommandHandler("newmember", cmd_newmember))
    app.add_handler(CommandHandler("done", done_router))

    app.add_handler(MessageHandler(filters.Document.ALL, file_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    app.add_error_handler(error_handler)

    logger.info("DiBot CV FEE berjalan...")
    print("DiBot CV FEE berjalan...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()