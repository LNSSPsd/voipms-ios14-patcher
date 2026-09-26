#!/bin/sh
# voip.ms Softphone -> iOS 14 TrollStore build: shim -> patch -> offline load check.
#   usage: ./build.sh <decrypted.ipa> <dyld_shared_cache_arm64e> [out.tipa]
#   env:   WORK (default ./work), THEOS (default ~/theos), DYLDEX, CONCURRENCY, SDK,
#          VOIPSHIM_LOG=1 (diagnostic build: Documents/voipshim.log)
set -e
[ $# -ge 2 ] || { sed -n '3,4p' "$0"; exit 2; }
HERE="$(cd "$(dirname "$0")" && pwd)"
IPA="$1"
CACHE="$2"
OUT="${3:-voipms-softphone-ios14.tipa}"
W="${WORK:-$HERE/work}"
mkdir -p "$W"
DYLDEX="${DYLDEX:-$W/venv/bin/dyldex}"
if [ ! -x "$DYLDEX" ]; then
    python3 -m venv "$W/venv"
    # setuptools<81: capstone (dyldextractor dep) still imports pkg_resources
    "$W/venv/bin/pip" install -q dyldextractor 'setuptools<81'
fi
"$HERE/src/build-shim.sh" "$W"
python3 "$HERE/tools/patch.py" "$IPA" "$OUT" "$CACHE" "$DYLDEX" "$W" | grep -v '  weak '
python3 "$HERE/tools/verify.py" "$OUT" "$CACHE" "$DYLDEX" "$W"
