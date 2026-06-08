import os
import tempfile
import unittest
from unittest.mock import patch

import teleshell as bot


class TeleshellHelpersTest(unittest.TestCase):
    def test_resolve_cd_target_expands_home_before_relative_join(self):
        target = bot.resolve_cd_target("/tmp/current", "~/Documents")

        self.assertEqual(target, os.path.expanduser("~/Documents"))

    def test_resolve_cd_target_keeps_relative_paths_under_current_directory(self):
        target = bot.resolve_cd_target("/tmp/current", "../next")

        self.assertEqual(target, "/tmp/next")

    def test_parse_float_env_uses_default_for_missing_or_invalid_values(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(bot.get_float_env("MISSING_TIMEOUT", 42.0), 42.0)

        with patch.dict(os.environ, {"BAD_TIMEOUT": "not-a-number"}):
            self.assertEqual(bot.get_float_env("BAD_TIMEOUT", 12.0), 12.0)

    def test_escape_markdown_v2_escapes_shell_output_characters(self):
        text = "file_name [ok] `cmd` path=/tmp/a-b!"

        escaped = bot.escape_markdown_v2(text)

        self.assertEqual(escaped, r"file\_name \[ok\] \`cmd\` path\=/tmp/a\-b\!")

    def test_document_filename_for_single_cat_uses_requested_file_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "chapter-01.md")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("content")

            filename = bot.document_filename_for_command("cat chapter-01.md", tmpdir)

        self.assertEqual(filename, "chapter-01.md")

    def test_document_filename_for_non_file_command_uses_default(self):
        filename = bot.document_filename_for_command("ls -la", "/tmp")

        self.assertEqual(filename, "output.txt")


class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return FakeSentMessage(text, kwargs)


class FakeSentMessage:
    def __init__(self, text, kwargs):
        self.text = text
        self.kwargs = kwargs
        self.edits = []

    async def edit_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class FakeUser:
    id = 123


class FakeUpdate:
    def __init__(self, text):
        self.message = FakeMessage(text)
        self.effective_user = FakeUser()


class FakeContext:
    def __init__(self, args=None):
        self.args = args or []


class FakeCallbackQuery:
    def __init__(self, user_id=123, data="interactive:exit"):
        self.from_user = type("User", (), {"id": user_id})()
        self.data = data
        self.answers = []
        self.edits = []

    async def answer(self):
        self.answers.append(True)

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class FakeCallbackUpdate:
    def __init__(self, user_id=123, data="interactive:exit"):
        self.callback_query = FakeCallbackQuery(user_id, data)
        self.effective_user = self.callback_query.from_user


class FakeInteractiveSessions:
    def __init__(self, has_session):
        self._has_session = has_session
        self.sent = []
        self.keys = []
        self.started = []
        self.stopped = []
        self.interrupted = []

    def has_session(self, user_id):
        return self._has_session

    def should_start(self, command):
        return False

    async def send_input(self, user_id, text):
        self.sent.append((user_id, text))
        return True

    async def send_key(self, user_id, text):
        self.keys.append((user_id, text))
        return True

    async def start(self, user_id, command, cwd, output_callback):
        self.started.append((user_id, command, cwd))
        return f"Interactive session started: {command}"

    async def stop(self, user_id):
        self.stopped.append(user_id)
        return self._has_session

    async def interrupt(self, user_id):
        self.interrupted.append(user_id)
        return self._has_session


class FakeClaudeBridge:
    def __init__(self, has_session=False):
        self._has_session = has_session
        self.started = []
        self.prompts = []
        self.stopped = []

    def has_session(self, user_id):
        return self._has_session

    def start(self, user_id, cwd):
        self._has_session = True
        self.started.append((user_id, cwd))

    async def send_prompt(self, user_id, prompt):
        self.prompts.append((user_id, prompt))
        return "claude says hi"

    def stop(self, user_id):
        self.stopped.append(user_id)
        was_running = self._has_session
        self._has_session = False
        return was_running


