"""
vip.py — Tampilkan harga paket VIP dan arahkan user ke admin.
Pembayaran manual (QRIS pending approval Midtrans).
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from datetime import datetime
from config import ADMIN_CONTACT


PAKET = [
    {"label": "1 Minggu",  "days": 7,  "harga": "Rp 5.000"},
    {"label": "2 Minggu",  "days": 14, "harga": "Rp 10.000"},
    {"label": "3 Minggu",  "days": 21, "harga": "Rp 15.000"},
    {"label": "1 Bulan",   "days": 30, "harga": "Rp 20.000"},
]


async def cmd_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    expired_at  = db.get_vip_expiry(user.id)
    status_line = ""
    if db.is_member(user.id):
        if expired_at:
            exp  = datetime.fromisoformat(expired_at)
            sisa = (exp - datetime.now()).days
            status_line = (
                f"\nStatus: VIP Aktif\n"
                f"Berakhir: <b>{exp.strftime('%d %b %Y')}</b> (sisa {sisa} hari)\n"
            )
        else:
            status_line = "\nStatus: Member Permanen\n"

    lines = []
    for p in PAKET:
        lines.append(f"{'─'*26}\n<b>{p['label']}</b>   {p['harga']}")

    keyboard = [[InlineKeyboardButton("Daftar VIP", url=f"https://t.me/{ADMIN_CONTACT.lstrip('@')}")]]

    await update.message.reply_text(
        f"<b>PAKET VIP DIBOT</b>\n"
        f"{status_line}\n"
        + "\n".join(lines) +
        f"\n{'─'*26}\n\n"
        f"Cara daftar:\n"
        f"1. Hubungi {ADMIN_CONTACT}\n"
        f"2. Pilih paket & konfirmasi\n"
        f"3. Transfer sesuai nominal\n"
        f"4. Kirim bukti transfer\n"
        f"5. Akses langsung aktif\n\n"
        f"<i>Pembayaran manual (QRIS segera tersedia)</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True
    )
