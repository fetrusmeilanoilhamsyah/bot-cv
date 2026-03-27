from database import db

def cleanup():
    with db.get_connection() as conn:
        # Cari user yang full_name-nya 'Promo 7 Hari' dan username-nya kosong 
        # (artinya mereka belum pernah interaksi sama sekali sama bot)
        res = conn.execute("SELECT id FROM users WHERE full_name = 'Promo 7 Hari' AND (username = '' OR username IS NULL)")
        to_delete = [row['id'] for row in res]
        
        if not to_delete:
            print("Tidak ada user ghaib yang perlu dihapus.")
            return

        print(f"Menghapus {len(to_delete)} user ghaib...")
        for uid in to_delete:
            conn.execute("DELETE FROM users WHERE id = ?", (uid,))
        conn.commit()
        print("Selesai. Database bersih!")

if __name__ == "__main__":
    cleanup()
