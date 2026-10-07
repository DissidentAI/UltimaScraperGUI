"""`UltimaScraper --self-test`: checks that a (frozen) build has everything it needs.

Used by CI on the built executable; also handy to diagnose a broken install.
"""

from __future__ import annotations

import sys
import tempfile
import threading
import traceback
from pathlib import Path


def _run_migrations(database_path: Path, errors: list[str]) -> None:
    try:
        from ultima_scraper_collection.managers.database_manager.connections.sqlite.sqlite_database import (
            SqliteDatabase,
        )

        database = SqliteDatabase().init_db(database_path)
        if not database.migration_directory.joinpath("alembic.ini").exists():
            errors.append(f"missing alembic.ini in {database.migration_directory}")
            return
        database.run_migrations()
        database.session.remove()
        database.session_factory.kw["bind"].dispose()
    except Exception:
        errors.append(traceback.format_exc())


def run_self_test() -> int:
    lines: list[str] = []
    errors: list[str] = []
    try:
        import ultima_scraper.ultima_scraper  # noqa: F401
        import ultima_scraper_api.helpers.main_helper as main_helper
        from tests import main_test
        from ultima_scraper.gui import config_store

        main_test.check_start_up()
        config, _updated = main_helper.get_config(config_store.config_path())
        lines.append(f"config ok: {sorted(config.supported.__dict__)}")

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            # run_migrations retries forever on failure, hence the thread + timeout.
            worker = threading.Thread(
                target=_run_migrations,
                args=(Path(tmp, "user_data.db"), errors),
                daemon=True,
            )
            worker.start()
            worker.join(120)
            if worker.is_alive():
                errors.append("database migrations did not finish (see output above)")
            elif not errors:
                lines.append("database migrations ok")
    except Exception:
        errors.append(traceback.format_exc())

    lines.extend(f"ERROR: {error}" for error in errors)
    lines.append("SELF-TEST " + ("FAILED" if errors else "PASSED"))
    report = "\n".join(lines) + "\n"
    Path("selftest.log").write_text(report, encoding="utf-8")
    if sys.__stdout__ is not None:
        sys.__stdout__.write(report)
    return 1 if errors else 0
