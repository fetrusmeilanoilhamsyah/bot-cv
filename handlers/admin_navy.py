"""
admin_navy.py — In-memory approach, tidak ada disk sama sekali.
"""
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middleware.auth import require_member
from core.vcf_parser import add_plus, contacts_to_vcf

STATES = {
    "WAIT_ADMIN_NUMBERS": "AN_STEP1",
    "WAIT_NAVY_NUMBERS":  "AN_STEP2",
    "WAIT_ADMIN_NAME":    "AN_STEP3",
    "WAIT_NAVY_NAME":     "AN_STEP4",
    "WAIT_FILE_NAME":     "AN_STEP5",
}


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_member(update, context):
        return
    user_id = update.effective_user.id
    db.set_session(user_id, STATES["WAIT_ADMIN_NUMBERS"], {})
    await update.message.reply_text(
        "Berikan nomor ADMIN.\n"
        "Format: satu nomor per baris, contoh:\n"
        "628123456789\n"
        "628987654321"
    )


async def handle_admin_navy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sess = db.get_session(user_id)
    state = sess["state"]
    data = sess["data"]
    text = update.message.text.strip()

    if state == STATES["WAIT_ADMIN_NUMBERS"]:
        numbers = [n.strip() for n in text.splitlines() if n.strip()]
        data["admin_numbers"] = numbers
        db.set_session(user_id, STATES["WAIT_NAVY_NUMBERS"], data)
        await update.message.reply_text(
            "Berikan nomor NAVY.\nFormat: satu nomor per baris."
        )

    elif state == STATES["WAIT_NAVY_NUMBERS"]:
        numbers = [n.strip() for n in text.splitlines() if n.strip()]
        data["navy_numbers"] = numbers
        db.set_session(user_id, STATES["WAIT_ADMIN_NAME"], data)
        await update.message.reply_text(
            "Masukkan nama ADMIN (label kontak untuk nomor ADMIN):"
        )

    elif state == STATES["WAIT_ADMIN_NAME"]:
        data["admin_name"] = text
        db.set_session(user_id, STATES["WAIT_NAVY_NAME"], data)
        await update.message.reply_text(
            "Masukkan nama NAVY (label kontak untuk nomor NAVY):"
        )

    elif state == STATES["WAIT_NAVY_NAME"]:
        data["navy_name"] = text
        db.set_session(user_id, STATES["WAIT_FILE_NAME"], data)
        await update.message.reply_text("Masukkan nama file output:")

    elif state == STATES["WAIT_FILE_NAME"]:
        data["file_name"] = text

        # Build VCF di RAM langsung, tidak perlu disk sama sekali
        contacts = []
        admin_nums = data["admin_numbers"]
        navy_nums = data["navy_numbers"]
        admin_name = data["admin_name"]
        navy_name = data["navy_name"]

        for i, num in enumerate(admin_nums, start=1):
            contacts.append({
                "name": f"{admin_name}{i}" if len(admin_nums) > 1 else admin_name,
                "tel": add_plus(num.strip())
            })

        for i, num in enumerate(navy_nums, start=1):
            contacts.append({
                "name": f"{navy_name}{i}" if len(navy_nums) > 1 else navy_name,
                "tel": add_plus(num.strip())
            })

        vcf_bytes = contacts_to_vcf(contacts).encode("utf-8")
        db.clear_session(user_id)

        await update.message.reply_document(
            document=vcf_bytes,
            filename=f"{data['file_name']}.vcf"
        )