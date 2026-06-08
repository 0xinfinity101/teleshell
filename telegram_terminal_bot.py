"""
Telegram Terminal Bot
=====================
Jalankan perintah terminal langsung dari Telegram.
- Tanpa prefix, ketik langsung: ls, cd /home, pwd, dll
- cd persistent per session
- Output panjang otomatis dikirim sebagai file
- Whitelist user ID untuk keamanan

Instalasi:
    pip install python-telegram-bot python-dotenv

Buat file .env di folder yang sama:
    BOT_TOKEN=isi_token_kamu
    ALLOWED_USER_IDS=123456789,987654321

Jalankan:
    python telegram_terminal_bot.py
"""

import os
import asyncio
import logging
import shlex
import subprocess
import tempfile
from dotenv import load_dotenv
from telegram import Update
from telegram.error import TimedOut, NetworkError
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

load_dotenv()

# ─────────────────────────────────────────────
# KONFIGURASI — dari .env
# ─────────────────────────────────────────────

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def parse_id_set(raw_ids: str) -> set[int]:
    return {int(uid.strip()) for uid in raw_ids.split(",") if uid.strip().isdigit()}


def get_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Nilai %s=%r tidak valid, memakai default %s", name, raw, default)
        return default


# ALLOWED_USER_IDS di .env diisi dipisah koma: 123456789,987654321.
# ALLOWED_CHAT_IDS tetap dibaca sebagai nama lama agar konfigurasi lama tidak rusak.
_raw_user_ids = os.getenv("ALLOWED_USER_IDS") or os.getenv("ALLOWED_CHAT_IDS", "")
ALLOWED_USER_IDS = parse_id_set(_raw_user_ids)

# Batas karakter sebelum output dikirim sebagai file
MAX_OUTPUT_CHARS = 3500

# Timeout eksekusi perintah (detik)
COMMAND_TIMEOUT = 30

# Timeout request Telegram API. Default bawaan library 5 detik sering terlalu sempit
# untuk jaringan lambat, long polling, atau upload output file.
TELEGRAM_CONNECT_TIMEOUT = get_float_env("TELEGRAM_CONNECT_TIMEOUT", 15.0)
TELEGRAM_READ_TIMEOUT = get_float_env("TELEGRAM_READ_TIMEOUT", 30.0)
TELEGRAM_WRITE_TIMEOUT = get_float_env("TELEGRAM_WRITE_TIMEOUT", 30.0)
TELEGRAM_POOL_TIMEOUT = get_float_env("TELEGRAM_POOL_TIMEOUT", 10.0)
TELEGRAM_MEDIA_WRITE_TIMEOUT = get_float_env("TELEGRAM_MEDIA_WRITE_TIMEOUT", 120.0)
TELEGRAM_GET_UPDATES_READ_TIMEOUT = get_float_env("TELEGRAM_GET_UPDATES_READ_TIMEOUT", 60.0)
POLLING_TIMEOUT = get_float_env("POLLING_TIMEOUT", 30.0)

# Perintah yang diblokir (opsional, hapus jika tidak perlu)
BLOCKED_COMMANDS = {
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    ":(){:|:&};:",  # fork bomb
}

MARKDOWN_V2_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!"

# ─────────────────────────────────────────────
# STATE — Menyimpan working directory per user
# ─────────────────────────────────────────────

user_cwd: dict[int, str] = {}

def get_cwd(user_id: int) -> str:
    return user_cwd.get(user_id, os.path.expanduser("~"))

def set_cwd(user_id: int, path: str):
    user_cwd[user_id] = path

# ─────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────

def is_allowed(update: Update) -> bool:
    return update.effective_user.id in ALLOWED_USER_IDS

def is_blocked(command: str) -> bool:
    cmd_lower = command.strip().lower()
    return any(blocked in cmd_lower for blocked in BLOCKED_COMMANDS)

def resolve_cd_target(cwd: str, target: str) -> str:
    target = os.path.expandvars(os.path.expanduser(target))
    if not os.path.isabs(target):
        target = os.path.join(cwd, target)
    return os.path.normpath(target)

def escape_markdown_v2(text: str) -> str:
    return "".join(
        f"\\{char}" if char in MARKDOWN_V2_SPECIAL_CHARS else char
        for char in text
    )

def run_shell_command(command: str, cwd: str) -> str:
    result = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=COMMAND_TIMEOUT,
    )
    output = result.stdout
    if result.stderr:
        output += result.stderr
    return output.rstrip()

