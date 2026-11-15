#!/bin/bash
# Double-click to start FoxProfile (macOS)
cd "$(dirname "$0")" || exit 1
source .venv/bin/activate
exec python -m src.main
