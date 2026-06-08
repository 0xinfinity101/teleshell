import asyncio
import unittest

from interactive_sessions import InteractiveSessionManager, command_name, parse_command_set


class FakeChild:
    def __init__(self):
        self.lines = []
        self.keys = []
        self.terminated = False
        self.interrupted = False

    def sendline(self, line):
        self.lines.append(line)

    def send(self, text):
        self.keys.append(text)

    def terminate(self, force=False):
        self.terminated = True
        self.force = force

    def kill(self, signal_number):
        self.interrupted = signal_number


class FakeReadableChild:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def isalive(self):
        return bool(self.chunks)

    def read_nonblocking(self, size, timeout):
        return self.chunks.pop(0)


class InteractiveSessionHelpersTest(unittest.TestCase):
    def test_parse_command_set_trims_empty_items(self):
        commands = parse_command_set("claude, python3,, node ")

        self.assertEqual(commands, {"claude", "python3", "node"})

    def test_command_name_uses_first_shell_token_basename(self):
        self.assertEqual(command_name("/usr/bin/python3 -q"), "python3")
        self.assertEqual(command_name('claude --model "sonnet"'), "claude")

    def test_command_name_returns_empty_for_invalid_shell_syntax(self):
        self.assertEqual(command_name("claude 'unterminated"), "")


class InteractiveSessionManagerTest(unittest.IsolatedAsyncioTestCase):
    async def test_allowlisted_command_can_start_interactive_session(self):
        manager = InteractiveSessionManager({"claude"})

        self.assertTrue(manager.should_start("claude"))
        self.assertTrue(manager.should_start("claude --continue"))
        self.assertFalse(manager.should_start("ls"))

    async def test_send_input_routes_text_to_active_session(self):
        child = FakeChild()
        manager = InteractiveSessionManager({"claude"}, spawn_factory=lambda command, cwd: child)

        await manager.start(7, "claude", "/tmp", lambda text: asyncio.sleep(0))
        sent = await manager.send_input(7, "hello")

        self.assertTrue(sent)
        self.assertEqual(child.lines, ["hello"])

    async def test_send_key_routes_raw_input_to_active_session(self):
        child = FakeChild()
        manager = InteractiveSessionManager({"claude"}, spawn_factory=lambda command, cwd: child)

        await manager.start(7, "claude", "/tmp", lambda text: asyncio.sleep(0))
        sent = await manager.send_key(7, "1")

        self.assertTrue(sent)
        self.assertEqual(child.keys, ["1"])
        self.assertEqual(child.lines, [])

    async def test_stop_session_terminates_active_process(self):
        child = FakeChild()
        manager = InteractiveSessionManager({"claude"}, spawn_factory=lambda command, cwd: child)

        await manager.start(7, "claude", "/tmp", lambda text: asyncio.sleep(0))
        stopped = await manager.stop(7)

        self.assertTrue(stopped)
        self.assertTrue(child.terminated)
        self.assertFalse(manager.has_session(7))

    async def test_read_loop_forwards_raw_terminal_output_to_callback(self):
        child = FakeReadableChild(["\x1b[93mAccessing\x1b[39m workspace"])
        manager = InteractiveSessionManager({"claude"}, spawn_factory=lambda command, cwd: child)
        seen = []

        async def collect(text):
            seen.append(text)

        await manager.start(7, "claude", "/tmp", collect)
        await asyncio.sleep(0.1)

        self.assertIn("\x1b[93mAccessing\x1b[39m workspace", seen)


if __name__ == "__main__":
    unittest.main()
