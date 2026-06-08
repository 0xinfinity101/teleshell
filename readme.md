# teleshell

**A private Telegram control plane for your local machine.**

`teleshell` lets you operate a trusted computer from Telegram: run shell commands, keep a per-user working directory, open pseudo-terminal sessions for interactive CLIs, and talk to Claude Code through a chat bridge. It is designed for personal remote access when you are away from your keyboard, with safe command routing, Telegram user whitelisting, and optional systemd autorun.

## What It Does

| Capability | How it works |
| --- | --- |
| Safe shell access | Send shell commands with `/run <command>` when `SAFE_MODE=true`. |
| Working directory memory | Use `cd`, then later commands run from that directory. |
| Claude Code bridge | Type `claude`, then send normal Telegram messages as Claude prompts. |
| Interactive PTY sessions | Use `/pty python`, `/pty ssh user@host`, or another CLI that needs stdin. |
| Long output handling | Large output is sent as a Telegram document instead of flooding chat. |
| Background service | Enable autorun with a systemd user service. |
| Access control | Only `ALLOWED_USER_IDS` can use the bot. |

## How It Differs From SSH

`teleshell` is not a replacement for SSH. It is a Telegram-native control layer for moments when chat is the most convenient interface.

| SSH | teleshell |
| --- | --- |
| Opens a real terminal session. | Uses Telegram messages, documents, inline buttons, and optional PTY panels. |
| Requires network reachability to the machine, usually through LAN, VPN, port forwarding, or a tunnel. | Uses Telegram as the transport, so the bot can receive commands as long as the machine can reach Telegram. |
| Best for long terminal work, full-screen tools, editors, and low-latency sessions. | Best for quick checks, remote commands, Claude prompts, small fixes, and phone-based workflows. |
| Authentication is handled by SSH keys, users, and host keys. | Authentication is handled by Telegram bot token secrecy plus `ALLOWED_USER_IDS`. |
| Mature and battle-tested as a remote shell protocol. | Convenience-focused and intentionally narrower; treat it as a private automation surface. |

Use SSH when you need a real terminal. Use `teleshell` when you want to operate your machine from Telegram without exposing an SSH port or opening a terminal app.

## Security Model

This project intentionally gives shell access to the machine where it runs. Treat it like SSH exposed through a Telegram bot.

Use it only for personal access, with:

- a private bot token,
- a strict `ALLOWED_USER_IDS` whitelist,
- `SAFE_MODE=true`,
- a non-root Linux user,
- and a trusted machine or container.

Do not commit `.env`. It contains your Telegram token and private user IDs.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```env
BOT_TOKEN=token_from_botfather
ALLOWED_USER_IDS=123456789
SAFE_MODE=true
```

Find your Telegram user ID with a bot such as `@userinfobot`.

Run the bot:

```bash
python teleshell.py
```

Try it in Telegram:

```text
pwd
cd Documents/novel/manuscript
/run ls
/run cat chapter-01.md
claude
summarize this folder
/exit
```

## Configuration

The full example is in `.env.example`.

```env
LOG_LEVEL=WARNING
HTTP_LOG_LEVEL=WARNING
TELEGRAM_CONNECT_TIMEOUT=15
TELEGRAM_READ_TIMEOUT=30
TELEGRAM_WRITE_TIMEOUT=30
TELEGRAM_POOL_TIMEOUT=10
TELEGRAM_MEDIA_WRITE_TIMEOUT=120
TELEGRAM_GET_UPDATES_READ_TIMEOUT=60
POLLING_TIMEOUT=30
SAFE_MODE=true
AUTORUN=false
SERVICE_NAME=teleshell
COMMAND_EXTRA_PATHS=
CLAUDE_BRIDGE_COMMAND=claude
CLAUDE_BRIDGE_ARGS=--print --permission-mode acceptEdits
CLAUDE_BRIDGE_TIMEOUT=300
INTERACTIVE_COMMANDS=python,python3,node,ssh,mysql,psql
```

