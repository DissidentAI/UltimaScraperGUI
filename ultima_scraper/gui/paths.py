"""Locations used by the GUI, for source checkouts and PyInstaller builds alike."""

import os
import sys
from pathlib import Path

APP_NAME = "UltimaScraper"
PORTABLE_MARKER = "portable.txt"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_directory() -> Path:
    """Folder holding the executable (frozen) or the repository root (source)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def resource_path(*parts: str) -> Path:
    """Path to a file bundled with the application."""
    base = Path(getattr(sys, "_MEIPASS", app_directory()))
    return base.joinpath(*parts)


def resolve_data_directory() -> Path:
    """Folder that will contain __settings__ and __user_data__.

    - ULTIMA_DATA_DIR, when set, always wins.
    - Running from source keeps the historical layout (repository root).
    - A frozen build next to a portable.txt marker (or an existing
      __settings__ folder) is portable and keeps its data beside the exe.
    - Otherwise (installed build) data lives in ~/UltimaScraper so it survives
      updates/uninstalls and never needs admin rights.
    """
    env_directory = os.environ.get("ULTIMA_DATA_DIR")
    if env_directory:
        return Path(env_directory).expanduser().resolve()
    app_dir = app_directory()
    if not is_frozen():
        return app_dir
    if (
        app_dir.joinpath(PORTABLE_MARKER).exists()
        or app_dir.joinpath("__settings__").exists()
    ):
        return app_dir
    return Path.home().joinpath(APP_NAME)


def prepare_data_directory() -> Path:
    """Create the data folder and make it the working directory.

    The scraper libraries resolve "__settings__" and "__user_data__" relative to
    the current directory, so everything else depends on this chdir.
    """
    data_directory = resolve_data_directory()
    data_directory.mkdir(parents=True, exist_ok=True)
    os.chdir(data_directory)
    return data_directory


def settings_directory() -> Path:
    return Path.cwd().joinpath("__settings__")


def profiles_directory() -> Path:
    return Path.cwd().joinpath("__user_data__", "profiles")


def open_in_file_manager(path: Path) -> None:
    path = Path(path)
    if path.is_dir() or not path.suffix:
        path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        import subprocess

        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, str(path)])
