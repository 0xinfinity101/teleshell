# terminalhub

Telegram bot untuk menjalankan terminal lokal dari Telegram. Cocok untuk akses cepat ke mesin pribadi saat sedang jauh dari keyboard.

## Fitur

- Jalankan command terminal langsung dari chat Telegram.
- `cd` persistent per user, jadi working directory tetap tersimpan selama bot hidup.
- Output pendek dikirim sebagai pesan.
- Output panjang otomatis dikirim sebagai file.
- Jika command `cat nama-file` menghasilkan output panjang, file Telegram memakai nama file asli.
- Whitelist user ID.
- Timeout Telegram API bisa dikonfigurasi dari `.env`.

## Peringatan Keamanan

Bot ini memberi akses shell ke mesin tempat bot berjalan. Jalankan hanya untuk penggunaan pribadi, dengan token bot yang aman, user whitelist yang benar, dan idealnya pada user Linux/container dengan permission terbatas.

Jangan commit `.env`. File itu berisi token Telegram dan user ID privat.

## Instalasi

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Isi `.env`:

```env
BOT_TOKEN=token_dari_botfather
ALLOWED_USER_IDS=123456789
```

Cari user ID Telegram kamu dengan bot seperti `@userinfobot`.

## Konfigurasi

Contoh lengkap ada di `.env.example`.

```env
TELEGRAM_CONNECT_TIMEOUT=15
TELEGRAM_READ_TIMEOUT=30
TELEGRAM_WRITE_TIMEOUT=30
TELEGRAM_POOL_TIMEOUT=10
TELEGRAM_MEDIA_WRITE_TIMEOUT=120
TELEGRAM_GET_UPDATES_READ_TIMEOUT=60
POLLING_TIMEOUT=30
```

Naikkan timeout jika koneksi ke Telegram sering lambat atau upload output file sering timeout.

## Menjalankan Bot

```bash
source .venv/bin/activate
python telegram_terminal_bot.py
```

Di Telegram:

```bash
pwd
cd Documents/novel/naskah
ls
cat bab-01.md
```

Jika `cat bab-01.md` terlalu panjang untuk dikirim sebagai pesan, bot akan mengirim dokumen bernama `bab-01.md`.

## Test

```bash
source .venv/bin/activate
python -m unittest test_telegram_terminal_bot.py
```

## Catatan

- `ALLOWED_USER_IDS` adalah whitelist berdasarkan user ID Telegram, bukan chat ID grup.
- `ALLOWED_CHAT_IDS` masih dibaca sebagai nama lama untuk kompatibilitas.
- Command shell tetap dieksekusi dengan `shell=True`, jadi perlakukan bot ini seperti akses terminal penuh.
