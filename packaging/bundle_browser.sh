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
# The app only spoofs the OS it runs on (os_type must equal HOST_OS), so faces other OSes read
# are dead weight (~0.6 GB on macOS, ~1 GB on Windows). Unknown files are kept.
case $NAME in *-mac.*) OS=M ;; *-win.*) OS=W ;; *) OS=L ;; esac
python - "$OS" "$(dirname "$0")/font_groups.tsv" "$DEST" <<'PY'
import pathlib, sys
os_, manifest, dest = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
groups = dict(reversed(l.split("\t")) for l in open(manifest, encoding="utf-8").read().splitlines() if not l.startswith("#"))
(fonts,) = [d for d in dest.rglob("fonts") if d.is_dir() and d.parent.name != "fonts"]
dropped = [f for f in fonts.iterdir() if f.name in groups and os_ not in groups[f.name]]
for f in dropped:
    f.unlink()
print(f"fonts: dropped {len(dropped)} faces other OSes read, kept {len(list(fonts.iterdir()))}")
PY
SHA=$(python -c "import hashlib,sys;print(hashlib.file_digest(open(sys.argv[1],'rb'),'sha256').hexdigest())" "$ZIP")
printf '{"version":"%s","build":"%s","prerelease":false,"sha256":"%s","source":"%s","interface":1}\n' \
  "$VERSION" "$BUILD" "$SHA" "$NAME" > "$DEST/version.json"
du -sh "$DEST"
