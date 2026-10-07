"""Thread-safe plumbing between the scraper thread and the Tk main loop.

The scraper libraries were written for a terminal: they print() progress and
call input() when they need an answer. The GUI redirects stdout/stderr into a
queue and turns input()/option prompts into dialogs answered on the Tk thread.
"""

from __future__ import annotations

import builtins
import io
import queue
import threading
from typing import Any, Callable


class UiBridge:
    def __init__(self) -> None:
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.last_line = ""
        # Used when input() is called on the Tk thread (e.g. during start-up).
        self.main_thread_input: Callable[[str], str | None] | None = None

    def log(self, text: str) -> None:
        if not text:
            return
        stripped = [
            line for line in text.replace("\r", "\n").splitlines() if line.strip()
        ]
        if stripped:
            self.last_line = stripped[-1].strip()
        self.events.put(("log", text))

    def status(self, text: str) -> None:
        self.events.put(("status", text))

    def request(self, kind: str, **payload: Any) -> Any:
        """Ask the Tk thread something and block until it answers."""
        if threading.current_thread() is threading.main_thread():
            raise RuntimeError("UiBridge.request must not be called from the Tk thread")
        reply: queue.Queue[Any] = queue.Queue(maxsize=1)
        self.events.put(("request", (kind, payload, reply)))
        return reply.get()

    def ask_input(self, prompt: str = "") -> str:
        prompt = str(prompt).strip() or self.last_line or "Saisie requise"
        if threading.current_thread() is threading.main_thread():
            answer = self.main_thread_input(prompt) if self.main_thread_input else None
        else:
            answer = self.request("input", prompt=prompt)
        return "" if answer is None else str(answer)

    def ask_choice(self, title: str, options_type: str, items: list[str]) -> list[str]:
        return list(
            self.request("choice", title=title, options_type=options_type, items=items)
            or []
        )


class BridgeStream(io.TextIOBase):
    """File-like object that forwards writes to the GUI log (and the terminal, if any)."""

    def __init__(self, bridge: UiBridge, original: Any = None) -> None:
        self.bridge = bridge
        self.original = original

    def write(self, text: str) -> int:  # type: ignore[override]
        self.bridge.log(text)
        if self.original is not None:
            try:
                self.original.write(text)
            except Exception:
                pass
        return len(text)

    def flush(self) -> None:
        if self.original is not None:
            try:
                self.original.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        return False

    @property
    def encoding(self) -> str:  # type: ignore[override]
        return "utf-8"


_patched = False


def install_patches(bridge: UiBridge) -> None:
    """Replace the terminal-only interactions of the scraper libraries.

    - input() opens a dialog.
    - prompt_modified() (opens notepad/nano and waits) only logs a message,
      since config/auth files are edited from the GUI.
    - Option prompts (profiles, subscriptions, ...) open a checklist dialog
      when no automatic choice is configured.
    """
    global _patched
    if _patched:
        return
    _patched = True

    builtins.input = lambda prompt="": bridge.ask_input(prompt)  # type: ignore[assignment]

    import ultima_scraper_api.helpers.main_helper as main_helper

    def prompt_modified(message: str, path: Any) -> None:
        bridge.log(
            f"[Info] {path} est prêt. Modifiez-le depuis les onglets Comptes / Paramètres.\n"
        )

    main_helper.prompt_modified = prompt_modified

    from ultima_scraper_collection.managers.option_manager import OptionsFormat

    original_choose_option = OptionsFormat.choose_option

    async def choose_option(self: OptionsFormat) -> list[str]:
        if self.auto_choice:
            return await original_choose_option(self)
        if not self.item_keys:
            # Nothing to choose from (e.g. no authenticated account): don't prompt.
            return []
        titles = {
            "sites": "Choisissez les sites",
            "profiles": "Choisissez les comptes à utiliser",
            "subscriptions": "Choisissez les créateurs à télécharger",
            "contents": "Choisissez les types de contenu",
            "medias": "Choisissez les types de média",
        }
        title = titles.get(self.options_type, f"Choisissez : {self.options_type}")
        keys = [str(key) for key in self.item_keys]
        return bridge.ask_choice(title, self.options_type, keys)

    OptionsFormat.choose_option = choose_option  # type: ignore[assignment]
