#!/usr/bin/env sh
# One-command installation of the UltimaScraper GUI on Linux/macOS.
# Python 3.11 and every dependency are downloaded into this folder (.tools/.venv):
# nothing is installed system-wide and PATH is never modified.
set -eu

ROOT=$(cd "$(dirname "$0")" && pwd)
TOOLS="$ROOT/.tools"
UV="$TOOLS/uv/uv"
export UV_PYTHON_INSTALL_DIR="$TOOLS/python"
export UV_CACHE_DIR="$TOOLS/cache"

if [ ! -x "$UV" ]; then
    echo "==> Téléchargement de uv (gestionnaire Python autonome)"
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL="$TOOLS/uv" UV_NO_MODIFY_PATH=1 sh
    else
        wget -qO- https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL="$TOOLS/uv" UV_NO_MODIFY_PATH=1 sh
    fi
fi

echo "==> Préparation de Python 3.11 et de l'environnement (.venv)"
if [ ! -x "$ROOT/.venv/bin/python" ]; then
    "$UV" venv --python 3.11 --python-preference only-managed "$ROOT/.venv"
fi

echo "==> Installation des dépendances"
"$UV" pip install --python "$ROOT/.venv/bin/python" --no-deps -r "$ROOT/requirements.txt"

LAUNCHER="$ROOT/UltimaScraper.sh"
cat > "$LAUNCHER" <<LAUNCH
#!/usr/bin/env sh
cd "$ROOT" && exec "$ROOT/.venv/bin/python" "$ROOT/ultima_scraper_gui.py" "\$@"
LAUNCH
chmod +x "$LAUNCHER"

if [ "$(uname -s)" = "Linux" ] && [ -d "$HOME/.local/share" ]; then
    mkdir -p "$HOME/.local/share/applications"
    cat > "$HOME/.local/share/applications/ultimascraper.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=UltimaScraper
Exec="$LAUNCHER"
Path=$ROOT
Icon=$ROOT/ultima_scraper/docs/assets/img/64255399-96a86700-cf21-11e9-8c62-87a483f33701.png
Terminal=false
Categories=Network;
DESKTOP
fi

echo ""
echo "Installation terminée. Lancez UltimaScraper avec : $LAUNCHER"
