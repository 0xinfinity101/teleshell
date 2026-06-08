import asyncio
import os
import shlex
import signal
from dataclasses import dataclass
from typing import Awaitable, Callable

import pexpect

from command_environment import build_command_env


OutputCallback = Callable[[str], Awaitable[None]]
SpawnFactory = Callable[[str, str], object]
TERMINAL_LINES = 16
TERMINAL_COLUMNS = 42


def parse_command_set(raw: str) -> set[str]:
    return {item.strip() for item in raw.split(",") if item.strip()}


def command_name(command: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError:
        return ""
    if not parts:
        return ""
    return os.path.basename(parts[0])


def default_spawn(command: str, cwd: str):
    env = build_command_env(os.environ)
    env.update({
        "CLICOLOR": "0",
        "NO_COLOR": "1",
        "TERM": "xterm-256color",
    })
    return pexpect.spawn(
        "/bin/bash",
        ["-lc", command],
        cwd=cwd,
        env=env,
        encoding="utf-8",
        echo=False,
        timeout=0.2,
        dimensions=(TERMINAL_LINES, TERMINAL_COLUMNS),
    )


@dataclass
class InteractiveSession:
    user_id: int
    command: str
    cwd: str
    child: object
    output_callback: OutputCallback
    reader_task: asyncio.Task | None = None


class InteractiveSessionManager:
    def __init__(
        self,
        allowed_commands: set[str],
        spawn_factory: SpawnFactory = default_spawn,
    ):
        self.allowed_commands = allowed_commands
        self.spawn_factory = spawn_factory
        self.sessions: dict[int, InteractiveSession] = {}

    def should_start(self, command: str) -> bool:
        return command_name(command) in self.allowed_commands

    def has_session(self, user_id: int) -> bool:
        return user_id in self.sessions

    async def start(
        self,
        user_id: int,
        command: str,
        cwd: str,
        output_callback: OutputCallback,
    ) -> str:
        if self.has_session(user_id):
            return "An interactive session is already running. Use /exit to close it."

        child = self.spawn_factory(command, cwd)
        session = InteractiveSession(user_id, command, cwd, child, output_callback)
        self.sessions[user_id] = session

        if hasattr(child, "read_nonblocking") and hasattr(child, "isalive"):
            session.reader_task = asyncio.create_task(self._read_loop(session))

        return (
            f"Interactive session started: {command}\n"
            "Send messages to interact.\n"
            "Use /exit to close it, or /ctrlc to send Ctrl-C."
        )

    async def send_input(self, user_id: int, text: str) -> bool:
        session = self.sessions.get(user_id)
        if not session:
            return False
        session.child.sendline(text)
        return True

    async def send_key(self, user_id: int, text: str) -> bool:
        session = self.sessions.get(user_id)
        if not session:
            return False
        session.child.send(text)
        return True

    async def interrupt(self, user_id: int) -> bool:
        session = self.sessions.get(user_id)
        if not session:
            return False
        session.child.kill(signal.SIGINT)
        return True

    async def stop(self, user_id: int) -> bool:
        session = self.sessions.pop(user_id, None)
        if not session:
            return False
        if session.reader_task:
            session.reader_task.cancel()
        session.child.terminate(force=True)
        return True

    async def _read_loop(self, session: InteractiveSession):
        try:
            while session.child.isalive():
                try:
                    output = await asyncio.to_thread(
                        session.child.read_nonblocking,
                        4096,
                        0.2,
                    )
                except pexpect.TIMEOUT:
                    await asyncio.sleep(0.1)
                    continue
                except pexpect.EOF:
                    break

                if output:
                    await session.output_callback(output)
        finally:
            self.sessions.pop(session.user_id, None)
            await session.output_callback(f"Interactive session ended: {session.command}")
