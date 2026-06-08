"""
teleshell
==========
Run terminal commands directly from Telegram.
- No prefix required; type commands directly: ls, cd /home, pwd, etc.
- cd persistent per session
- Long output is automatically sent as a file
- User ID whitelist for access control

Installation:
    pip install python-telegram-bot python-dotenv

Create a .env file in the same directory:
    BOT_TOKEN=your_token_here
    ALLOWED_USER_IDS=123456789,987654321

Run:
    python teleshell.py
"""

import asyncio
import logging
import os
import shlex
import subprocess
import tempfile
from dotenv import load_dotenv
from telegram import Update
from telegram.error import TimedOut, NetworkError
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from claude_bridge import ClaudeBridgeManager
from interactive_controls import (
    CALLBACK_CTRL_C,
    CALLBACK_DOWN,
    CALLBACK_EXIT,
    CALLBACK_PREFIX,
    CALLBACK_UP,
    callback_input,
    interactive_keyboard,
)
from interactive_sessions import InteractiveSessionManager, parse_command_set
from terminal_panel import TerminalPanel

load_dotenv()

# ─────────────────────────────────────────────
# CONFIGURATION - from .env
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
        logger.warning("Invalid %s=%r value, using default %s", name, raw, default)
        return default


def get_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off", ""}:
        return False
    logger.warning("Invalid %s=%r value, using default %s", name, raw, default)
    return default


# ALLOWED_USER_IDS is comma-separated in .env: 123456789,987654321.
# ALLOWED_CHAT_IDS is still read as the legacy name for compatibility.
_raw_user_ids = os.getenv("ALLOWED_USER_IDS") or os.getenv("ALLOWED_CHAT_IDS", "")
ALLOWED_USER_IDS = parse_id_set(_raw_user_ids)

# Character limit before output is sent as a file
MAX_OUTPUT_CHARS = 3500

# Command execution timeout in seconds
COMMAND_TIMEOUT = 30

# Telegram API request timeouts. The library default of 5 seconds is often too
# short for slow networks, long polling, or output file uploads.
TELEGRAM_CONNECT_TIMEOUT = get_float_env("TELEGRAM_CONNECT_TIMEOUT", 15.0)
TELEGRAM_READ_TIMEOUT = get_float_env("TELEGRAM_READ_TIMEOUT", 30.0)
TELEGRAM_WRITE_TIMEOUT = get_float_env("TELEGRAM_WRITE_TIMEOUT", 30.0)
TELEGRAM_POOL_TIMEOUT = get_float_env("TELEGRAM_POOL_TIMEOUT", 10.0)
TELEGRAM_MEDIA_WRITE_TIMEOUT = get_float_env("TELEGRAM_MEDIA_WRITE_TIMEOUT", 120.0)
TELEGRAM_GET_UPDATES_READ_TIMEOUT = get_float_env("TELEGRAM_GET_UPDATES_READ_TIMEOUT", 60.0)
POLLING_TIMEOUT = get_float_env("POLLING_TIMEOUT", 30.0)
SAFE_MODE = get_bool_env("SAFE_MODE", True)
CLAUDE_BRIDGE_COMMAND = os.getenv("CLAUDE_BRIDGE_COMMAND", "claude")
CLAUDE_BRIDGE_ARGS = os.getenv(
    "CLAUDE_BRIDGE_ARGS",
    "--print --permission-mode acceptEdits",
)
CLAUDE_BRIDGE_TIMEOUT = get_float_env("CLAUDE_BRIDGE_TIMEOUT", 300.0)
INTERACTIVE_COMMANDS = parse_command_set(
    os.getenv("INTERACTIVE_COMMANDS", "python,python3,node,ssh,mysql,psql")
)

# Blocked commands. Adjust this list for your own risk tolerance.
BLOCKED_COMMANDS = {
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    ":(){:|:&};:",  # fork bomb
}

MARKDOWN_V2_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!"

# ─────────────────────────────────────────────
# STATE - Stores each user's working directory
# ─────────────────────────────────────────────

user_cwd: dict[int, str] = {}
claude_bridge = ClaudeBridgeManager(
    command=CLAUDE_BRIDGE_COMMAND,
    args=CLAUDE_BRIDGE_ARGS,
    timeout=CLAUDE_BRIDGE_TIMEOUT,
)
interactive_sessions = InteractiveSessionManager(INTERACTIVE_COMMANDS)
interactive_panels: dict[int, TerminalPanel] = {}
interactive_panel_messages: dict[int, object] = {}
command_locks: dict[int, asyncio.Lock] = {}

def get_cwd(user_id: int) -> str:
    return user_cwd.get(user_id, os.path.expanduser("~"))

def set_cwd(user_id: int, path: str):
    user_cwd[user_id] = path

