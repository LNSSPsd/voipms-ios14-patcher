#!/bin/sh
# Build libvoipshim.dylib (arm64, iOS 14.0) with the theos toolchain.
#   usage: src/build-shim.sh <outdir>   env: THEOS (default ~/theos), SDK,
#          VOIPSHIM_LOG=1 for Documents/voipshim.log diagnostics (default off)
#   shim.S   - iOS 16 runtime entry points (objc_retain_xN, ...) bound by import
#   compat.m - add-if-missing fallbacks for iOS 15/16 ObjC methods
#   compat_cxx.mm - C++ exception diagnostics (__cxa_throw / set_terminate hooks)
set -e
OUT="$(mkdir -p "${1:?usage: build-shim.sh <outdir>}" && cd "$1" && pwd)"
THEOS="${THEOS:-$HOME/theos}"
T="$THEOS/toolchain/linux/iphone/bin"
SDK="${SDK:-$THEOS/sdks/iPhoneOS14.5.sdk}"
cd "$(dirname "$0")"
$T/clang -target arm64-apple-ios14.0 -isysroot "$SDK" -dynamiclib -fobjc-arc -O2 \
    -DVOIPSHIM_LOG="${VOIPSHIM_LOG:-0}" \
    -install_name @rpath/libvoipshim.dylib \
    -o "$OUT/libvoipshim.dylib" shim.S compat.m compat_cxx.mm \
    -lobjc -lsqlite3 -lc++ -framework Foundation
echo "built $OUT/libvoipshim.dylib (VOIPSHIM_LOG=${VOIPSHIM_LOG:-0})"
