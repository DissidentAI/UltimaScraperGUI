# -*- mode: python ; coding: utf-8 -*-
# Builds the UltimaScraper GUI executable.
#
#   pyinstaller --noconfirm pyinstaller.spec                 -> dist/UltimaScraper/ (folder, fast start-up, used by the installer)
#   ULTIMA_ONEFILE=1 pyinstaller --noconfirm pyinstaller.spec -> dist/UltimaScraper.exe (single portable file)
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

MAJOR, MINOR, PATCH = 8, 0, 0
NAME = "UltimaScraper"
ONEFILE = os.environ.get("ULTIMA_ONEFILE", "") not in ("", "0", "false")
ICON = os.path.join("ultima_scraper", "docs", "assets", "img", "icon.ico")

datas = [(ICON, os.path.join("ultima_scraper", "docs", "assets", "img"))]
binaries = []
hiddenimports = ["logging.config", "sqlite3"] + collect_submodules("ultima_scraper")

# The scraper libraries load alembic migrations, user-agent data files and
# dynamically imported modules at runtime: bundle them entirely, sources included.
for package in (
    "ultima_scraper_api",
    "ultima_scraper_collection",
    "ultima_scraper_renamer",
    "user_agent",
    "pywidevine",
):
    package_datas, package_binaries, package_hiddenimports = collect_all(package, include_py_files=True)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

# alembic.testing needs pytest and is never used.
hiddenimports += collect_submodules("alembic", filter=lambda name: not name.startswith("alembic.testing"))
datas += collect_data_files("alembic")

a = Analysis(
    ["ultima_scraper_gui.py"],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Declared by the libraries but never used at runtime.
    excludes=["mypy", "psycopg2", "websockets", "matplotlib", "numpy", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

version = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    version = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=(MAJOR, MINOR, PATCH, 0),
            prodvers=(MAJOR, MINOR, PATCH, 0),
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("FileDescription", "Ultima Scraper"),
                            StringStruct("FileVersion", f"{MAJOR}.{MINOR}.{PATCH}.0"),
                            StringStruct("LegalCopyright", "GPLv3"),
                            StringStruct("ProductName", "Ultima Scraper"),
                            StringStruct("ProductVersion", f"{MAJOR}.{MINOR}.{PATCH}"),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )

exe_options = dict(
    name=NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI application: no terminal window
    icon=ICON,
    version=version,
)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], runtime_tmpdir=None, **exe_options)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **exe_options)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=NAME)
