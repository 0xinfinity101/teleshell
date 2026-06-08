import os
from pathlib import Path


DEFAULT_USER_BIN_DIRS = (
    ".opencode/bin",
    ".local/bin",
    ".bun/bin",
    ".npm-global/bin",
    ".cargo/bin",
)


def split_path(value: str | None) -> list[str]:
    if not value:
        return []
    return [item for item in value.split(os.pathsep) if item]


def unique_paths(paths: list[str]) -> list[str]:
    seen = set()
    result = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            result.append(path)
    return result


def build_command_path(
    base_path: str | None,
    extra_paths: str | None = None,
    home: Path | None = None,
) -> str:
    home = home or Path.home()
    user_bins = [str(home / relative) for relative in DEFAULT_USER_BIN_DIRS]
    paths = [
        *split_path(extra_paths),
        *user_bins,
        *split_path(base_path),
    ]
    return os.pathsep.join(unique_paths(paths))


def build_command_env(base_env: dict[str, str] | None = None, home: Path | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)
    env["PATH"] = build_command_path(
        env.get("PATH"),
        extra_paths=env.get("COMMAND_EXTRA_PATHS"),
        home=home,
    )
    return env
