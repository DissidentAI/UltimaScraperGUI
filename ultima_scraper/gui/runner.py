"""Runs one scraping session on a background thread with its own event loop."""

from __future__ import annotations

import asyncio
import threading
import traceback
from argparse import Namespace
from dataclasses import dataclass, field
from typing import Any

from ultima_scraper.gui.bridge import UiBridge
from ultima_scraper.gui.config_store import CONTENT_TYPES, MEDIA_TYPES


@dataclass
class RunOptions:
    sites: list[str]
    all_models: bool = False
    contents: list[str] = field(default_factory=lambda: list(CONTENT_TYPES))
    medias: list[str] = field(default_factory=lambda: list(MEDIA_TYPES))
    verbose: bool = False


def _choice(selected: list[str], available: tuple[str, ...]) -> bool | list[str]:
    """True means "all", which is what the libraries expect for auto choices."""
    return True if set(available) <= set(selected) else list(selected)


def apply_run_options(config: Any, options: RunOptions) -> None:
    """Translate GUI choices into the auto_* settings so no terminal prompt appears."""
    for site in options.sites:
        site_config = getattr(config.supported, site.lower(), None)
        if not site_config:
            continue
        settings = site_config.settings
        if not settings.auto_profile_choice:
            settings.auto_profile_choice = True
        settings.auto_model_choice = True if options.all_models else False
        settings.auto_api_choice = _choice(options.contents, CONTENT_TYPES)
        settings.auto_media_choice = _choice(options.medias, MEDIA_TYPES)


class ScraperRunner(threading.Thread):
    def __init__(self, bridge: UiBridge, options: RunOptions) -> None:
        super().__init__(name="UltimaScraperRunner", daemon=True)
        self.bridge = bridge
        self.options = options
        self.loop: asyncio.AbstractEventLoop | None = None
        self.task: asyncio.Task[Any] | None = None
        self.stopping = False

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        ok = False
        try:
            self.task = loop.create_task(self._main())
            loop.run_until_complete(self.task)
            ok = True
        except asyncio.CancelledError:
            self.bridge.log("\n[Arrêté] Session interrompue par l'utilisateur.\n")
        except Exception:
            self.bridge.log("\n[Erreur]\n" + traceback.format_exc())
        finally:
            try:
                pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                for pending_task in pending:
                    pending_task.cancel()
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()
            self.bridge.events.put(("finished", ok))

    def stop(self) -> None:
        self.stopping = True
        if self.loop and self.task and not self.task.done():
            self.loop.call_soon_threadsafe(self.task.cancel)

    async def _main(self) -> None:
        import ultima_scraper_api.apis.api_helper as api_helper
        import ultima_scraper_api.helpers.main_helper as main_helper
        from ultima_scraper_collection.managers.filesystem_manager import (
            FilesystemManager,
        )

        from tests import main_test
        from ultima_scraper.ultima_scraper import UltimaScraper

        api_helper.parsed_args = Namespace(verbose=self.options.verbose)
        main_test.check_start_up()
        fsm = FilesystemManager()
        config, _updated = main_helper.get_config(
            fsm.settings_directory.joinpath("config.json")
        )
        apply_run_options(config, self.options)

        scraper = UltimaScraper(config.settings)
        failed: list[str] = []
        try:
            for site_name in self.options.sites:
                self.bridge.status(f"{site_name} : connexion et récupération…")
                api = await scraper.start(config, site_name)
                if not api.auths:
                    failed.append(site_name)
            if failed:
                self.bridge.log(
                    f"\n[Échec] Aucun compte {', '.join(failed)} n'a pu se connecter, "
                    "rien n'a été téléchargé. Voir la raison ci-dessus ; en général il faut "
                    "recopier les identifiants (onglet Comptes > Coller depuis cURL) "
                    "depuis une session ouverte dans le navigateur.\n"
                )
            else:
                self.bridge.log("\n[Terminé] Session terminée.\n")
        finally:
            for datascraper in scraper.datascraper_manager.datascrapers:
                try:
                    await datascraper.api.close_pools()
                except Exception:
                    pass
