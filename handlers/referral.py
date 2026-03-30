"""
handlers/referral.py — Referral system logic.
"""
from telegram import Update
from telegram.ext import ContextTypes
from database import db

async def cmd_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot_username = context.bot.username or "Bot"
    
    # Hitung jumlah referral
    count = db.get_referral_count(user.id)
    
    bonus_target = 5
    remains = bonus_target - (count % bonus_target)
    if remains == 0: remains = bonus_target
    
    link = f"https://t.me/{bot_username}?start=ref_{user.id}"
    
    text = (
        f"<b>PROGRAM REFERRAL</b> 🎁\n\n"
        f"Dapatkan <b>7 HARI VIP GRATIS</b> setiap kali kamu berhasil mengundang 5 teman baru!\n\n"
        f"🔗 <b>Link Referral Kamu:</b>\n"
        f"<code>{link}</code>\n"
        f"<i>(Klik link di atas untuk menyalin)</i>\n\n"
        f"📊 <b>Statistik Kamu:</b>\n"
        f"• Teman diundang: {count} orang\n"
        f"• Kurang {remains} orang lagi untuk dapat Bonus 7 Hari VIP!"
    )
    
    await update.message.reply_text(text, parse_mode="HTML")
