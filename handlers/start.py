import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    greeting = f"Halo {first_name}!"
    fitur = (
        "/txttovcf    - konversi file TXT ke VCF\n"
        "/vcftotxt    - konversi file VCF ke TXT\n"
        "/xlsxtotxt   - ekstrak kontak dari Excel/CSV\n"
        "/admin       - buat file admin/navy VCF\n"
        "/merge       - gabungkan file VCF\n"
        "/pecahvcf    - pecah file VCF\n"
        "/rename      - ganti nama file VCF\n"
        "/count       - hitung jumlah kontak\n"
        "/vip         - lihat & daftar paket VIP\n"
        "/referal     - undang teman (Dapatkan VIP Gratis)\n"
        "/reset       - bersihkan sesi aktif\n"
        "/done        - selesaikan proses file\n"
        "─────────────────\n"
        " KHUSUS ADMIN FEE:\n"
        "/stat        - lihat statistik & status bot\n"
        "/daftar      - daftar pengguna bot\n"
        "/brodcast    - kirim pesan massal (Teks)\n"
        "/mediabroadcast - kirim pesan massal (Media/Foto/Video)\n"
        "/addvip      - tambah member VIP\n"
        "/delvip      - copot member VIP\n"
        "/newmember   - buat member permanen\n"
        "/delmember   - hapus member permanen\n"
        "/resetdatabase - bersihkan cache server"
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Tutorial Penggunaan Bot", url=TUTORIAL_LINK)
    ]])
    admin_url = f"https://t.me/{ADMIN_CONTACT.lstrip('@')}"

    await update.message.reply_text(
        f"<b>{first_name}</b>\n\n"
        f"{greeting}\n\n"
        f"Fitur:\n"
        f"<pre>{fitur}</pre>\n"
        f"Owner: <a href='{admin_url}'>{ADMIN_CONTACT}</a>",
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

    # 2. KERJAKAN CLEANUP DI BACKGROUND (TIDAK BLOKIR REPLY)
    async def cleanup_bg():
        cancel_all(user.id)
        db.clear_session(user.id)
        clear_user_dir(user.id)
    
    asyncio.create_task(cleanup_bg())