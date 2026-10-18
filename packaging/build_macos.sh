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

# The patched Camoufox (canvas noise key, see README) ships inside the app and is launched
# in place: CAMOUFOX_ZIP=path/to/camoufox-<version>-<build>-fp1-mac.arm64.zip
if [[ -n "${CAMOUFOX_ZIP:-}" ]]; then
  bash packaging/bundle_browser.sh "$CAMOUFOX_ZIP" dist/FoxProfile.app/Contents/Resources/browser
fi

# flet pack leaves the version at 0.0.0. LSUIElement: this Python launcher only starts the
# Flet window app (~/.flet/client/.../FoxProfile.app), which has its own Dock icon.
PLIST=dist/FoxProfile.app/Contents/Info.plist
plutil -replace CFBundleShortVersionString -string "$VERSION" "$PLIST"
plutil -replace CFBundleVersion -string "$VERSION" "$PLIST"
plutil -replace LSUIElement -bool true "$PLIST"

codesign --force --deep -s - dist/FoxProfile.app   # ad-hoc: not notarized, first open needs right-click > Open
codesign --verify --deep --strict dist/FoxProfile.app

STAGE=build/dmg
mkdir -p "$STAGE" && cp -R dist/FoxProfile.app "$STAGE/" && ln -s /Applications "$STAGE/Applications"
hdiutil create -volname FoxProfile -srcfolder "$STAGE" -ov -format ULMO "dist/FoxProfile-$VERSION.dmg"
du -sh dist/FoxProfile.app "dist/FoxProfile-$VERSION.dmg"
