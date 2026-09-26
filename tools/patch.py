#!/usr/bin/env python3
"""Patch voip.ms Softphone (min iOS 16) to load on iOS 14. See ../NOTES.md.

usage: patch.py <in.ipa> <out.tipa> <dyld_shared_cache> <dyldex> <workdir>
  <workdir>/libvoipshim.dylib must exist (src/build-shim.sh).
  env: THEOS (default ~/theos), THEOS_BIN (ldid dir), CONCURRENCY (libswift_Concurrency.dylib)

Per chained-fixup image (main binary, SoftphoneIntents):
  * pointer format 6 -> 2, LC_BUILD_VERSION minos -> 14.0
  * missing system dylibs: libswift_Concurrency -> bundled back-deploy copy (@rpath),
    AVFAudio (split from AVFoundation in 14.5) -> weak load
  * each import that doesn't resolve on 14.3 is, in order:
      exported by libvoipshim            -> retarget to shim
      Foundation + in libswiftFoundation -> retarget (Swift overlay lived there pre-15)
      AVFAudio + in AVFoundation         -> retarget
      otherwise                          -> weak (null at runtime)
  * weak-lookup imports (ordinal -3: operator new/delete, typeinfo) -> the system dylib
    that exports them
Per classic-bind image (AmazonChimeSDK, AmazonChimeSDKMedia): weak-bind-only symbols
(ld-prime's operator new/delete, left null by 14.3 dyld2) get explicit binds.
Then Info.plist MinimumOSVersion, bundle shim + Concurrency, ldid re-sign keeping
the original entitlements, zip as .tipa.
"""
import os
import plistlib
import shutil
import struct
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from machotool import (MachO, Resolver, dylib_cmd, rpath_cmd, weak_lookup_only,
                       append_binds, LC_BUILD_VERSION, LC_LOAD_WEAK_DYLIB, LC_LOAD_DYLIB,
                       LC_DYLD_CHAINED_FIXUPS)

THEOS = os.environ.get('THEOS', os.path.expanduser('~/theos'))
THEOS_BIN = os.environ.get('THEOS_BIN', os.path.join(THEOS, 'toolchain/linux/iphone/bin'))
# Swift 5.5 back-deployment runtime (iOS 13-14), shipped with theos' swift-5.8 toolchain
CONCURRENCY = os.environ.get('CONCURRENCY', os.path.join(
    THEOS, 'toolchain/swift-5.8/linux/iphone/lib/swift-5.5/iphoneos/libswift_Concurrency.dylib'))
SHIM = None  # <workdir>/libvoipshim.dylib, set in main()
TESTED_VERSION = '0.0.6'
MINOS = 0x000E0000  # 14.0

SYS_CONCURRENCY = '/usr/lib/swift/libswift_Concurrency.dylib'
AVFAUDIO = '/System/Library/Frameworks/AVFAudio.framework/AVFAudio'
AVFOUNDATION = '/System/Library/Frameworks/AVFoundation.framework/AVFoundation'
FOUNDATION = '/System/Library/Frameworks/Foundation.framework/Foundation'
SWIFT_FOUNDATION = '/usr/lib/swift/libswiftFoundation.dylib'
SHIM_NAME = '@rpath/libvoipshim.dylib'
# resolvable imports still sent to the shim (diagnostic hooks, compat_cxx.mm)
HOOKS = {'___cxa_throw', '__ZSt13set_terminatePFvvE'}


def log(*a):
    print(*a, flush=True)


def lib_exports(res, path, fw_dir):
    """Exports of a load-command path as seen from the app on 14.3 (None = absent)."""
    if path.startswith('@rpath/'):
        rel = path[len('@rpath/'):]
        f = os.path.join(fw_dir, rel)
        if os.path.exists(f):
            return res.exports(path, file=f)
        return res.exports('/usr/lib/swift/' + rel)   # LC_RPATH /usr/lib/swift
    return res.exports(path)


def exporting_ordinal(m, sym, exports_of):
    """First non-weak dylib ordinal of m whose exports (on 14.3) contain sym, or None."""
    for o, cmd, p in m.dylibs():
        if cmd != LC_LOAD_WEAK_DYLIB and sym in (exports_of(p) or ()):
            return o
    return None


def patch_classic(path, res, fw_dir, report):
    """Explicit binds for weak-bind-only symbols (see machotool.weak_lookup_only)."""
    m = MachO(open(path, 'rb').read())
    name = os.path.basename(path)
    binds = []
    for seg, so, sym in weak_lookup_only(m):
        o = exporting_ordinal(m, sym, lambda p: lib_exports(res, p, fw_dir))
        assert o, f'{name}: no dylib exports weak-lookup {sym}'
        binds.append((seg, so, o, sym))
    if not binds:
        return False
    append_binds(m, binds)
    open(path, 'wb').write(m.d)
    report.append(f'{name}: {len(binds)} weak-bind-only -> explicit bind: '
                  + ' '.join(sorted({s for *_, s in binds})))
    return True


