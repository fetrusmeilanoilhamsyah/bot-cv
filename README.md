# DiBot CV FEE — Panduan Instalasi & Penggunaan

## Persyaratan
- Python 3.11 atau lebih baru
- Koneksi internet untuk bot Telegram

---

## Langkah 1 — Konfigurasi Bot

1. Salin file `.env.example` menjadi `.env`:
   ```
   copy .env.example .env
   ```
2. Buka file `.env` dengan Notepad, isi data berikut:
   ```
   BOT_TOKEN=token_dari_botfather
   ADMIN_IDS=telegram_id_anda
   ADMIN_CONTACT=@username_telegram_anda
   GROUP_LINK=https://t.me/link_grup_anda
   HARGA_MEMBER=Rp 50.000 / bulan
   ```

> Cara dapat TOKEN: Chat @BotFather di Telegram, ketik /newbot, ikuti instruksi.
> Cara dapat Telegram ID Anda: Chat @userinfobot di Telegram.

---

## Langkah 2 — Install Library Python

Buka Command Prompt / Terminal di folder bot, jalankan:
```
pip install -r requirements.txt
```

---

## Langkah 3 — Jalankan Bot

```
python main.py
```

Bot aktif jika muncul log: `✅ Database connection pool initialized (10 connections)
✅ Database tables and indexes initialized
2026-02-18 18:51:14,751 - __main__ - INFO - 🚀 DiBot CV FEE berjalan (OPTIMIZED VERSION)...
🚀 DiBot CV FEE berjalan (OPTIMIZED VERSION)...
📊 Max concurrent updates: 8
⏱️  Timeouts: pool=60s, read=60s, write=120s, connect=30s
🔐 Rate limit: Max 2 operations per user`

> Database otomatis dibuat sebagai file `database/bot.db` saat pertama kali bot dijalankan. Tidak perlu setup apapun.

---

## Langkah 4 — Daftarkan Admin sebagai Member

Setelah bot berjalan, jalankan perintah ini sekali di terminal untuk mendaftarkan diri sebagai member:
```
python -c "from database import db; db.set_member(ID_TELEGRAM_ANDA, 'NAMA_ANDA'); print('done')"
```

---

## Daftar Perintah

| Perintah | Fungsi | Akses |
|---|---|---|
| /start | Sapa dan info member | Semua |
| /reset | Hapus sesi & bersihkan RAM | Member |
| /Admin | Buat VCF Admin + Navy | Member |
| /merge | Gabungkan file VCF | Member |
| /vcftotxt | Konversi VCF ke TXT | Member |
| /pecahvcf | Pecah VCF per N kontak | Member |
| /rename | Ganti nama file VCF | Member |
| /txttovcf | Konversi TXT ke VCF | Member |
| /Brodcast | Kirim pesan ke semua user | Admin |
| /newmember | Aktifkan member baru | Admin |
| /done | Selesaikan proses upload | Member |

---

## Catatan Penting

- Boleh kirim banyak file sekaligus (merge, vcftotxt, txttovcf), ketik `/done` setelah selesai
- Selalu ketik `/reset` setelah selesai konversi agar RAM tetap bersih
- Nomor telepon otomatis ditambahkan `+` di depan
- Jika bot error, cek file `logs/bot.log`
- Data user tersimpan di `database/bot.db`, bisa dibuka dengan DB Browser for SQLite

---

## LISENSI FETRUS MEILANO ILHAMSYAH
Dilarang menyebarkan atau menjual ulang tanpa izin.