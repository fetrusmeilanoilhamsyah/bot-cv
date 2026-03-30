import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from database import db
from middleware.session import clear_user_dir
from handlers.cancel_helper import cancel_all
from config import ADMIN_CONTACT, TUTORIAL_LINK


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Cek apakah user baru (untuk referral)
    is_new_user = db.get_user(user.id) is None

    # Daftarkan user ke database
    db.upsert_user(user.id, user.username or "", user.full_name)
    db.increment_usage(user.id)

    # Cek referral: /start ref_ID
    if is_new_user and context.args and len(context.args) > 0:
        arg = context.args[0]
        if arg.startswith("ref_"):
            try:
                referrer_id = int(arg.replace("ref_", ""))
                if referrer_id != user.id:
                    db.set_referrer(user.id, referrer_id)
                    count = db.get_referral_count(referrer_id)
                    
                    # Notifikasi ke pengundang
                    try:
                        bonus_target = 5
                        remains = bonus_target - (count % bonus_target)
                        if remains == 0: remains = bonus_target # Jika pas kelipatan 5
                        
                        # Jika pas kelipatan 5, beri hadiah
                        if count > 0 and count % bonus_target == 0:
                            db.set_member_vip(referrer_id, 7, "Referral Bonus")
                            await context.bot.send_message(
                                chat_id=referrer_id,
                                text=f"🎁 <b>BONUS REFERRAL!</b>\n\nTeman ke-{count} baru saja bergabung. Kamu mendapatkan <b>7 HARI VIP GRATIS!</b>",
                                parse_mode="HTML"
                            )
                        else:
                            await context.bot.send_message(
                                chat_id=referrer_id,
                                text=f"👤 <b>Teman baru bergabung!</b>\n\nSatu orang lagi menggunakan link kamu. (Total: {count} orang)\nUndang {count + remains - count} orang lagi untuk dapat 7 hari VIP GRATIS!",
                                parse_mode="HTML"
                            )
                    except Exception:
                        pass
            except ValueError:
                pass

    first_name = user.first_name or user.full_name or "Kawan"
    bot_username = context.bot.username or "Bot"
    
    # 1. KIRIM REPLY SEGERA (INSTANT RESPONSE)
    greeting = f"<b>Halo {first_name}! Selamat datang di bot.</b>"
    fitur = (
        "<b>/txttovcf    - konversi file TXT ke VCF</b>\n"
        "<b>/vcftotxt    - konversi file VCF ke TXT</b>\n"
        "<b>/xlsxtotxt   - ekstrak kontak dari Excel/CSV</b>\n"
        "<b>/admin       - buat file admin/navy VCF</b>\n"
        "<b>/merge       - gabungkan file VCF</b>\n"
        "<b>/pecahvcf    - pecah file VCF</b>\n"
        "<b>/rename      - ganti nama file VCF</b>\n"
        "<b>/count       - hitung jumlah kontak</b>\n"
        "<b>/vip         - lihat & daftar paket VIP</b>\n"
        "<b>/referal     - undang teman (Dapatkan VIP Gratis)</b>\n"
        "<b>/reset       - bersihkan sesi aktif</b>\n"
        "<b>/done        - selesaikan proses file</b>\n"
        "<b>─────────────────</b>\n"
        "<b>KHUSUS ADMIN FEE:</b>\n"
        "<b>/stat        - lihat statistik & status bot</b>\n"
        "<b>/daftar      - daftar pengguna bot</b>\n"
        "<b>/brodcast    - kirim pesan massal (Teks)</b>\n"
        "<b>/mediabroadcast - kirim pesan massal (Media/Foto/Video)</b>\n"
        "<b>/addvip      - tambah member VIP</b>\n"
        "<b>/delvip      - copot member VIP</b>\n"
        "<b>/newmember   - buat member permanen</b>\n"
        "<b>/delmember   - hapus member permanen</b>\n"
        "<b>/resetdatabase - bersihkan cache server</b>"
    )

    # 2. MENU BUTTONS (REPLY KEYBOARD)
    keyboard_buttons = [
        [KeyboardButton("/txttovcf"), KeyboardButton("/vcftotxt"), KeyboardButton("/xlsxtotxt")],
        [KeyboardButton("/admin"), KeyboardButton("/merge"), KeyboardButton("/pecahvcf")],
        [KeyboardButton("/rename"), KeyboardButton("/count"), KeyboardButton("/vip")],
        [KeyboardButton("/referal"), KeyboardButton("/reset"), KeyboardButton("/done")],
        [KeyboardButton("/start")]
    ]
    reply_keyboard = ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True)

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Tutorial Penggunaan Bot", url=TUTORIAL_LINK)
    ]])
    admin_url = f"https://t.me/{ADMIN_CONTACT.lstrip('@')}"

    await update.message.reply_text(
        f"{greeting}\n\n"
        f"<b>Fitur Bot:</b>\n"
        f"{fitur}\n\n"
        f"<b>Owner: {ADMIN_CONTACT}</b>",
        parse_mode="HTML",
        reply_markup=reply_keyboard,
        disable_web_page_preview=True
    )

    # Tambahkan inline keyboard secara terpisah jika perlu link tutorial
    await update.message.reply_text(
        "<b>Pencet tombol di bawah untuk tutorial:</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )

    # 2. KERJAKAN CLEANUP DI BACKGROUND (TIDAK BLOKIR REPLY)
    async def cleanup_bg():
        cancel_all(user.id)
        db.clear_session(user.id)
        clear_user_dir(user.id)
    
    asyncio.create_task(cleanup_bg())