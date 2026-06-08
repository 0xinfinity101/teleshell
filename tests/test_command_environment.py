import os
import unittest
from pathlib import Path

from command_environment import build_command_env, build_command_path


class CommandEnvironmentTest(unittest.TestCase):
    def test_build_command_path_prepends_common_user_bin_directories(self):
        path = build_command_path(
            base_path="/usr/bin:/bin",
            extra_paths="",
            home=Path("/home/ijal"),
        )

        parts = path.split(os.pathsep)
        self.assertEqual(parts[0], "/home/ijal/.opencode/bin")
        self.assertIn("/home/ijal/.local/bin", parts)
        self.assertIn("/home/ijal/.npm-global/bin", parts)
        self.assertTrue(parts.index("/home/ijal/.opencode/bin") < parts.index("/usr/bin"))

    def test_build_command_path_prepends_explicit_extra_paths(self):
        path = build_command_path(
            base_path="/usr/bin",
            extra_paths="/opt/bin:/custom/bin",
            home=Path("/home/ijal"),
        )

        self.assertEqual(path.split(os.pathsep)[:2], ["/opt/bin", "/custom/bin"])

    def test_build_command_env_sets_path_without_mutating_base_env(self):
        base_env = {"PATH": "/usr/bin", "COMMAND_EXTRA_PATHS": "/opt/bin"}

        env = build_command_env(base_env, home=Path("/home/ijal"))

        self.assertEqual(base_env["PATH"], "/usr/bin")
        self.assertTrue(env["PATH"].startswith("/opt/bin:"))
        self.assertIn("/home/ijal/.opencode/bin", env["PATH"])


if __name__ == "__main__":
    unittest.main()
