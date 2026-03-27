"""
bulk_promo.py
Script untuk memberikan akses VIP 7 hari secara massal ke list ID Telegram.
"""
import asyncio
import sys
from telegram import Bot
from database import db
from config import BOT_TOKEN

# DAFTAR ID TELEGRAM (Masukkan 100 ID di bawah)
# Contoh: [123456789, 987654321]
TARGET_IDS = [
    1341856464, 7162615240, 6408964864, 6431576847, 6987835519, 
    7101422159, 6733514838, 8303743384, 6592082791, 5416016802, 
    7700468057, 6185512907, 8553192960, 7924749009, 7182212716, 
    7900547707, 7012964148, 6625956535, 6768072131, 7766424896, 
    8407351171, 7716879245, 8565801604, 7291247590, 7780751596, 
    6109358186, 7102510018, 6716998616, 7599931728, 6600334449, 
    5390892910, 7328838004, 6297489400, 7793690375, 8323971224, 
    7133079102, 1478279447, 5830703426, 8134802762, 6613321702, 
    7115542187, 1454156587, 7610161541, 5168536344, 7606803587, 
    5753989688, 8219682560, 8432090039, 8440040644, 6877210361, 
    8094118792, 5673596898, 7540448930, 6674775708, 7176162127, 
    6481340989, 7357276101, 7769438494, 1651841826, 6404822546, 
    8081336148, 7970682263, 7055816098, 8522744747, 7365698665, 
    8355520677, 6007791995, 6631657053, 554203544, 7510856955, 
    6958966841, 8381479401, 6988362899, 8079163752, 7716002752, 
    6472638686, 6421999861, 7679899409, 7628601252, 8202649559, 
    7213403309, 7454794904, 7085902120, 8398426621, 6391729464, 
    7420100754, 6429796570, 6639312549, 7373792830, 7590506777, 
    7558235394, 7540579825, 7242831002, 6545413282, 7976462201, 
    6602236855, 1348458557, 7529812276, 7453904614, 7962905495
]

async def run_promo():
    if not TARGET_IDS:
        print("Error: List TARGET_IDS masih kosong.")
        return

    bot = Bot(token=BOT_TOKEN)
    print(f"Memproses {len(TARGET_IDS)} user...")
    
    count = 0
    fail = 0
    
    for uid in TARGET_IDS:
        try:
            # Update database (7 hari)
            db.set_member_vip(uid, days=7, full_name="Promo 7 Hari")
            
            # Pesan profesional (Singkat & To the point)
            msg = (
                "Akses VIP 7 Hari Aktif.\n\n"
                "Fitur premium sudah bisa digunakan.\n"
                "Cek status: /start"
            )
            
            await bot.send_message(chat_id=uid, text=msg)
            print(f"ID {uid}: Berhasil")
            count += 1
            
            # Delay anti-flood
            await asyncio.sleep(0.05)
            
        except Exception as e:
            err_msg = str(e)
            if "bot can't initiate conversation" in err_msg:
                print(f"ID {uid}: Gagal (User belum pernah /start bot)")
            elif "Forbidden: bot was blocked by the user" in err_msg:
                print(f"ID {uid}: Gagal (User memblokir bot)")
            else:
                print(f"ID {uid}: Gagal ({err_msg})")
            fail += 1

    print(f"\nSelesai.\nBerhasil: {count}\nGagal: {fail}")

if __name__ == "__main__":
    try:
        asyncio.run(run_promo())
    except KeyboardInterrupt:
        print("\nDibatalkan oleh user.")
        sys.exit(0)
