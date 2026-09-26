# voipms-ios14-patcher

**WARNING: AI Slop, works on my phone though**

**as usual, supposed to work only on Linux, not verified on Mac OS**

Patches the **voip.ms Softphone** iOS app (which requires iOS 16) so it runs on **iOS 14**
via [TrollStore](https://github.com/opa334/TrollStore), with push notifications for
incoming calls (PushKit) and the native call UI (CallKit) working, including when the app
is killed.

This repo contains only the patcher: build scripts, a small runtime shim, and Mach-O
tooling. **It contains no binaries.**
You supply the app and an iOS dyld shared cache yourself.

Not affiliated with voip.ms or Acrobits. Use it with an app and account you're entitled to.

## Tested

| | |
|---|---|
| App | voip.ms Softphone `ms.voip.softphone.ios` **0.0.6** (build 1748909285), `MinimumOSVersion` 16.0, Xcode 16.2 / iOS 18.2 SDK |
| iOS | **14.3** (18C66), arm64e (A12+) iPhone, TrollStore |
| Host | Linux (Arch), Python 3.14, [theos](https://theos.dev) with its Linux iOS toolchain (clang 11.1, ldid), theos `iPhoneOS14.5.sdk`, theos `swift-5.8` toolchain (for the Swift Concurrency back-deploy runtime), `dyldextractor` 2.2.2 |

Working on the test device: login and provisioning, incoming calls with the app killed
(PushKit), shown as CallKit calls.

Other app versions: the patcher refuses anything that isn't `ms.voip.softphone.ios` and
warns if the version isn't 0.0.6. The fixes are derived from the binaries at build time,
so a nearby version *may* work, but runtime fallbacks (`src/compat.m`) are version-specific.
Other iOS 14.x versions: build against that version's own dyld cache; untested.

## Requirements

- An iPhone on iOS 14.x with TrollStore installed.
- A Linux host with:
  - `python3` (with `venv`), `unzip`
  - theos + its Linux toolchain at `$THEOS` (default `~/theos`):
    `toolchain/linux/iphone/bin/{clang,ldid}`, `sdks/iPhoneOS14.5.sdk`, and
    `toolchain/swift-5.8/linux/iphone/lib/swift-5.5/iphoneos/libswift_Concurrency.dylib`
  - [apfs-fuse](https://github.com/sgan81/apfs-fuse) to read the iOS root filesystem
- ~12 GB free disk for the IPSW and its root filesystem (deletable afterwards).

`build.sh` creates a Python venv with `dyldextractor` on first run (set `DYLDEX` to use your own).

## 1. Get a decrypted IPA

App Store IPAs are encrypted. You need a **decrypted** IPA of the app version above, from
your own download, e.g. via TrollDecrypt

Check: `cryptid 0` in the main binary (`otool -l` / `llvm-objdump --macho --private-headers`).

## 2. Get the dyld shared cache for your iOS version

The patcher resolves every import against the real system libraries of your target iOS,
so it needs that version's `dyld_shared_cache_arm64e`.

1. Download the IPSW for **your device model and iOS version** from Apple (ipsw.me lists
   the Apple download links).
2. Unzip it and find the largest `.dmg` (the root filesystem):
   ```sh
   unzip -l iPhone*.ipsw | sort -k1 -n | tail -3
   unzip iPhone*.ipsw 038-XXXXX-XXX.dmg
   ```
3. Mount it read-only and copy the cache:
   ```sh
   mkdir -p rootfs && apfs-fuse -o ro 038-XXXXX-XXX.dmg rootfs
   cp rootfs/root/System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64e .
   fusermount -u rootfs
   ```
   (Depending on the apfs-fuse version the volume may be at `rootfs/` instead of `rootfs/root/`.)

A12 and newer use `dyld_shared_cache_arm64e`. Older devices (`..._arm64`) are untested.

## 3. Build

```sh
./build.sh path/to/decrypted.ipa path/to/dyld_shared_cache_arm64e [out.tipa]
```

This builds the shim (`src/`), patches the app (`tools/patch.py`), and runs an independent
offline load check against your cache (`tools/verify.py`). Every image must print `ok`:

```
ok   Frameworks/AmazonChimeSDK.framework/AmazonChimeSDK: minos 12.0 chains ['classic'], 756 imports, 1 weak-missing
ok   Frameworks/AmazonChimeSDKMedia.framework/AmazonChimeSDKMedia: ...
ok   Frameworks/SoftphoneIntents.framework/SoftphoneIntents: ...
ok   Frameworks/libswift_Concurrency.dylib: ...
ok   Frameworks/libvoipshim.dylib: ...
ok   VoIP_ms Softphone: minos 14.0 chains [2], 1976 imports, 1 weak-missing
```

The first run extracts the needed system libraries from the cache into `work/` and takes a
few minutes. Environment overrides: `WORK`, `THEOS`, `THEOS_BIN`, `SDK`, `CONCURRENCY`, `DYLDEX`.

For a diagnostic build (see Troubleshooting), add `VOIPSHIM_LOG=1`:

```sh
VOIPSHIM_LOG=1 ./build.sh path/to/decrypted.ipa path/to/dyld_shared_cache_arm64e debug.tipa
```

## 4. Install

1. If the App Store version is installed, delete it (same bundle ID).
2. Copy the `.tipa` to the phone and open it with TrollStore → Install.
3. Launch, allow microphone and notifications, log in.

For full-screen incoming calls while the phone is unlocked, set **Settings → Phone →
Incoming Calls → Full Screen** (iOS 14 defaults to a compact banner; locked phones always
get full screen).

Test the important part: swipe the app away, lock the phone, call yourself. It should ring
as a normal call. Repeat over a day or so — iOS stops delivering VoIP pushes to apps that
fail to report incoming calls, so an intermittent failure matters.

## Troubleshooting

Rebuild with `VOIPSHIM_LOG=1`. The shim then writes `voipshim.log` to the app's Documents
folder: **Files → On My iPhone → VoIP.ms Softphone**. iOS 14 crash reports don't include
exception reasons; this log does. Normal builds have no logging and no exception hooks.

| Log line | Meaning |
|---|---|
| `UNRECOGNIZED -[Class selector]` + backtrace | app called a method this iOS doesn't have — needs a fallback in `src/compat.m` |
| `UNCAUGHT …` | uncaught Objective-C exception |
| `TERMINATE type: message` + `thrown at` / `terminate at` | exception ended in `std::terminate`. Frames are `image+0xoffset`; main-binary addresses = `0x100000000 + offset` |
| `MISSING iOS 15+ function called` | a shimmed function that can't be emulated was reached |

Crash reports: Settings → Privacy → Analytics & Improvements → Analytics Data, or a crash
reporter such as Cr4shed.

`verify.py` failures:

- `unresolved <dylib> <symbol>` — import not in your iOS version's libraries. Add it to the
  shim, or extend the retarget rules in `tools/patch.py`.
- `weak-lookup only` — an import iOS 14's dyld would leave null.
- `LINKEDIT: …` — layout iOS 14's dyld would reject.

See [NOTES.md](NOTES.md) for everything the patcher changes and why.

## Layout

| | |
|---|---|
| `build.sh` | shim → patch → verify |
| `src/shim.S` | iOS 16 runtime entry points (`objc_retain_xN`, …) and StoreKit 2 stubs |
| `src/compat.m` | add-if-missing fallbacks for iOS 15/16 methods, nib class stub, carrier-info hiding, diagnostics log |
| `src/compat_cxx.mm` | C++ exception diagnostics (`__cxa_throw` / `std::set_terminate` hooks) |
| `src/build-shim.sh` | builds `libvoipshim.dylib` (arm64, iOS 14.0) |
| `tools/machotool.py` | Mach-O, chained-fixup, bind-opcode, export-trie helpers; dyld-cache export resolver |
| `tools/patch.py` | the patcher |
| `tools/verify.py` | independent offline load check against the dyld cache |

## License

[CC0 1.0](LICENSE) — public domain dedication, applies to everything in this repository.
