import asyncio
import os
import signal
import shlex
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


Runner = Callable[[list[str], str, float], subprocess.CompletedProcess]


def build_claude_command(
    command: str,
    args: str,
    session_id: str,
    prompt: str,
    resume: bool = False,
) -> list[str]:
    session_flag = "--resume" if resume else "--session-id"
    return [
        *shlex.split(command),
        *shlex.split(args),
        session_flag,
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
    successful_turns: int = 0
    prompt_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    process_id: int | None = None
    created_at: datetime | None = None


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

    async def kill_session(self, user_id: int) -> str:
        """Kill Claude process associated with user session. Return status message."""
        session = self.sessions.get(user_id)
        if not session:
            self.sessions.pop(user_id, None)  # Cleanup if orphaned
            return "No Claude session found."
        
        if session.process_id is None:
            self.sessions.pop(user_id, None)
            return "Claude session closed (no process tracked)."
        
        pid = session.process_id
        try:
            # Try graceful termination first
            os.kill(pid, signal.SIGTERM)
            # Give it time to shutdown
            await asyncio.sleep(0.5)
        except ProcessLookupError:
            # Process already terminated
            self.sessions.pop(user_id, None)
            return f"Claude session (PID: {pid}) was already terminated."
        except Exception as e:
            self.sessions.pop(user_id, None)
            return f"Error terminating Claude (PID: {pid}): {e}"
        
        # Check if process is still alive, force kill if needed
        try:
            os.kill(pid, 0)  # Signal 0: check if process exists
            # Process still alive, force kill
            os.kill(pid, signal.SIGKILL)
            await asyncio.sleep(0.2)
        except ProcessLookupError:
            # Good, process is dead
            pass
        except Exception as e:
            return f"Error force-killing Claude (PID: {pid}): {e}"
        
        self.sessions.pop(user_id, None)
        return f"Claude session (PID: {pid}) terminated."

    async def send_prompt(self, user_id: int, prompt: str) -> str:
        session = self.sessions.get(user_id)
        if not session:
            return "Claude bridge is not running."
        if session.prompt_lock.locked():
            return "Another Claude prompt is still running."

        async with session.prompt_lock:
            argv = build_claude_command(
                self.command,
                self.args,
                session.session_id,
                prompt,
                resume=session.successful_turns > 0,
            )
            # Convert argv list to shell command string for proper PATH resolution
            cmd_str = " ".join(shlex.quote(arg) for arg in argv)
            
            try:
                # Use shell=True to enable PATH resolution for 'claude' command
                result = await asyncio.to_thread(
                    self._run_with_shell, cmd_str, session, self.timeout
                )
            except subprocess.TimeoutExpired:
                return f"Claude timed out after {self.timeout:g} seconds."
            except Exception as exc:
                return f"Claude error: {exc}"

            output = (result.stdout or "").rstrip()
            error = (result.stderr or "").rstrip()
            if result.returncode == 0:
                session.successful_turns += 1
                return output or "(no output)"
            return error or output or f"Claude exited with status {result.returncode}."

    def _run_with_shell(self, cmd_str: str, session: ClaudeBridgeSession, timeout: float) -> subprocess.CompletedProcess:
        """Execute command with shell=True to enable PATH resolution. Track PID."""
        process = subprocess.Popen(
            cmd_str,
            cwd=session.cwd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Store PID in session for later termination
        session.process_id = process.pid
        session.created_at = datetime.now()
        
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            return subprocess.CompletedProcess(
                args=cmd_str,
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
            )
        except subprocess.TimeoutExpired:
            process.kill()
            raise
