import os
import shutil
import sqlite3

def clean_all():
    print("🧹 Memulai pembersihan data dummy...")

    # 1. Hapus database bot.db (akan dibuat otomatis saat start)
    db_path = os.path.join("database", "bot.db")
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print("✅ Database (bot.db) berhasil dihapus.")
        except Exception as e:
            print(f"❌ Gagal menghapus database: {e}")
    else:
        print("✅ Database sudah bersih.")

    # 2. Hapus isi folder tmp/sessions
    tmp_path = os.path.join("tmp", "sessions")
    if os.path.exists(tmp_path):
        try:
            shutil.rmtree(tmp_path)
            os.makedirs(tmp_path, exist_ok=True)
            print("✅ Folder tmp/sessions berhasil dibersihkan.")
        except Exception as e:
            print(f"❌ Gagal membersihkan tmp/sessions: {e}")
    else:
        print("✅ Folder tmp/sessions sudah bersih.")

    # 3. Hapus logs
    log_path = os.path.join("logs", "bot.log")
    if os.path.exists(log_path):
        try:
            os.remove(log_path)
            print("✅ File logs/bot.log berhasil dihapus.")
        except Exception as e:
            print(f"❌ Gagal menghapus logs: {e}")
    else:
        print("✅ Logs sudah bersih.")

    print("\n✨ Pembersihan selesai! Bot siap untuk dipush ke production.")

if __name__ == "__main__":
    clean_all()
