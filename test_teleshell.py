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


if __name__ == "__main__":
    unittest.main()
