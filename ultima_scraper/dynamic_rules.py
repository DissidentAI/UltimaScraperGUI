"""OnlyFans request-signing rules ("dynamic rules").

Every OnlyFans API request must be signed with values (static_param, checksum
indexes, app token...) that OnlyFans rotates regularly. The library downloads
them from `settings.dynamic_rules_link`, whose default still points to the
original author's repository, which stopped being updated in 2023: OnlyFans
then answers every request with 401 "Please refresh the page" and logging in
fails even with valid cookies.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson

# Maintained fork, same JSON schema as the one the library expects.
DEFAULT_RULES_URL = (
    "https://raw.githubusercontent.com/DATAHOARDERS/dynamic-rules/main/onlyfans.json"
)
# Defaults written by older versions; they are replaced automatically.
OUTDATED_RULES_URLS = {
    "",
    "https://raw.githubusercontent.com/DIGITALCRIMINALS/dynamic-rules/main/onlyfans.json",
}


def resolve(url: str | None) -> str:
    url = (url or "").strip()
    return DEFAULT_RULES_URL if url in OUTDATED_RULES_URLS else url


def fix_config(config: Any) -> bool:
    """Update an in-memory Config object. Returns True when it was changed."""
    settings = config.settings
    new_url = resolve(settings.dynamic_rules_link)
    changed = new_url != settings.dynamic_rules_link
    settings.dynamic_rules_link = new_url
    return changed


def fix_config_file(config_path: Path) -> bool:
    """Update config.json on disk. Returns True when it was changed."""
    if not config_path.exists():
        return False
    data: dict[str, Any] = orjson.loads(config_path.read_bytes() or b"{}")
    settings = data.get("settings")
    if not isinstance(settings, dict):
        return False
    new_url = resolve(settings.get("dynamic_rules_link"))
    if new_url == settings.get("dynamic_rules_link"):
        return False
    settings["dynamic_rules_link"] = new_url
    config_path.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2))
    return True
