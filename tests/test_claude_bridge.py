import subprocess
import unittest

from claude_bridge import ClaudeBridgeManager, build_claude_command


class ClaudeBridgeCommandTest(unittest.TestCase):
    def test_build_claude_command_uses_print_mode_session_and_prompt(self):
        argv = build_claude_command(
            command="claude",
            args="--print --permission-mode acceptEdits",
            session_id="00000000-0000-4000-8000-000000000000",
            prompt="hello claude",
            resume=False,
        )

        self.assertEqual(argv, [
            "claude",
            "--print",
            "--permission-mode",
            "acceptEdits",
            "--session-id",
            "00000000-0000-4000-8000-000000000000",
            "hello claude",
        ])

    def test_build_claude_command_uses_resume_after_first_prompt(self):
        argv = build_claude_command(
            command="claude",
            args="--print",
            session_id="00000000-0000-4000-8000-000000000000",
            prompt="continue",
            resume=True,
        )

        self.assertEqual(argv, [
            "claude",
            "--print",
            "--resume",
            "00000000-0000-4000-8000-000000000000",
            "continue",
        ])


class ClaudeBridgeManagerTest(unittest.IsolatedAsyncioTestCase):
    async def test_started_session_sends_prompt_with_stable_session_id(self):
        calls = []

        def runner(argv, cwd, timeout):
            calls.append((argv, cwd, timeout))
            return subprocess.CompletedProcess(argv, 0, "hello back", "")

        manager = ClaudeBridgeManager(
            command="claude",
            args="--print",
            timeout=120,
            runner=runner,
            session_id_factory=lambda: "00000000-0000-4000-8000-000000000000",
        )

        manager.start(7, "/tmp")
        first = await manager.send_prompt(7, "who are you?")
        second = await manager.send_prompt(7, "continue")

        self.assertEqual(first, "hello back")
        self.assertEqual(second, "hello back")
        self.assertEqual(calls[0][0], [
            "claude",
            "--print",
            "--session-id",
            "00000000-0000-4000-8000-000000000000",
            "who are you?",
        ])
        self.assertEqual(calls[1][0][-3:], [
            "--resume",
            "00000000-0000-4000-8000-000000000000",
            "continue",
        ])
        self.assertEqual(calls[0][1], "/tmp")
        self.assertEqual(calls[0][2], 120)

    async def test_send_prompt_returns_stderr_for_failed_command(self):
        def runner(argv, cwd, timeout):
            return subprocess.CompletedProcess(argv, 1, "", "permission denied")

        manager = ClaudeBridgeManager(runner=runner)
        manager.start(7, "/tmp")

        output = await manager.send_prompt(7, "edit files")

        self.assertEqual(output, "permission denied")

    async def test_send_prompt_reports_missing_session(self):
        manager = ClaudeBridgeManager()

        output = await manager.send_prompt(7, "hello")

        self.assertEqual(output, "Claude bridge is not running.")


if __name__ == "__main__":
    unittest.main()
