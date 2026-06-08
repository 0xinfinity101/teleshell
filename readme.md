# teleshell

Telegram bot for running your local terminal from Telegram. It is useful for quick access to a personal machine when you are away from the keyboard.

## Features

- Run terminal commands directly from a Telegram chat.
- Persistent `cd` per user, so each working directory is kept while the bot is running.
- Short output is sent as a message.
- Long output is automatically sent as a file.
- If `cat file-name` produces long output, the Telegram document uses the original file name.
- User ID whitelist.
- Telegram API timeouts can be configured from `.env`.

## Security Warning

This bot gives shell access to the machine where it runs. Use it only for personal access, with a protected bot token, a correct user whitelist, and ideally a restricted Linux user or container.

Do not commit `.env`. It contains your Telegram token and private user IDs.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

```env
BOT_TOKEN=token_from_botfather
ALLOWED_USER_IDS=123456789
```

Find your Telegram user ID with a bot such as `@userinfobot`.

## Configuration

The full example is in `.env.example`.

```env
TELEGRAM_CONNECT_TIMEOUT=15
TELEGRAM_READ_TIMEOUT=30
TELEGRAM_WRITE_TIMEOUT=30
TELEGRAM_POOL_TIMEOUT=10
TELEGRAM_MEDIA_WRITE_TIMEOUT=120
TELEGRAM_GET_UPDATES_READ_TIMEOUT=60
POLLING_TIMEOUT=30
```

Increase these timeouts if the Telegram connection is often slow or output file uploads often time out.

## Running The Bot

```bash
source .venv/bin/activate
python teleshell.py
```

In Telegram:

```bash
pwd
cd Documents/novel/manuscript
ls
cat chapter-01.md
```

If `cat chapter-01.md` is too long to send as a message, the bot sends a document named `chapter-01.md`.

## Test

```bash
source .venv/bin/activate
python -m unittest test_teleshell.py
```

## Notes

- `ALLOWED_USER_IDS` is a whitelist based on Telegram user IDs, not group chat IDs.
- `ALLOWED_CHAT_IDS` is still read as a legacy name for compatibility.
- Shell commands are still executed with `shell=True`, so treat this bot as full terminal access.
