import tempfile
import unittest
from pathlib import Path

from service_manager import (
    ServiceConfig,
    apply_autorun,
    parse_bool,
    service_unit_content,
)


class ServiceManagerTest(unittest.TestCase):
    def test_parse_bool_reads_common_true_and_false_values(self):
        self.assertTrue(parse_bool("true"))
        self.assertTrue(parse_bool("1"))
        self.assertTrue(parse_bool("yes"))
        self.assertFalse(parse_bool("false"))
        self.assertFalse(parse_bool("0"))
        self.assertFalse(parse_bool(None))

    def test_service_unit_content_runs_teleshell_from_project_venv(self):
        config = ServiceConfig(
            autorun=True,
            service_name="teleshell",
            project_dir=Path("/opt/teleshell"),
            env_path=Path("/opt/teleshell/.env"),
            python_path=Path("/opt/teleshell/.venv/bin/python"),
            script_path=Path("/opt/teleshell/teleshell.py"),
            systemd_dir=Path("/tmp/systemd/user"),
            command_path="/opt/bin:/usr/bin",
        )

        content = service_unit_content(config)

        self.assertIn("Description=teleshell Telegram terminal bot", content)
        self.assertIn("WorkingDirectory=/opt/teleshell", content)
        self.assertIn("EnvironmentFile=-/opt/teleshell/.env", content)
        self.assertIn("Environment=PATH=/opt/bin:/usr/bin", content)
        self.assertIn("ExecStart=/opt/teleshell/.venv/bin/python /opt/teleshell/teleshell.py", content)
        self.assertIn("Restart=always", content)
        self.assertIn("NoNewPrivileges=true", content)
        self.assertIn("PrivateTmp=true", content)
        self.assertIn("ProtectSystem=full", content)
        self.assertIn("WantedBy=default.target", content)

    def test_apply_autorun_true_writes_and_enables_user_service(self):
        commands = []

        def runner(command, **kwargs):
            commands.append((command, kwargs))

        with tempfile.TemporaryDirectory() as tmpdir:
            systemd_dir = Path(tmpdir)
            config = ServiceConfig(
                autorun=True,
                service_name="teleshell",
                project_dir=Path("/opt/teleshell"),
                env_path=Path("/opt/teleshell/.env"),
                python_path=Path("/opt/teleshell/.venv/bin/python"),
                script_path=Path("/opt/teleshell/teleshell.py"),
                systemd_dir=systemd_dir,
                command_path="/usr/bin",
            )

            message = apply_autorun(config, runner=runner)

            self.assertTrue((systemd_dir / "teleshell.service").exists())
            self.assertEqual(commands[0][0], ["systemctl", "--user", "daemon-reload"])
            self.assertEqual(commands[1][0], ["systemctl", "--user", "enable", "--now", "teleshell.service"])
            self.assertIn("enabled", message)

    def test_apply_autorun_false_disables_and_removes_user_service(self):
        commands = []

        def runner(command, **kwargs):
            commands.append((command, kwargs))

        with tempfile.TemporaryDirectory() as tmpdir:
            systemd_dir = Path(tmpdir)
            unit_path = systemd_dir / "teleshell.service"
            unit_path.write_text("old unit", encoding="utf-8")
            config = ServiceConfig(
                autorun=False,
                service_name="teleshell",
                project_dir=Path("/opt/teleshell"),
                env_path=Path("/opt/teleshell/.env"),
                python_path=Path("/opt/teleshell/.venv/bin/python"),
                script_path=Path("/opt/teleshell/teleshell.py"),
                systemd_dir=systemd_dir,
                command_path="/usr/bin",
            )

            message = apply_autorun(config, runner=runner)

            self.assertFalse(unit_path.exists())
            self.assertEqual(commands[0][0], ["systemctl", "--user", "disable", "--now", "teleshell.service"])
            self.assertEqual(commands[1][0], ["systemctl", "--user", "daemon-reload"])
            self.assertIn("disabled", message)


if __name__ == "__main__":
    unittest.main()
