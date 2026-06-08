# teleshell

Telegram bot for running your local terminal from Telegram. It is useful for quick access to a personal machine when you are away from the keyboard.

## Features

- Run terminal commands directly from a Telegram chat.
- Persistent `cd` per user, so each working directory is kept while the bot is running.
- Short output is sent as a message.
- Long output is automatically sent as a file.
- If `cat file-name` produces long output, the Telegram document uses the original file name.
- Claude chat bridge for Claude Code prompts from Telegram.
- Interactive mini-shell sessions for allowlisted commands such as `python` and `ssh`.
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
AUTORUN=false
SERVICE_NAME=teleshell
CLAUDE_BRIDGE_COMMAND=claude
CLAUDE_BRIDGE_ARGS=--print --permission-mode acceptEdits
CLAUDE_BRIDGE_TIMEOUT=300
INTERACTIVE_COMMANDS=python,python3,node,ssh,mysql,psql
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

## Autorun

`teleshell` can run in the background through a systemd user service. Set this in `.env` to enable automatic background startup:

```env
AUTORUN=true
SERVICE_NAME=teleshell
```

Then apply the setting:

```bash
source .venv/bin/activate
python service_manager.py apply
```

Changing `.env` alone does not change systemd. Run `python service_manager.py apply` each time you switch `AUTORUN` between `true` and `false`.

When `AUTORUN=true`, the service manager writes `~/.config/systemd/user/teleshell.service`, reloads systemd, and runs:

```bash
systemctl --user enable --now teleshell.service
```

When `AUTORUN=false`, running `python service_manager.py apply` disables and removes the user service.

The generated service uses the repository virtual environment by default:

```bash
.venv/bin/python teleshell.py
```

Useful commands:

```bash
python service_manager.py status
python service_manager.py unit
python service_manager.py enable
python service_manager.py disable
```

To allow the service to start after reboot before you log in, enable lingering once:

```bash
loginctl enable-linger "$USER"
```

## Claude Bridge

Type `claude` to start a Claude chat bridge from the current working directory. While the bridge is active, normal Telegram messages are sent to Claude Code in non-interactive print mode, and Claude's response is sent back to the chat.

```bash
claude
read this project and summarize it
run the tests and explain the failures
/exit
```

You can also send the first prompt immediately:

```bash
claude explain this repository
```

The bridge uses `claude --print` by default, with a stable Claude session ID for each Telegram session. The first prompt creates the Claude session with `--session-id`; later prompts continue it with `--resume`, so the conversation state is preserved. Use `CLAUDE_BRIDGE_ARGS` to adjust Claude flags. If Claude needs broader tool permissions for your workflow, configure that in `.env` deliberately.

## Interactive Sessions

Some CLI apps need a real terminal and ongoing stdin, so one-shot command execution is not enough. `teleshell` can open a mini-shell session through a pseudo-terminal.

Allowlisted interactive commands start automatically:

```bash
python
ssh user@example.com
```

You can force any command into interactive mode with `/pty`:

```bash
/pty claude
/pty python
```

While a session is active, `teleshell` keeps a mini terminal panel updated by editing the session message. Normal Telegram messages are sent to that process instead of being executed as new shell commands.

The panel is rendered as a preformatted terminal viewport and uses a small ANSI terminal emulator for apps that redraw the screen, such as Claude Code. It uses about 16 rows by 42 columns, which keeps it close to a small Telegram terminal. Use `Up` and `Down` to scroll through older or newer output.

The panel includes buttons for common interactive prompts:

```text
[Up] [Down]
[1] [2] [Enter] [Esc]
[Ctrl-C] [Close]
```

Session controls:

```bash
/exit
/ctrlc
```

For command-line prompts, tap `1`, `2`, `Enter`, or `Esc` as needed.

## Test

```bash
source .venv/bin/activate
python -m unittest discover -s tests
```

## Notes

- `ALLOWED_USER_IDS` is a whitelist based on Telegram user IDs, not group chat IDs.
- `ALLOWED_CHAT_IDS` is still read as a legacy name for compatibility.
- Shell commands are still executed with `shell=True`, so treat this bot as full terminal access.