Keep `HTTP_LOG_LEVEL=WARNING` unless you are actively debugging Telegram requests, because lower levels may log request URLs.

`teleshell` automatically prepends common user command directories to `PATH`, including `~/.opencode/bin`, `~/.local/bin`, `~/.bun/bin`, `~/.npm-global/bin`, and `~/.cargo/bin`. If a tool is installed somewhere else, add it to `COMMAND_EXTRA_PATHS` using colon-separated paths:

```env
COMMAND_EXTRA_PATHS=/opt/my-tools/bin:/another/bin
```

## Shell Commands

With `SAFE_MODE=true`, shell commands must be sent with `/run <command>`:

```text
/run git status
/run python -m unittest discover -s tests
/run cat chapter-01.md
```

This keeps normal chat text from becoming an accidental shell command. If `/run cat chapter-01.md` produces long output, the bot sends a document named `chapter-01.md`.

You can set `SAFE_MODE=false` to restore direct shell execution from plain text, but that makes every Telegram message from an allowed user a shell command.

## Claude Bridge

Type `claude` to start a Claude chat bridge from the current working directory. While the bridge is active, normal Telegram messages are sent to Claude Code in non-interactive print mode, and Claude's response is sent back to the chat.

```text
claude
read this project and summarize it
run the tests and explain the failures
/exit
```

You can also send the first prompt immediately:

```text
claude explain this repository
```

The bridge uses `claude --print` by default, with a stable Claude session ID for each Telegram session. The first prompt creates the Claude session with `--session-id`; later prompts continue it with `--resume`, so the conversation state is preserved. Use `CLAUDE_BRIDGE_ARGS` to adjust Claude flags.

## Interactive Sessions

Some CLI apps need a real terminal and ongoing stdin, so one-shot command execution is not enough. `teleshell` can open a mini-shell session through a pseudo-terminal.

With `SAFE_MODE=true`, start interactive programs explicitly:

```text
/pty python
/pty ssh user@example.com
/pty opencode
```

When `SAFE_MODE=false`, allowlisted commands in `INTERACTIVE_COMMANDS` can start automatically.

While a session is active, `teleshell` keeps a mini terminal panel updated by editing the session message. Normal Telegram messages are sent to that process instead of being executed as new shell commands.

The panel is rendered as a preformatted terminal viewport and uses a small ANSI terminal emulator for apps that redraw the screen. Use `Up` and `Down` to scroll through older or newer output.

```text
[Up] [Down]
[1] [2] [Enter] [Esc]
[Ctrl-C] [Close]
```

Session controls:

```text
/exit
/ctrlc
```

## Autorun

`teleshell` can run in the background through a systemd user service. Set this in `.env` to enable automatic background startup:

```env
AUTORUN=true
SERVICE_NAME=teleshell
```

Apply the setting:

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

Useful service manager commands:

```bash
python service_manager.py status
python service_manager.py unit
python service_manager.py enable
python service_manager.py disable
```

Useful systemd commands:

```bash
systemctl --user restart teleshell.service
systemctl --user stop teleshell.service
systemctl --user start teleshell.service
systemctl --user disable --now teleshell.service
systemctl --user status teleshell.service --no-pager
journalctl --user -u teleshell.service -n 80 --no-pager
```

To reduce noisy Telegram HTTP logs, keep this in `.env` and restart the service:

```env
LOG_LEVEL=WARNING
HTTP_LOG_LEVEL=WARNING
```

The generated service includes basic hardening options such as `NoNewPrivileges=true`, `PrivateTmp=true`, and `ProtectSystem=full`.

To allow the service to start after reboot before you log in, enable lingering once:

```bash
loginctl enable-linger "$USER"
```

## Testing

```bash
source .venv/bin/activate
python -m unittest discover -s tests
```

## Notes

- `ALLOWED_USER_IDS` is a whitelist based on Telegram user IDs, not group chat IDs.
- `ALLOWED_CHAT_IDS` is still read as a legacy name for compatibility.
- Shell commands are still executed with `shell=True` behind `/run`, so treat this bot as full terminal access.
