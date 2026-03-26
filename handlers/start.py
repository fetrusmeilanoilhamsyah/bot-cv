from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from middleware.session import clear_user_dir
from handlers.cancel_helper import cancel_all
from config import ADMIN_CONTACT, TUTORIAL_LINK


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Cancel semua proses aktif user saat /start
    cancel_all(user.id)
    db.clear_session(user.id)
    clear_user_dir(user.id)

    # Daftarkan user ke database
    db.upsert_user(user.id, user.username or "", user.full_name or "")

    first_name = user.first_name or user.full_name or "Kawan"

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
        "/reset       - bersihkan sesi aktif\n"
        "/done        - selesaikan proses file\n"
        "─────────────────\n"
        " KHUSUS ADMIN FEE:\n"
        "/stat        - lihat statistik & status bot\n"
        "/daftar      - daftar pengguna bot\n"
        "/brodcast    - kirim pesan massal\n"
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
        f"Hallo <b>{first_name}</b>, selamat datang di bot\n"
        f"Fitur bot:\n"
        f"<pre>{fitur}</pre>\n"
        f"Bot milik <a href='{admin_url}'>{ADMIN_CONTACT}</a>",
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )