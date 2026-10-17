"""Calculate user folders without inspecting or changing the filesystem."""

import ntpath
import posixpath
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePath, PurePosixPath, PureWindowsPath


@dataclass(frozen=True)
class AppDirs:
    data: PurePath
    logs: PurePath
    addons: PurePath
    cache: PurePath


def app_dirs(
    system: str,
    env: Mapping[str, str],
    home: str | PurePath,
    app_name: str,
    *,
    install_dir: str | PurePath | None = None,
) -> AppDirs:
    """Return absolute, normalized paths; optionally exclude an installation tree."""
    platform = system.casefold()
    if platform in {"windows", "win32"}:
        windows = True
    elif platform in {"darwin", "macos", "linux"}:
        windows = False
    else:
        raise ValueError("Unsupported system")
    if (
        not app_name
        or app_name in {".", ".."}
        or app_name != app_name.strip()
        or app_name.endswith(".")
        or any(character in '<>:"/\\|?*' or ord(character) < 32 for character in app_name)
    ):
        raise ValueError("app_name must be a safe single path component")
    stem = app_name.split(".", 1)[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL"} or stem in {
        f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
    }:
        raise ValueError("app_name is a reserved filename")

    path_type = PureWindowsPath if windows else PurePosixPath
    normalize = ntpath.normpath if windows else posixpath.normpath

    def absolute(value: str | PurePath) -> PurePath:
        path = path_type(normalize(str(value)))
        if not path.is_absolute():
            raise ValueError("Paths must be absolute for the requested system")
        return path

    user_home = absolute(home)
    installation = absolute(install_dir) if install_dir is not None else None
    variables = {key.upper() if windows else key: value for key, value in env.items()}

    def root(key: str, fallback: PurePath) -> PurePath:
        value = variables.get(key)
        if not value or not value.strip():
            return fallback
        try:
            return absolute(value)
        except ValueError:
            return fallback

    def safe(preferred: PurePath, fallback: PurePath, *, with_addons: bool = False) -> PurePath:
        def excluded(path: PurePath) -> bool:
            return installation is not None and (
                path.is_relative_to(installation) or (with_addons and (path / "addons").is_relative_to(installation))
            )

        if not excluded(preferred):
            return preferred
        if not excluded(fallback):
            return fallback
        raise ValueError("The user folder would be inside the installation directory")

    if windows:
        # Everything is local, never roaming: the roaming folder may be on a network share or copied at sign-out,
        # where a database's file locks are unreliable. Two computers share a workspace through its synced folder.
        local = user_home / "AppData" / "Local"
        base = root("LOCALAPPDATA", local) / app_name
        data = safe(base / "data", local / app_name / "data", with_addons=True)
        logs = safe(base / "logs", local / app_name / "logs")
        cache = safe(base / "cache", local / app_name / "cache")
    elif platform in {"darwin", "macos"}:
        library = user_home / "Library"
        data = safe(
            library / "Application Support" / app_name, library / "Application Support" / app_name, with_addons=True
        )
        logs = safe(library / "Logs" / app_name, library / "Logs" / app_name)
        cache = safe(library / "Caches" / app_name, library / "Caches" / app_name)
    else:
        data_default = user_home / ".local" / "share" / app_name
        state_default = user_home / ".local" / "state" / app_name / "logs"
        cache_default = user_home / ".cache" / app_name
        data = safe(root("XDG_DATA_HOME", user_home / ".local" / "share") / app_name, data_default, with_addons=True)
        logs = safe(root("XDG_STATE_HOME", user_home / ".local" / "state") / app_name / "logs", state_default)
        cache = safe(root("XDG_CACHE_HOME", user_home / ".cache") / app_name, cache_default)
    return AppDirs(data=data, logs=logs, addons=data / "addons", cache=cache)