def document_filename_for_command(command: str, cwd: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError:
        return "output.txt"

    if len(parts) != 2 or parts[0] != "cat":
        return "output.txt"

    target = resolve_cd_target(cwd, parts[1])
    if os.path.isfile(target):
        return os.path.basename(target)
    return "output.txt"

async def send_output(update: Update, text: str, cwd: str, document_filename: str = "output.txt"):
    """Kirim output. Jika terlalu panjang, kirim sebagai file .txt"""
    header = f"`{escape_markdown_v2(cwd)}` ↵\n"

    if len(text) == 0:
        await update.message.reply_text(header + "_\\(no output\\)_", parse_mode="MarkdownV2")
        return

    if len(text) <= MAX_OUTPUT_CHARS:
        full = header + f"```\n{escape_markdown_v2(text)}\n```"
        await update.message.reply_text(full, parse_mode="MarkdownV2")
    else:
        # Output terlalu panjang → kirim sebagai file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="terminal_output_"
        ) as f:
            f.write(text)
            tmp_path = f.name

        await update.message.reply_text(
            header + (
                f"_\\(output terlalu panjang, {len(text)} karakter, "
                "dikirim sebagai file\\)_"
            ),
            parse_mode="MarkdownV2"
        )
        try:
            with open(tmp_path, "rb") as f:
                await update.message.reply_document(document=f, filename=document_filename)
        finally:
            os.unlink(tmp_path)

# ─────────────────────────────────────────────
# HANDLER UTAMA — Eksekusi perintah
# ─────────────────────────────────────────────

async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("⛔ Akses ditolak.")
        return

    raw = update.message.text.strip()
    if not raw:
        return

    # Cek blacklist
    if is_blocked(raw):
        await update.message.reply_text("⛔ Perintah diblokir.")
        return

    user_id = update.effective_user.id
    cwd = get_cwd(user_id)

    # Handle perintah cd secara khusus
    # Karena subprocess tidak bisa mengubah cwd parent process
    if raw == "cd" or raw.startswith("cd ") or raw.startswith("cd\t"):
        parts = raw.split(maxsplit=1)
        target = parts[1] if len(parts) > 1 else os.path.expanduser("~")

        target = resolve_cd_target(cwd, target)

        if os.path.isdir(target):
            set_cwd(user_id, target)
            await update.message.reply_text(
                f"`{escape_markdown_v2(target)}`",
                parse_mode="MarkdownV2",
            )
        else:
            await update.message.reply_text(
                f"```\n{escape_markdown_v2(f'cd: {target}: No such file or directory')}\n```",
                parse_mode="MarkdownV2",
            )
        return

    # Jalankan perintah lain
    try:
        output = await asyncio.to_thread(run_shell_command, raw, cwd)
    except subprocess.TimeoutExpired:
        output = f"⏱ Timeout setelah {COMMAND_TIMEOUT} detik."
    except Exception as e:
        output = f"Error: {e}"

    try:
        await send_output(
            update,
            output,
            cwd,
            document_filename=document_filename_for_command(raw, cwd),
        )
    except TimedOut:
        logger.exception("Timeout saat mengirim output ke Telegram")

# ─────────────────────────────────────────────
# COMMAND /start dan /pwd
# ─────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    user_id = update.effective_user.id
    cwd = get_cwd(user_id)
    await update.message.reply_text(
        f"Terminal Bot aktif\n\n"
        f"Ketik perintah langsung, tidak perlu prefix /.\n"
        f"Working dir sekarang: {cwd}\n\n"
        f"Contoh: ls -la, pwd, cd /tmp, cat /etc/hostname"
    )

async def cmd_pwd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    cwd = get_cwd(update.effective_user.id)
    await update.message.reply_text(
        f"`{escape_markdown_v2(cwd)}`",
        parse_mode="MarkdownV2",
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, TimedOut):
        logger.warning("Request Telegram timeout: %s", context.error)
        return
    if isinstance(context.error, NetworkError):
        logger.warning("Network error Telegram: %s", context.error)
        return
    logger.exception("Error tidak terduga dari bot", exc_info=context.error)

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN tidak ditemukan di .env!")
        return
    if not ALLOWED_USER_IDS:
        print("❌ ALLOWED_USER_IDS tidak ditemukan atau kosong di .env!")
        return

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
        .read_timeout(TELEGRAM_READ_TIMEOUT)
        .write_timeout(TELEGRAM_WRITE_TIMEOUT)
        .pool_timeout(TELEGRAM_POOL_TIMEOUT)
        .media_write_timeout(TELEGRAM_MEDIA_WRITE_TIMEOUT)
        .get_updates_connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
        .get_updates_read_timeout(TELEGRAM_GET_UPDATES_READ_TIMEOUT)
        .get_updates_write_timeout(TELEGRAM_WRITE_TIMEOUT)
        .get_updates_pool_timeout(TELEGRAM_POOL_TIMEOUT)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("pwd", cmd_pwd))
    # Semua pesan teks biasa → eksekusi sebagai perintah
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_command))
    app.add_error_handler(error_handler)

    print("🤖 Bot berjalan... (Ctrl+C untuk stop)")
    app.run_polling(timeout=POLLING_TIMEOUT, bootstrap_retries=-1)

if __name__ == "__main__":
    main()
