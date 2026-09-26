# Technical notes

What the patcher changes and why. Addresses are for app version 0.0.6 (build 1748909285);
main-binary addresses assume the unslid base `0x100000000`.

The app: `ms.voip.softphone.ios`, built with Xcode 16.2 / iOS 18.2 SDK, `MinimumOSVersion`
16.0. The calling engine is Acrobits `libsoftphone`, statically linked; video/conferencing
comes from bundled `AmazonChimeSDK*` frameworks.

## Constraints

- **Keep PushKit working.** Bundle ID and entitlements (`aps-environment`,
  `application-identifier`, calling/messaging entitlements) are carried over unchanged, so
  the install must go through TrollStore (a plain re-sign can't keep them).
- **Everything is derived from the target's own dyld shared cache at build time**, not
  hardcoded: an import is only touched if it doesn't resolve against that cache.
- **Nothing on disk that 14's dyld doesn't understand.** `tools/verify.py` re-checks every
  loaded image independently, including LINKEDIT layout as iOS 14's dyld validates it.

## Load-time fixes (tools/patch.py)

Main binary and `SoftphoneIntents.framework` use chained fixups (`imports_format` 1,
`pointer_format` 6). Unresolved on 14.3 and the fix:

| Problem | Fix |
|---|---|
| Pointer format 6 (`DYLD_CHAINED_PTR_64_OFFSET`, iOS 15+) | convert to format 2: rebase target += `__TEXT` vmaddr, same bit layout |
| `LC_BUILD_VERSION` minos 16.0, `MinimumOSVersion` 16.0 | 14.0 |
| 123 Swift Foundation overlay symbols bound to `Foundation` (lived in `/usr/lib/swift/libswiftFoundation.dylib` before iOS 15) | add `LC_LOAD_DYLIB`, retarget ordinals |
| `AVFAudio.framework` absent before 14.5 (18 imports) | retarget to AVFoundation, AVFAudio load → weak |
| `libswift_Concurrency.dylib` absent before 15 | bundle the Swift 5.5 back-deployment runtime, `@rpath` + `LC_RPATH /usr/lib/swift` |
| `objc_retain_xN` / `objc_release_xN`, `objc_claimAutoreleasedReturnValue` (iOS 16 runtime) | shim (`src/shim.S`) |
| `sqlite3_changes64`, `swift_stdlib_isStackAllocationSafe` | shim (→ `sqlite3_changes`; → false) |
| Data constants (`SKANErrorDomain`, SKAdNetwork values, `UIApplicationOpenDefaultApplicationsSettingsURLString`) | shim exports NSString constants — weak-null *data* crashes on first read |
| StoreKit 2 `AppStore.deviceVerificationID` | shim returns `Optional<UUID>.none` |
| StoreKit 2 `Transaction` getters | shim logs + aborts (unreachable without a StoreKit 2 transaction) |
| `VNGeneratePersonSegmentationRequest` | left weak (video background blur only) |
| Weak-lookup imports (ordinal −3: `operator new/delete`, `new[]/delete[]`, typeinfo) | retarget to the dylib that exports them (libc++) |
| `UISupportedDevices` (App Store device thinning) | removed from Info.plist |

### ld-prime weak-bind-only imports (AmazonChimeSDK, AmazonChimeSDKMedia)

The Chime frameworks use classic `LC_DYLD_INFO` binds. `operator new/delete` (5 in Media,
2 in SDK) appear **only in the weak-bind table** — no bind, no lazy-bind, `__la_symbol_ptr`
slot 0 on disk. Newer dyld resolves them by weak lookup; iOS 14's dyld2 only coalesces weak
binds when some non-cache image has weak definitions, so the slots stay 0.

Crash signature: `ImageLoaderMachO::doModInitFunctions` → `AmazonChimeSDKMedia` static
initializer building a `std::map` → `operator new` → pc 0, SIGSEGV.

Fix: explicit binds to libc++ appended to the bind stream. Moving the stream has two traps:

- iOS 14 dyld2 enforces **file order** rebase ≤ bind ≤ weak_bind ≤ lazy_bind ≤ export
  (`malformed mach-o image: dyld weak bind info overlaps bind info` is an order check), so
  bind, weak_bind, lazy_bind and export are copied together, in order, to the end.
  Lazy-bind offsets in `__stub_helper` are stream-relative and stay valid.
- `ldid` places the new code signature at the **end of the string table**, so the string
  table is copied after them too, then the frameworks are re-signed.

## Runtime fixes (src/compat.m)

A min-16 build compiles out every `@available` check for APIs ≤ 16.0, so iOS 15/16 methods
are called unguarded. Checks for APIs newer than the deployment target (e.g. 16.4's
`WKWebView.isInspectable`) survive and are fine.

Found by intersecting the app's `__objc_selrefs` with `ios(15|16)`-annotated declarations
in the iOS 16.5 SDK. Each gets an add-if-missing fallback (no-op where the real method exists):
`UIWindowScene.keyWindow`, `+UIColor.tintColor`, `UIBarButtonItem.hidden/selected`,
`UIButton.configuration/subtitleLabel`, `UIBackgroundConfiguration.image*`,
`UINavigationItem.style`, `UIMenuElement/UIScene.subtitle`, `UISearchBar.enabled`,
`UIPageControl.direction`, `NSURLSessionTask.delegate`,
`NSPersonNameComponentsFormatter.locale`, `NSUUID compare:`, `CHHapticPattern` URL init,
`UNNotificationContent contentByUpdatingWithProvider:error:`,
`NSDiffableDataSourceSnapshot reconfigureItemsWithIdentifiers:`, and more.

**Name-collision trap:** `scrollEdgeAppearance` is iOS 13 on `UINavigationBar` but iOS 15
on `UIToolbar`, `UITabBar`, `UITabBarItem`. A scan that skips names already present on
14 misses it. Unfixed, theming the toolbar after initial provisioning raised an
NSException inside libsoftphone's C++ provisioning code → `noexcept` boundary →
`std::terminate` (right after the "please wait" bar).

Nibs: the only missing class is `UIButtonConfiguration` (7 buttons in 3 nibs whose title
exists only in the configuration). compat.m registers a stub class and applies its title /
image / colour from `-[UIButton initWithCoder:]`.

## Diagnostics (src/compat.m, src/compat_cxx.mm)

Only in builds with `VOIPSHIM_LOG=1`; normal builds compile all of this out, and since the
shim then exports no `___cxa_throw` / `set_terminate`, patch.py leaves those imports bound
to libc++. Written to `Documents/voipshim.log` (the app has `UIFileSharingEnabled`, so Files app →
On My iPhone shows it). iOS 14 crash reports omit exception reasons; this file has them.

| Line | Meaning |
|---|---|
| `added -[Class sel]` | a fallback was installed (method missing on this iOS) |
| `UNRECOGNIZED -[Class sel]` + backtrace | a method the app calls doesn't exist → add a fallback |
| `UNCAUGHT name: reason` | uncaught NSException |
| `TERMINATE type: what` + `thrown at` / `terminate at` | C++ (or ObjC-through-C++) exception hit `std::terminate` |
| `MISSING iOS 15+ function called` | a shimmed-to-abort function was reached |

C++ hooks: the main binary's `___cxa_throw` and `std::set_terminate` imports are retargeted
to the shim (`HOOKS` in patch.py; `__DATA,__interpose` is ignored by iOS 14 dyld2 except
for inserted libraries). The throw hook records each thread's last throw (type +
backtrace); the terminate handler logs it. libsoftphone installs its own terminate handler,
which would otherwise hide ObjC exceptions that end in `std::terminate`. Frames print as
`image+0xoffset`; for the main binary add `0x100000000`.

## Known limits

- ObjC calls to iOS 15/16 methods reached only via `performSelector:`-style strings aren't
  caught by the scan — watch for `UNRECOGNIZED`.
- `objc_claimAutoreleasedReturnValue` → `objc_retainAutoreleasedReturnValue`: correct, the
  return-value fast path just never engages.
- Tested on one iOS version (14.3). Other 14.x versions should work if built against their
  own dyld cache, but are untested.
