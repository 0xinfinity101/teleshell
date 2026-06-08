import argparse
import getpass
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dotenv import dotenv_values

from command_environment import build_command_path


TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off", ""}
Runner = Callable[..., subprocess.CompletedProcess]


@dataclass
class ServiceConfig:
    autorun: bool
    service_name: str
    project_dir: Path
    env_path: Path
    python_path: Path
    script_path: Path
    systemd_dir: Path
    command_path: str

    @property
    def unit_name(self) -> str:
        if self.service_name.endswith(".service"):
            return self.service_name
        return f"{self.service_name}.service"

    @property
    def unit_path(self) -> Path:
        return self.systemd_dir / self.unit_name


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return default


def service_name_from_env(value: str | None) -> str:
    name = (value or "teleshell").strip()
    if not name:
        return "teleshell"
    if "/" in name or "\\" in name:
        raise ValueError("SERVICE_NAME cannot contain path separators.")
    return name


def build_config(env_path: Path | None = None) -> ServiceConfig:
    project_dir = Path(__file__).resolve().parent
    env_path = env_path or project_dir / ".env"
    env = dotenv_values(env_path)

    venv_python = project_dir / ".venv" / "bin" / "python"
    python_path = Path(env.get("SERVICE_PYTHON") or (venv_python if venv_python.exists() else sys.executable))
    script_path = Path(env.get("SERVICE_SCRIPT") or project_dir / "teleshell.py")
    systemd_dir = Path(
        env.get("SYSTEMD_USER_DIR")
        or Path.home() / ".config" / "systemd" / "user"
    )
    command_path = build_command_path(
        env.get("SERVICE_PATH") or os.environ.get("PATH"),
        extra_paths=env.get("COMMAND_EXTRA_PATHS"),
    )

    return ServiceConfig(
        autorun=parse_bool(env.get("AUTORUN"), default=False),
        service_name=service_name_from_env(env.get("SERVICE_NAME")),
        project_dir=project_dir,
        env_path=env_path,
        python_path=python_path,
        script_path=script_path,
        systemd_dir=systemd_dir,
        command_path=command_path,
    )


def service_unit_content(config: ServiceConfig) -> str:
    return "\n".join([
        "[Unit]",
        "Description=teleshell Telegram terminal bot",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        "Type=simple",
        f"WorkingDirectory={config.project_dir}",
        f"EnvironmentFile=-{config.env_path}",
        "Environment=PYTHONUNBUFFERED=1",
        f"Environment=PATH={config.command_path}",
        f"ExecStart={config.python_path} {config.script_path}",
        "Restart=always",
        "RestartSec=5",
        "",
        "[Install]",
        "WantedBy=default.target",
        "",
    ])


def apply_autorun(config: ServiceConfig, runner: Runner = subprocess.run) -> str:
    if config.autorun:
        config.systemd_dir.mkdir(parents=True, exist_ok=True)
        config.unit_path.write_text(service_unit_content(config), encoding="utf-8")
        runner(["systemctl", "--user", "daemon-reload"], check=True)
        runner(["systemctl", "--user", "enable", "--now", config.unit_name], check=True)
        return (
            f"{config.unit_name} enabled and started.\n"
            "If it should start before login after reboot, run: "
            f"loginctl enable-linger {getpass.getuser()}"
        )

    runner(["systemctl", "--user", "disable", "--now", config.unit_name], check=False)
    if config.unit_path.exists():
        config.unit_path.unlink()
    runner(["systemctl", "--user", "daemon-reload"], check=True)
    return f"{config.unit_name} disabled and stopped."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage the teleshell systemd user service.")
    parser.add_argument("command", choices=["apply", "enable", "disable", "unit", "status"])
    parser.add_argument("--env", default=None, help="Path to the .env file.")
    args = parser.parse_args(argv)

    config = build_config(Path(args.env) if args.env else None)
    if args.command == "enable":
        config.autorun = True
    elif args.command == "disable":
        config.autorun = False

    if args.command in {"apply", "enable", "disable"}:
        print(apply_autorun(config))
        return 0

    if args.command == "unit":
        print(service_unit_content(config), end="")
        return 0

    return subprocess.run(["systemctl", "--user", "status", config.unit_name], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
