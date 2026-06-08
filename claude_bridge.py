import asyncio
import shlex
import subprocess
import uuid
from dataclasses import dataclass
from typing import Callable


Runner = Callable[[list[str], str, float], subprocess.CompletedProcess]


def build_claude_command(
    command: str,
    args: str,
    session_id: str,
    prompt: str,
) -> list[str]:
    return [
        *shlex.split(command),
        *shlex.split(args),
        "--session-id",
        session_id,
        prompt,
    ]


def default_runner(argv: list[str], cwd: str, timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


@dataclass
class ClaudeBridgeSession:
    cwd: str
    session_id: str


class ClaudeBridgeManager:
    def __init__(
        self,
        command: str = "claude",
        args: str = "--print --permission-mode acceptEdits",
        timeout: float = 300.0,
        runner: Runner = default_runner,
        session_id_factory: Callable[[], str] | None = None,
    ):
        self.command = command
        self.args = args
        self.timeout = timeout
        self.runner = runner
        self.session_id_factory = session_id_factory or (lambda: str(uuid.uuid4()))
        self.sessions: dict[int, ClaudeBridgeSession] = {}

    def start(self, user_id: int, cwd: str) -> ClaudeBridgeSession:
        session = ClaudeBridgeSession(cwd=cwd, session_id=self.session_id_factory())
        self.sessions[user_id] = session
        return session

    def has_session(self, user_id: int) -> bool:
        return user_id in self.sessions

    def stop(self, user_id: int) -> bool:
        return self.sessions.pop(user_id, None) is not None

    async def send_prompt(self, user_id: int, prompt: str) -> str:
        session = self.sessions.get(user_id)
        if not session:
            return "Claude bridge is not running."

        argv = build_claude_command(
            self.command,
            self.args,
            session.session_id,
            prompt,
        )
        try:
            result = await asyncio.to_thread(self.runner, argv, session.cwd, self.timeout)
        except subprocess.TimeoutExpired:
            return f"Claude timed out after {self.timeout:g} seconds."
        except Exception as exc:
            return f"Claude error: {exc}"

        output = (result.stdout or "").rstrip()
        error = (result.stderr or "").rstrip()
        if result.returncode == 0:
            return output or "(no output)"
        return error or output or f"Claude exited with status {result.returncode}."