def patch_image(path, res, fw_dir, report):
    m = MachO(open(path, 'rb').read())
    name = os.path.basename(path)

    for c in m.cmds:
        if c[0] == LC_BUILD_VERSION:
            b = bytearray(c[1])
            struct.pack_into('<I', b, 12, MINOS)
            c[1] = bytes(b)

    if m.chain_formats() != {2}:
        r, b = m.convert_chains_6_to_2()
        report.append(f'{name}: chains 6->2, {r} rebases, {b} binds')

    # load-command fixes for dylibs absent on 14.3
    need_swift_rpath = False
    for c in m.cmds:
        if c[0] not in (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB):
            continue
        no = struct.unpack_from('<I', c[1], 8)[0]
        p = c[1][no:].split(b'\0')[0].decode()
        if p == SYS_CONCURRENCY:
            cur, compat = struct.unpack_from('<II', c[1], 16)
            c[:] = dylib_cmd(c[0], '@rpath/libswift_Concurrency.dylib', cur, compat)
            need_swift_rpath = True
            report.append(f'{name}: {p} -> @rpath (bundled back-deploy)')
        elif p == AVFAUDIO and c[0] == LC_LOAD_DYLIB:
            b = bytearray(c[1])
            struct.pack_into('<I', b, 0, LC_LOAD_WEAK_DYLIB)
            c[:] = [LC_LOAD_WEAK_DYLIB, bytes(b)]
            report.append(f'{name}: {p} -> weak load')

    shim_exports = res.exports(SHIM_NAME, file=SHIM)
    ords = {o: p for o, _, p in m.dylibs()}
    by_path = {p: o for o, p in ords.items()}
    exp_cache = {}

    def exports_of(p):
        if p not in exp_cache:
            exp_cache[p] = lib_exports(res, p, fw_dir)
        return exp_cache[p]

    # classify unresolved imports
    plan = []  # (entry_offset, target_path | None(weak), name, from_path)
    for i, eo, o, weak, sym in m.chained_imports():
        if o in (0, 0xFD, 0xFE, 0xFF):       # self / weak-lookup / flat / main
            continue
        p = ords[o]
        if sym in HOOKS and sym in shim_exports:
            plan.append((eo, SHIM_NAME, sym, p))
            continue
        ex = exports_of(p)
        if ex is not None and sym in ex:
            continue
        if sym in shim_exports:
            plan.append((eo, SHIM_NAME, sym, p))
        elif p == FOUNDATION and sym in (exports_of(SWIFT_FOUNDATION) or ()):
            plan.append((eo, SWIFT_FOUNDATION, sym, p))
        elif p == AVFAUDIO and sym in (exports_of(AVFOUNDATION) or ()):
            plan.append((eo, AVFOUNDATION, sym, p))
        else:
            plan.append((eo, None, sym, p))

    # add any new load commands (appended => new ordinals at the end)
    for target in sorted({t for _, t, _, _ in plan if t}):
        if target not in by_path:
            m.cmds.append(dylib_cmd(LC_LOAD_DYLIB, target))
            report.append(f'{name}: + LC_LOAD_DYLIB {target}')
    if need_swift_rpath and '/usr/lib/swift' not in m.rpaths():
        m.cmds.append(rpath_cmd('/usr/lib/swift'))
        report.append(f'{name}: + LC_RPATH /usr/lib/swift')
    m.write_cmds()
    by_path = {p: o for o, _, p in m.dylibs()}

    counts = {}
    for eo, target, sym, frm in plan:
        if target:
            m.set_import(eo, ordinal=by_path[target])
            key = f'{os.path.basename(frm)} -> {os.path.basename(target)}'
        else:
            m.set_import(eo, weak=True)
            key = f'weak ({os.path.basename(frm)})'
            report.append(f'{name}:   weak {os.path.basename(frm)} {sym}')
        counts[key] = counts.get(key, 0) + 1
    for k, v in sorted(counts.items()):
        report.append(f'{name}: {v:4d} imports {k}')

    # weak-lookup (-3) imports not defined here -> concrete ordinal
    own = m.exports()
    wl = []
    for i, eo, o, weak, sym in m.chained_imports():
        if o == 0xFD and sym not in own:
            t = exporting_ordinal(m, sym, exports_of)
            assert t, f'{name}: no dylib exports weak-lookup {sym}'
            m.set_import(eo, ordinal=t)
            wl.append(sym)
    if wl:
        report.append(f'{name}: {len(wl):4d} weak-lookup imports -> explicit: {" ".join(wl)}')

    open(path, 'wb').write(m.d)


