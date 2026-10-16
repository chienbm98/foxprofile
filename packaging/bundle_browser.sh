#!/usr/bin/env bash
# Unpack a Camoufox release zip into the app's browser/ dir with the version.json camoufox
# reads (foxprofile_app.use_bundled_browser points camoufox at it).
# Usage: bundle_browser.sh camoufox-156.0.1-beta.36-fp1-mac.arm64.zip <dest>
set -euo pipefail
ZIP=$1 DEST=$2
NAME=$(basename "$ZIP" .zip)            # camoufox-156.0.1-beta.36-fp1-mac.arm64
VERSION=$(cut -d- -f2 <<<"$NAME")       # 156.0.1
BUILD=$(cut -d- -f3 <<<"$NAME")         # beta.36
rm -rf "$DEST" && mkdir -p "$DEST"
unzip -q "$ZIP" -d "$DEST"
SHA=$(python -c "import hashlib,sys;print(hashlib.file_digest(open(sys.argv[1],'rb'),'sha256').hexdigest())" "$ZIP")
printf '{"version":"%s","build":"%s","prerelease":false,"sha256":"%s","source":"%s","interface":1}\n' \
  "$VERSION" "$BUILD" "$SHA" "$NAME" > "$DEST/version.json"
du -sh "$DEST"