def get_command_lock(user_id: int) -> asyncio.Lock:
    lock = command_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        command_locks[user_id] = lock
    return lock

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

async def run_shell_command_for_user(user_id: int, command: str, cwd: str) -> str:
    lock = get_command_lock(user_id)
    if lock.locked():
        return "Another command is still running. Wait for it to finish, or use /ctrlc for interactive sessions."
    async with lock:
        return await asyncio.to_thread(run_shell_command, command, cwd)

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
    """Send output. If it is too long, send it as a .txt file."""
    header = f"`{escape_markdown_v2(cwd)}` ↵\n"

    if len(text) == 0:
        await update.message.reply_text(header + "_\\(no output\\)_", parse_mode="MarkdownV2")
        return

    if len(text) <= MAX_OUTPUT_CHARS:
        full = header + f"```\n{escape_markdown_v2(text)}\n```"
        await update.message.reply_text(full, parse_mode="MarkdownV2")
    else:
        # Output is too long, so send it as a file.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="teleshell_output_"
        ) as f:
            f.write(text)
            tmp_path = f.name

        await update.message.reply_text(
            header + (
                f"_\\(output too long, {len(text)} characters, "
                "sent as a file\\)_"
            ),
            parse_mode="MarkdownV2"
        )
        try:
            with open(tmp_path, "rb") as f:
                await update.message.reply_document(document=f, filename=document_filename)
        finally:
            os.unlink(tmp_path)

# ─────────────────────────────────────────────
# MAIN HANDLER - Command execution
# ─────────────────────────────────────────────

async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("Access denied.")
        return

    raw = update.message.text.strip()
    if not raw:
        return

    # Check the blocklist.
    if is_blocked(raw):
        await update.message.reply_text("Command blocked.")
        return

    user_id = update.effective_user.id
    cwd = get_cwd(user_id)

    if claude_bridge.has_session(user_id):
        output = await claude_bridge.send_prompt(user_id, raw)
        await send_output(update, output, cwd)
        return

    if interactive_sessions.has_session(user_id):
        await interactive_sessions.send_input(user_id, raw)
        return

    if raw.startswith("/"):
        await update.message.reply_text("Unknown command. Use /pty <command> to start a session.")
        return

    # Handle cd specially because subprocess cannot change the parent cwd.
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

    if raw == "claude":
        await start_claude_bridge(update, cwd)
        return

    if raw.startswith("claude "):
        prompt = raw.split(maxsplit=1)[1]
        await start_claude_bridge(update, cwd)
        output = await claude_bridge.send_prompt(user_id, prompt)
        await send_output(update, output, cwd)
        return

    if SAFE_MODE:
        await update.message.reply_text(
            "Safe mode is enabled. Use /run <command> to execute shell commands."
        )
        return

    if interactive_sessions.should_start(raw):
        await start_interactive_session(update, raw, cwd)
        return

    # Run other commands.
    try:
        output = await run_shell_command_for_user(user_id, raw, cwd)
    except subprocess.TimeoutExpired:
        output = f"Timeout after {COMMAND_TIMEOUT} seconds."
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
        logger.exception("Timed out while sending output to Telegram")

# ─────────────────────────────────────────────
# COMMANDS /start and /pwd
# ─────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    user_id = update.effective_user.id
    cwd = get_cwd(user_id)
    await update.message.reply_text(
        f"teleshell is active\n\n"
        f"Type commands directly. No / prefix required.\n"
        f"Current working directory: {cwd}\n\n"
        f"Examples: ls -la, pwd, cd /tmp, cat /etc/hostname"
    )

async def cmd_pwd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    cwd = get_cwd(update.effective_user.id)
    await update.message.reply_text(
        f"`{escape_markdown_v2(cwd)}`",
        parse_mode="MarkdownV2",
    )

async def start_claude_bridge(update: Update, cwd: str):
    user_id = update.effective_user.id
    claude_bridge.start(user_id, cwd)
    await update.message.reply_text(
        "Claude bridge started.\n"
        "Send Telegram messages as Claude prompts.\n"
        "Use /exit to close it, or /pty claude for the raw Claude TUI."
    )

async def start_interactive_session(update: Update, command: str, cwd: str):
    user_id = update.effective_user.id
    panel = TerminalPanel(command, cwd)
    interactive_panels[user_id] = panel

    async def output_callback(text: str):
        if text:
            panel.append(text)
            await render_interactive_panel(user_id)

    message = await interactive_sessions.start(
        user_id,
        command,
        cwd,
        output_callback,
    )
    panel.set_status(message)
    sent_message = await update.message.reply_text(
        panel.render_for_telegram(),
        parse_mode="HTML",
        reply_markup=interactive_keyboard(),
    )
    interactive_panel_messages[user_id] = sent_message
    await render_interactive_panel(user_id)

