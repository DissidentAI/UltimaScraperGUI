"""Reading and writing config.json, auth.json profiles and GUI preferences."""

from __future__ import annotations

import json
import re
import shlex
import shutil
from pathlib import Path
from typing import Any

from ultima_scraper.gui import paths

SITES = ("OnlyFans", "Fansly")
CONTENT_TYPES = ("Stories", "Posts", "Messages", "Chats", "Highlights", "MassMessages")
MEDIA_TYPES = ("Images", "Videos", "Audios", "Texts")

# Fields shown in the Accounts tab, per site: (json key, label, multiline)
AUTH_FIELDS: dict[str, list[tuple[str, str, bool]]] = {
    "OnlyFans": [
        ("cookie", "Cookie", True),
        ("x_bc", "x-bc", False),
        ("user_agent", "User-Agent", False),
    ],
    "Fansly": [
        ("authorization", "Authorization", True),
        ("user_agent", "User-Agent", False),
    ],
}


def read_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists() and path.stat().st_size:
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------- config.json
def config_path() -> Path:
    return paths.settings_directory().joinpath("config.json")


def ensure_config() -> dict[str, Any]:
    """Create/upgrade config.json with the library defaults and return it."""
    import ultima_scraper_api.helpers.main_helper as main_helper

    from ultima_scraper import dynamic_rules

    main_helper.get_config(config_path())
    dynamic_rules.fix_config_file(config_path())
    return read_json(config_path())


def site_settings(config: dict[str, Any], site: str) -> dict[str, Any]:
    return (
        config.setdefault("supported", {})
        .setdefault(site.lower(), {})
        .setdefault("settings", {})
    )


# ------------------------------------------------------------------ profiles
def site_profiles_directory(site: str) -> Path:
    return paths.profiles_directory().joinpath(site)


def list_profiles(site: str) -> list[str]:
    directory = site_profiles_directory(site)
    if not directory.exists():
        return []
    return sorted(
        child.name
        for child in directory.iterdir()
        if child.is_dir() and child.joinpath("auth.json").exists()
    )


def load_profile(site: str, name: str) -> dict[str, Any]:
    data = read_json(site_profiles_directory(site).joinpath(name, "auth.json"))
    return data.get("auth", {})


def save_profile(site: str, name: str, values: dict[str, Any]) -> Path:
    path = site_profiles_directory(site).joinpath(name, "auth.json")
    data = read_json(path)
    auth = data.get("auth") or default_auth(site)
    auth.update(values)
    auth["username"] = name
    data["auth"] = auth
    write_json(path, data)
    return path


def delete_profile(site: str, name: str) -> None:
    directory = site_profiles_directory(site).joinpath(name)
    if directory.exists():
        shutil.rmtree(directory)


def default_auth(site: str) -> dict[str, Any]:
    if site == "Fansly":
        from ultima_scraper_api.apis.fansly.classes.extras import AuthDetails
    else:
        from ultima_scraper_api.apis.onlyfans.classes.extras import AuthDetails
    return AuthDetails().export()


def valid_profile_name(name: str) -> bool:
    return (
        bool(re.fullmatch(r"[A-Za-z0-9_.\- ]{1,64}", name)) and name.strip(" .") == name
    )


# ------------------------------------------------------------- GUI settings
def gui_settings_path() -> Path:
    return paths.settings_directory().joinpath("gui.json")


def load_gui_settings() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "sites": ["OnlyFans"],
        "models": "ask",
        "contents": list(CONTENT_TYPES),
        "medias": list(MEDIA_TYPES),
    }
    defaults.update(read_json(gui_settings_path()))
    return defaults


def save_gui_settings(values: dict[str, Any]) -> None:
    write_json(gui_settings_path(), values)


# ------------------------------------------------------------- cURL parsing
def parse_curl(text: str) -> dict[str, str]:
    """Extract headers from a browser "Copy as cURL" (bash or cmd flavour).

    Returns lowercase header names, e.g. {"cookie": ..., "x-bc": ..., "user-agent": ...}.
    """
    text = text.strip()
    if not text:
        return {}
    if "^" in text:
        # Windows "Copy as cURL (cmd)": ^ escapes every special character and
        # ends continued lines.
        text = re.sub(r"\^\r?\n", " ", text)
        text = re.sub(r"\^(.)", r"\1", text)
    text = re.sub(r"\\\r?\n", " ", text)
    try:
        tokens = shlex.split(text, posix=True)
    except ValueError:
        tokens = text.split()
    headers: dict[str, str] = {}
    iterator = iter(range(len(tokens)))
    for index in iterator:
        token = tokens[index]
        value: str | None = None
        if token in ("-H", "--header") and index + 1 < len(tokens):
            value = tokens[index + 1]
            next(iterator, None)
            if ":" in value:
                name, _, header_value = value.partition(":")
                headers[name.strip().lower()] = header_value.strip()
        elif token in ("-b", "--cookie") and index + 1 < len(tokens):
            headers["cookie"] = tokens[index + 1].strip()
            next(iterator, None)
        elif token in ("-A", "--user-agent") and index + 1 < len(tokens):
            headers["user-agent"] = tokens[index + 1].strip()
            next(iterator, None)
    if not headers:
        # Fallback: raw "Name: value" header lines pasted from the devtools.
        for line in text.splitlines():
            if ":" in line:
                name, _, header_value = line.partition(":")
                if name.strip() and " " not in name.strip():
                    headers[name.strip().lower()] = header_value.strip()
    return headers


def auth_values_from_headers(site: str, headers: dict[str, str]) -> dict[str, str]:
    values: dict[str, str] = {}
    if headers.get("user-agent"):
        values["user_agent"] = headers["user-agent"]
    if site == "OnlyFans":
        if headers.get("cookie"):
            values["cookie"] = headers["cookie"]
        if headers.get("x-bc"):
            values["x_bc"] = headers["x-bc"]
    elif headers.get("authorization"):
        values["authorization"] = headers["authorization"]
    return values
