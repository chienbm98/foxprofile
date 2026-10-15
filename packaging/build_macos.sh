#!/usr/bin/env bash
# Build dist/FoxProfile.app (arm64 on Apple Silicon) and dist/FoxProfile-<version>.dmg.
# Usage (repo root, venv active):  pip install -r requirements.lock -r requirements-build.txt
#                                  bash packaging/build_macos.sh
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
ICONSET=packaging/.gen/FoxProfile.iconset
rm -rf build dist packaging/.gen && mkdir -p "$ICONSET"
for s in 16 32 128 256; do
  sips -z $s $s src/assets/icon.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s * 2)) $((s * 2)) src/assets/icon.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o packaging/.gen/FoxProfile.icns

bash packaging/pack.sh --icon packaging/.gen/FoxProfile.icns --bundle-id com.foxprofile.app

codesign --force --deep -s - dist/FoxProfile.app   # ad-hoc: not notarized, first open needs right-click > Open
codesign --verify --deep --strict dist/FoxProfile.app

STAGE=build/dmg
mkdir -p "$STAGE" && cp -R dist/FoxProfile.app "$STAGE/" && ln -s /Applications "$STAGE/Applications"
hdiutil create -volname FoxProfile -srcfolder "$STAGE" -ov -format UDZO "dist/FoxProfile-$VERSION.dmg"
du -sh dist/FoxProfile.app "dist/FoxProfile-$VERSION.dmg"
