#!/usr/bin/env bash
# Shared `flet pack` invocation (macOS + Windows/git-bash). Extra args are passed to flet pack.
set -euo pipefail
cd "$(dirname "$0")/.."

SEP=":"; [[ "${OS:-}" == "Windows_NT" ]] && SEP=";"
VERSION=$(python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")

flet pack packaging/foxprofile_app.py -y -n FoxProfile --product-name FoxProfile \
  --product-version "$VERSION" --copyright "MIT License" \
  --add-data "src/assets${SEP}src/assets" --add-data "src/web${SEP}src/web" \
  "$@" -- \
  --onedir --paths . \
  --collect-data camoufox --collect-data fpgen --collect-data language_tags --collect-all playwright \
  --collect-submodules uvicorn \
  --hidden-import src.services.browser.runner --hidden-import src.services.browser.cookie_tool \
  --hidden-import chrome_engine.runner --hidden-import camoufox.__main__