async def render_interactive_panel(user_id: int):
    panel = interactive_panels.get(user_id)
    message = interactive_panel_messages.get(user_id)
    if not panel or not message:
        return
    try:
        await message.edit_text(
            panel.render_for_telegram(),
            parse_mode="HTML",
            reply_markup=interactive_keyboard(),
        )
    except Exception as exc:
        logger.debug("Unable to update interactive panel: %s", exc)

async def handle_interactive_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    if query.from_user.id not in ALLOWED_USER_IDS:
        await query.edit_message_text("Access denied.")
        return

    user_id = query.from_user.id
    data = query.data or ""

    if data == CALLBACK_EXIT:
        stopped = await close_interactive_session(user_id)
        await query.edit_message_text(
            "Interactive session closed." if stopped else "No interactive session is running."
        )
        return

    if data == CALLBACK_CTRL_C:
        interrupted = await interactive_sessions.interrupt(user_id)
        if interrupted:
            panel = interactive_panels.get(user_id)
            if panel:
                panel.set_status("Sent Ctrl-C.")
            await render_interactive_panel(user_id)
        return

    panel = interactive_panels.get(user_id)
    if data == CALLBACK_UP and panel:
        panel.scroll_up()
        await render_interactive_panel(user_id)
        return
    if data == CALLBACK_DOWN and panel:
        panel.scroll_down()
        await render_interactive_panel(user_id)
        return

    key = callback_input(data)
    if key is not None:
        await interactive_sessions.send_key(user_id, key)
        return

async def close_interactive_session(user_id: int) -> bool:
    stopped = await interactive_sessions.stop(user_id)
    interactive_panels.pop(user_id, None)
    interactive_panel_messages.pop(user_id, None)
    return stopped

async def cmd_pty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    command = " ".join(context.args).strip()
    if not command:
        await update.message.reply_text("Usage: /pty <command>")
        return
    if is_blocked(command):
        await update.message.reply_text("Command blocked.")
        return
    await start_interactive_session(
        update,
        command,
        get_cwd(update.effective_user.id),
    )

async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    command = " ".join(context.args).strip()
    if not command:
        await update.message.reply_text("Usage: /run <command>")
        return
    if is_blocked(command):
        await update.message.reply_text("Command blocked.")
        return

    user_id = update.effective_user.id
    cwd = get_cwd(user_id)
    try:
        output = await run_shell_command_for_user(user_id, command, cwd)
    except subprocess.TimeoutExpired:
        output = f"Timeout after {COMMAND_TIMEOUT} seconds."
    except Exception as e:
        output = f"Error: {e}"

    try:
        await send_output(
            update,
            output,
            cwd,
            document_filename=document_filename_for_command(command, cwd),
        )
    except TimedOut:
        logger.exception("Timed out while sending output to Telegram")

async def cmd_claude(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    user_id = update.effective_user.id
    cwd = get_cwd(user_id)
    prompt = " ".join(context.args).strip()
    await start_claude_bridge(update, cwd)
    if prompt:
        output = await claude_bridge.send_prompt(user_id, prompt)
        await send_output(update, output, cwd)

async def cmd_exit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    user_id = update.effective_user.id
    if claude_bridge.stop(user_id):
        await update.message.reply_text("Claude bridge closed.")
        return

    stopped = await close_interactive_session(user_id)
    await update.message.reply_text(
        "Interactive session closed." if stopped else "No interactive session is running."
    )

async def cmd_ctrlc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    interrupted = await interactive_sessions.interrupt(update.effective_user.id)
    await update.message.reply_text(
        "Sent Ctrl-C." if interrupted else "No interactive session is running."
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, TimedOut):
        logger.warning("Request Telegram timeout: %s", context.error)
        return
    if isinstance(context.error, NetworkError):
        logger.warning("Network error Telegram: %s", context.error)
        return
    logger.exception("Unexpected bot error", exc_info=context.error)

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        print("BOT_TOKEN was not found in .env!")
        return
    if not ALLOWED_USER_IDS:
        print("ALLOWED_USER_IDS was not found or is empty in .env!")
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
    app.add_handler(CommandHandler("claude", cmd_claude))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("pty", cmd_pty))
    app.add_handler(CommandHandler("exit", cmd_exit))
    app.add_handler(CommandHandler("ctrlc", cmd_ctrlc))
    app.add_handler(CallbackQueryHandler(handle_interactive_button, pattern=f"^{CALLBACK_PREFIX}"))
    # Text is treated as shell input. Registered bot commands are handled first.
    app.add_handler(MessageHandler(filters.TEXT, handle_command))
    app.add_error_handler(error_handler)

    print("Bot is running... (Ctrl+C to stop)")
    app.run_polling(timeout=POLLING_TIMEOUT, bootstrap_retries=-1)

if __name__ == "__main__":
    main()