def set_min_os(plist_path):
    """MinimumOSVersion -> 14.0; drop App Store thinning's UISupportedDevices (the
    input was thinned for iPhone10,1/10,4/12,8/14,6 — installd refuses other models)."""
    with open(plist_path, 'rb') as f:
        pl = plistlib.load(f)
    fmt = plistlib.FMT_BINARY if open(plist_path, 'rb').read(6) == b'bplist' else plistlib.FMT_XML
    old = pl.get('MinimumOSVersion')
    pl['MinimumOSVersion'] = '14.0'
    if pl.pop('UISupportedDevices', None):
        old = f'{old} (UISupportedDevices removed)'
    with open(plist_path, 'wb') as f:
        plistlib.dump(pl, f, fmt=fmt)
    return old


def ldid(*args):
    r = subprocess.run([os.path.join(THEOS_BIN, 'ldid'), *args], capture_output=True)
    if r.returncode:
        raise SystemExit(f'ldid {args}: {r.stderr.decode()}')
    return r.stdout


def main():
    global SHIM
    ipa, out, cache, dyldex, work = sys.argv[1:6]
    SHIM = os.path.join(work, 'libvoipshim.dylib')
    for f, what in ((SHIM, 'shim (run src/build-shim.sh)'), (CONCURRENCY, 'libswift_Concurrency (set CONCURRENCY)'),
                    (os.path.join(THEOS_BIN, 'ldid'), 'ldid (set THEOS or THEOS_BIN)')):
        if not os.path.exists(f):
            raise SystemExit(f'missing {what}: {f}')
    stage = os.path.join(work, 'stage')
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    with zipfile.ZipFile(ipa) as z:
        z.extractall(stage)
    # zipfile drops modes; restore exec bits from the archive
    with zipfile.ZipFile(ipa) as z:
        for zi in z.infolist():
            mode = zi.external_attr >> 16
            if mode:
                os.chmod(os.path.join(stage, zi.filename), mode & 0o7777)

    app = os.path.join(stage, 'Payload', os.listdir(os.path.join(stage, 'Payload'))[0])
    info = plistlib.load(open(os.path.join(app, 'Info.plist'), 'rb'))
    if info.get('CFBundleIdentifier') != 'ms.voip.softphone.ios':
        raise SystemExit(f"not the voip.ms Softphone: {info.get('CFBundleIdentifier')}")
    if info.get('CFBundleShortVersionString') != TESTED_VERSION:
        log(f"WARNING: input is {info.get('CFBundleShortVersionString')}, patcher tested on {TESTED_VERSION}")
    exe = os.path.join(app, info['CFBundleExecutable'])
    fw = os.path.join(app, 'Frameworks')
    intents = os.path.join(fw, 'SoftphoneIntents.framework', 'SoftphoneIntents')

    # entitlements before touching anything
    ents = {}
    for p in (exe, intents):
        e = ldid('-e', p)
        ents[p] = os.path.join(work, os.path.basename(p) + '.ents.plist')
        open(ents[p], 'wb').write(e)

    shutil.copy2(SHIM, fw)
    shutil.copy2(CONCURRENCY, fw)

    res = Resolver(dyldex, cache, os.path.join(work, 'dsc'))
    report = []
    for p in (exe, intents):
        patch_image(p, res, fw, report)
    classic = []
    for d in sorted(os.listdir(fw)):
        if d.endswith('.framework'):
            p = os.path.join(fw, d, d[:-len('.framework')])
            if os.path.exists(p) and MachO(open(p, 'rb').read()).linkedit(LC_DYLD_CHAINED_FIXUPS) is None:
                assert not ldid('-e', p).strip(), f'{p}: entitlements, plain re-sign would drop them'
                if patch_classic(p, res, fw, report):
                    classic.append(p)
    for pl in (os.path.join(app, 'Info.plist'),
               os.path.join(fw, 'SoftphoneIntents.framework', 'Info.plist')):
        report.append(f'{os.path.relpath(pl, app)}: MinimumOSVersion {set_min_os(pl)} -> 14.0')

    # re-sign: patched images with original entitlements, added dylibs plain
    for p in (intents, exe):
        ldid('-S' + ents[p] if os.path.getsize(ents[p]) else '-S', p)
    for p in classic:
        ldid('-S', p)
    for d in ('libvoipshim.dylib', 'libswift_Concurrency.dylib'):
        ldid('-S', os.path.join(fw, d))
    report.append('re-signed (ldid) with original entitlements')

    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(os.path.join(stage, 'Payload')):
            dirs.sort()
            for f in sorted(files):
                full = os.path.join(root, f)
                zi = zipfile.ZipInfo.from_file(full, os.path.relpath(full, stage))
                zi.compress_type = zipfile.ZIP_DEFLATED
                with open(full, 'rb') as fh:
                    z.writestr(zi, fh.read())
    report.append(f'wrote {out}')
    log('\n'.join(report))


if __name__ == '__main__':
    main()