class TeleshellRoutingTest(unittest.IsolatedAsyncioTestCase):
    async def test_claude_command_starts_claude_bridge_instead_of_tui_session(self):
        sessions = FakeInteractiveSessions(has_session=False)
        bridge = FakeClaudeBridge(has_session=False)
        update = FakeUpdate("claude")

        with patch.object(bot, "ALLOWED_USER_IDS", {123}), \
             patch.object(bot, "interactive_sessions", sessions), \
             patch.object(bot, "claude_bridge", bridge):
            await bot.handle_command(update, None)

        self.assertEqual(bridge.started, [(123, os.path.expanduser("~"))])
        self.assertEqual(sessions.started, [])
        self.assertIn("Claude bridge started", update.message.replies[0][0])

    async def test_active_claude_bridge_receives_plain_text_prompt(self):
        sessions = FakeInteractiveSessions(has_session=False)
        bridge = FakeClaudeBridge(has_session=True)
        update = FakeUpdate("are you claude?")

        with patch.object(bot, "ALLOWED_USER_IDS", {123}), \
             patch.object(bot, "interactive_sessions", sessions), \
             patch.object(bot, "claude_bridge", bridge), \
             patch.object(bot, "run_shell_command") as run_shell_command:
            await bot.handle_command(update, None)

        self.assertEqual(bridge.prompts, [(123, "are you claude?")])
        self.assertIn("claude says hi", update.message.replies[0][0])
        run_shell_command.assert_not_called()

    async def test_exit_closes_claude_bridge(self):
        bridge = FakeClaudeBridge(has_session=True)
        update = FakeUpdate("/exit")

        with patch.object(bot, "ALLOWED_USER_IDS", {123}), \
             patch.object(bot, "claude_bridge", bridge), \
             patch.object(bot, "interactive_sessions", FakeInteractiveSessions(has_session=False)):
            await bot.cmd_exit(update, None)

        self.assertEqual(bridge.stopped, [123])
        self.assertEqual(update.message.replies[0][0], "Claude bridge closed.")

    async def test_claude_slash_command_can_send_first_prompt(self):
        bridge = FakeClaudeBridge(has_session=False)
        update = FakeUpdate("/claude hello")
        context = FakeContext(["hello", "claude"])

        with patch.object(bot, "ALLOWED_USER_IDS", {123}), \
             patch.object(bot, "claude_bridge", bridge):
            await bot.cmd_claude(update, context)

        self.assertEqual(bridge.started, [(123, os.path.expanduser("~"))])
        self.assertEqual(bridge.prompts, [(123, "hello claude")])
        self.assertIn("Claude bridge started", update.message.replies[0][0])
        self.assertIn("claude says hi", update.message.replies[1][0])

    async def test_start_interactive_session_adds_terminal_panel_controls(self):
        sessions = FakeInteractiveSessions(has_session=False)
        update = FakeUpdate("claude")

        with patch.object(bot, "interactive_sessions", sessions):
            await bot.start_interactive_session(update, "claude", "/tmp")

        reply_text, kwargs = update.message.replies[0]
        keyboard = kwargs["reply_markup"].inline_keyboard
        self.assertEqual(kwargs["parse_mode"], "HTML")
        self.assertTrue(reply_text.startswith("<pre>"))
        self.assertIn("teleshell: claude", reply_text)
        self.assertIn("cwd: /tmp", reply_text)
        self.assertEqual([button.text for button in keyboard[0]], ["Up", "Down"])
        self.assertEqual([button.text for button in keyboard[1]], ["1", "2", "Enter", "Esc"])
        self.assertEqual([button.text for button in keyboard[2]], ["Ctrl-C", "Close"])

    async def test_close_button_callback_stops_session(self):
        sessions = FakeInteractiveSessions(has_session=True)
        update = FakeCallbackUpdate()

        with patch.object(bot, "ALLOWED_USER_IDS", {123}), \
             patch.object(bot, "interactive_sessions", sessions):
            await bot.handle_interactive_button(update, None)

        self.assertEqual(sessions.stopped, [123])
        self.assertEqual(update.callback_query.answers, [True])
        self.assertEqual(update.callback_query.edits[0][0], "Interactive session closed.")

    async def test_key_button_callback_sends_raw_key_to_session(self):
        sessions = FakeInteractiveSessions(has_session=True)
        update = FakeCallbackUpdate(data="interactive:key:1")

        with patch.object(bot, "ALLOWED_USER_IDS", {123}), \
             patch.object(bot, "interactive_sessions", sessions):
            await bot.handle_interactive_button(update, None)

        self.assertEqual(sessions.keys, [(123, "1")])
        self.assertEqual(update.callback_query.answers, [True])

    async def test_enter_button_callback_sends_raw_enter_to_session(self):
        sessions = FakeInteractiveSessions(has_session=True)
        update = FakeCallbackUpdate(data="interactive:key:enter")

        with patch.object(bot, "ALLOWED_USER_IDS", {123}), \
             patch.object(bot, "interactive_sessions", sessions):
            await bot.handle_interactive_button(update, None)

        self.assertEqual(sessions.keys, [(123, "\r")])

    async def test_scroll_button_callback_updates_terminal_panel(self):
        sessions = FakeInteractiveSessions(has_session=True)
        sent_message = FakeSentMessage("", {})
        panel = bot.TerminalPanel("claude", "/tmp", max_lines=2)
        panel.append("line 1\nline 2\nline 3\nline 4")
        update = FakeCallbackUpdate(data="interactive:scroll:up")

        with patch.object(bot, "ALLOWED_USER_IDS", {123}), \
             patch.object(bot, "interactive_sessions", sessions), \
             patch.dict(bot.interactive_panels, {123: panel}, clear=True), \
             patch.dict(bot.interactive_panel_messages, {123: sent_message}, clear=True):
            await bot.handle_interactive_button(update, None)

        self.assertEqual(sessions.keys, [])
        self.assertEqual(update.callback_query.answers, [True])
        self.assertIn("line 1", sent_message.edits[-1][0])

    async def test_active_interactive_session_receives_plain_text_instead_of_shell(self):
        sessions = FakeInteractiveSessions(has_session=True)
        update = FakeUpdate("hello claude")

        with patch.object(bot, "ALLOWED_USER_IDS", {123}), \
             patch.object(bot, "interactive_sessions", sessions), \
             patch.object(bot, "run_shell_command") as run_shell_command:
            await bot.handle_command(update, None)

        self.assertEqual(sessions.sent, [(123, "hello claude")])
        run_shell_command.assert_not_called()

    async def test_active_interactive_session_receives_slash_text(self):
        sessions = FakeInteractiveSessions(has_session=True)
        update = FakeUpdate("/help")

        with patch.object(bot, "ALLOWED_USER_IDS", {123}), \
             patch.object(bot, "interactive_sessions", sessions), \
             patch.object(bot, "run_shell_command") as run_shell_command:
            await bot.handle_command(update, None)

        self.assertEqual(sessions.sent, [(123, "/help")])
        run_shell_command.assert_not_called()

    async def test_unknown_slash_command_without_session_does_not_run_shell(self):
        sessions = FakeInteractiveSessions(has_session=False)
        update = FakeUpdate("/unknown")

        with patch.object(bot, "ALLOWED_USER_IDS", {123}), \
             patch.object(bot, "interactive_sessions", sessions), \
             patch.object(bot, "run_shell_command") as run_shell_command:
            await bot.handle_command(update, None)

        self.assertEqual(update.message.replies[0][0], "Unknown command. Use /pty <command> to start a session.")
        run_shell_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
