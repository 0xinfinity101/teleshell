import unittest

from terminal_panel import TerminalPanel


class TerminalPanelTest(unittest.TestCase):
    def test_render_includes_command_cwd_and_recent_output(self):
        panel = TerminalPanel("claude", "/home/ijal", max_lines=4)
        panel.set_status("Interactive session started: claude")
        panel.append("Quick safety check:\n1. Yes, I trust this folder\n2. No, exit")

        rendered = panel.render()

        self.assertIn("teleshell: claude", rendered)
        self.assertIn("cwd: /home/ijal", rendered)
        self.assertIn("Quick safety check:", rendered)
        self.assertIn("1. Yes, I trust this folder", rendered)

    def test_render_keeps_last_lines_when_output_is_long(self):
        panel = TerminalPanel("python", "/tmp", max_lines=2)
        panel.append("line 1\nline 2\nline 3")

        rendered = panel.render()

        self.assertNotIn("line 1", rendered)
        self.assertIn("line 2", rendered)
        self.assertIn("line 3", rendered)

    def test_render_can_scroll_up_and_down_through_output(self):
        panel = TerminalPanel("python", "/tmp", max_lines=2)
        panel.append("line 1\nline 2\nline 3\nline 4")

        panel.scroll_up()
        scrolled_up = panel.render()
        panel.scroll_down()
        scrolled_down = panel.render()

        self.assertIn("line 1", scrolled_up)
        self.assertIn("line 2", scrolled_up)
        self.assertIn("line 3", scrolled_down)
        self.assertIn("line 4", scrolled_down)

    def test_append_keeps_view_at_bottom_when_not_scrolled(self):
        panel = TerminalPanel("python", "/tmp", max_lines=2)
        panel.append("line 1\nline 2\nline 3")

        rendered = panel.render()

        self.assertNotIn("line 1", rendered)
        self.assertIn("line 3", rendered)

    def test_render_limits_output_line_width(self):
        panel = TerminalPanel("python", "/tmp", max_lines=1, max_columns=10)
        panel.append("abcdefghijklmnopqrstuvwxyz")

        rendered = panel.render()

        body = rendered.split("\n\n", 1)[1]
        self.assertLessEqual(max(len(line) for line in body.splitlines()), 10)
        self.assertIn("uvwxyz", rendered)

    def test_render_emulates_terminal_line_redraw(self):
        panel = TerminalPanel("claude", "/tmp", max_lines=2, max_columns=20)

        panel.append("old prompt\r\x1b[2Knew prompt")

        rendered = panel.render()
        self.assertIn("new prompt", rendered)
        self.assertNotIn("old prompt", rendered)
        self.assertNotIn("\x1b", rendered)

    def test_render_for_telegram_uses_preformatted_html(self):
        panel = TerminalPanel("claude <debug>", "/tmp", max_lines=1)
        panel.append("value < 2")

        rendered = panel.render_for_telegram()

        self.assertTrue(rendered.startswith("<pre>"))
        self.assertTrue(rendered.endswith("</pre>"))
        self.assertIn("claude &lt;debug&gt;", rendered)
        self.assertIn("value &lt; 2", rendered)

    def test_append_ignores_empty_text(self):
        panel = TerminalPanel("claude", "/home/ijal")
        panel.append("")
        panel.append("   ")

        self.assertIn("(waiting for output)", panel.render())


if __name__ == "__main__":
    unittest.main()
