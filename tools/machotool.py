"""Minimal thin-arm64 Mach-O helpers + a dyld-cache export resolver.

Only what patch.py / verify.py need: load commands, chained-fixup imports,
export tries, and resolving an install name to its exported symbol set
(dyld_shared_cache images are extracted on demand with dyldex).
"""
import os
import struct
import subprocess

LC_SEGMENT_64 = 0x19
LC_LOAD_DYLIB = 0xC
LC_ID_DYLIB = 0xD
LC_LOAD_WEAK_DYLIB = 0x80000018
LC_REEXPORT_DYLIB = 0x8000001F
LC_LAZY_LOAD_DYLIB = 0x20
LC_LOAD_UPWARD_DYLIB = 0x80000023
LC_RPATH = 0x8000001C
LC_BUILD_VERSION = 0x32
LC_DYLD_INFO = 0x22
LC_DYLD_INFO_ONLY = 0x80000022
LC_DYLD_EXPORTS_TRIE = 0x80000033
LC_DYLD_CHAINED_FIXUPS = 0x80000034
LC_CODE_SIGNATURE = 0x1D
LC_SYMTAB = 0x2

DYLIB_CMDS = (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB,
              LC_LAZY_LOAD_DYLIB, LC_LOAD_UPWARD_DYLIB)


def uleb(d, i):
    r = sh = 0
    while True:
        b = d[i]
        i += 1
        r |= (b & 0x7F) << sh
        sh += 7
        if b < 0x80:
            return r, i


def export_trie(d, base):
    syms, stack = set(), [(0, b'')]
    while stack:
        off, pre = stack.pop()
        i = base + off
        tsize, i = uleb(d, i)
        if tsize:
            syms.add(pre.decode('utf-8', 'replace'))
        i += tsize
        n = d[i]
        i += 1
        for _ in range(n):
            e = d.index(b'\0', i)
            edge = d[i:e]
            i = e + 1
            child, i = uleb(d, i)
            stack.append((child, pre + edge))
    return syms


def cstr(b):
    return bytes(b).split(b'\0')[0].decode()


class MachO:
    def __init__(self, data):
        self.d = bytearray(data)
        magic, _, _, self.filetype, ncmds, _, _, _ = struct.unpack_from('<8I', self.d, 0)
        assert magic == 0xFEEDFACF, 'thin arm64 Mach-O only'
        self.cmds = []  # [cmd, bytes]
        off = 32
        for _ in range(ncmds):
            cmd, sz = struct.unpack_from('<II', self.d, off)
            self.cmds.append([cmd, bytes(self.d[off:off + sz])])
            off += sz

    # -- load commands -------------------------------------------------
    def dylibs(self):
        """[(ordinal, cmd, path)] in ordinal order (1-based)."""
        out = []
        for cmd, b in self.cmds:
            if cmd in DYLIB_CMDS:
                no = struct.unpack_from('<I', b, 8)[0]
                out.append((len(out) + 1, cmd, cstr(b[no:])))
        return out

    def rpaths(self):
        return [cstr(b[struct.unpack_from('<I', b, 8)[0]:]) for c, b in self.cmds if c == LC_RPATH]

    def segments(self):
        out = []
        for c, b in self.cmds:
            if c == LC_SEGMENT_64:
                name = cstr(b[8:24])
                vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<4Q', b, 24)
                nsect = struct.unpack_from('<I', b, 64)[0]
                sects = []
                for i in range(nsect):
                    so = 72 + 80 * i
                    sname = cstr(b[so:so + 16])
                    addr, size = struct.unpack_from('<2Q', b, so + 32)
                    offset, _, _, _, flags = struct.unpack_from('<5I', b, so + 48)
                    sects.append((sname, addr, size, offset, flags))
                out.append((name, vmaddr, vmsize, fileoff, filesize, sects))
        return out

    def header_limit(self):
        """File offset of the first section content: load commands must end before it."""
        lim = None
        for name, vmaddr, vmsize, fileoff, filesize, sects in self.segments():
            for sname, addr, size, offset, flags in sects:
                if offset and size and (flags & 0xFF) not in (1, 0xC, 0x12):  # skip zerofill
                    lim = offset if lim is None else min(lim, offset)
        return lim

    def linkedit(self, cmd):
        for c, b in self.cmds:
            if c == cmd:
                return b
        return None

    def exports(self):
        syms = set()
        for c, b in self.cmds:
            if c in (LC_DYLD_INFO, LC_DYLD_INFO_ONLY):
                eo, es = struct.unpack_from('<II', b, 40)
                if es:
                    syms |= export_trie(self.d, eo)
            elif c == LC_DYLD_EXPORTS_TRIE:
                eo, es = struct.unpack_from('<II', b, 8)
                if es:
                    syms |= export_trie(self.d, eo)
        return syms

    def reexports(self):
        return [p for _, c, p in self.dylibs() if c == LC_REEXPORT_DYLIB]

    def write_cmds(self):
        """Serialize self.cmds back into the header, checking the space budget."""
        blob = b''.join(b for _, b in self.cmds)
        lim = self.header_limit()
        old = struct.unpack_from('<I', self.d, 20)[0]
        assert 32 + len(blob) <= lim, f'load commands {32 + len(blob):#x} overrun first section {lim:#x}'
        self.d[32:32 + max(old, len(blob))] = blob + b'\0' * max(0, old - len(blob))
        struct.pack_into('<II', self.d, 16, len(self.cmds), len(blob))

    # -- chained fixups ------------------------------------------------
    def chained(self):
        b = self.linkedit(LC_DYLD_CHAINED_FIXUPS)
        if b is None:
            return None
        return struct.unpack_from('<I', b, 8)[0]

    def chained_imports(self):
        """[(index, entry_file_offset, ordinal, weak, name)] (imports_format 1 only)."""
        fo = self.chained()
        ver, starts, imps, syms, cnt, ifmt, sfmt = struct.unpack_from('<7I', self.d, fo)
        assert ifmt == 1 and sfmt == 0, (ifmt, sfmt)
        out = []
        for i in range(cnt):
            eo = fo + imps + 4 * i
            v = struct.unpack_from('<I', self.d, eo)[0]
            ordn, weak, no = v & 0xFF, (v >> 8) & 1, v >> 9
            name = cstr(self.d[fo + syms + no:fo + syms + no + 4096])
            out.append((i, eo, ordn, weak, name))
        return out

    def set_import(self, eo, ordinal=None, weak=None):
        v = struct.unpack_from('<I', self.d, eo)[0]
        if ordinal is not None:
            assert 0 < ordinal < 0xF0
            v = (v & ~0xFF) | ordinal
        if weak is not None:
            v = (v & ~0x100) | (int(weak) << 8)
        struct.pack_into('<I', self.d, eo, v)

    def chain_formats(self):
        fo = self.chained()
        so = fo + struct.unpack_from('<I', self.d, fo + 4)[0]
        fmts = set()
        for i in range(struct.unpack_from('<I', self.d, so)[0]):
            o = struct.unpack_from('<I', self.d, so + 4 + 4 * i)[0]
            if o:
                fmts.add(struct.unpack_from('<H', self.d, so + o + 6)[0])
        return fmts

    def convert_chains_6_to_2(self):
        """DYLD_CHAINED_PTR_64_OFFSET -> DYLD_CHAINED_PTR_64. Same bit layout and stride;
        rebase target changes from vm offset to absolute vmaddr."""
        fo = self.chained()
        segs = self.segments()
        base = next(s[1] for s in segs if s[0] == '__TEXT')
        so = fo + struct.unpack_from('<I', self.d, fo + 4)[0]
        nseg = struct.unpack_from('<I', self.d, so)[0]
        assert nseg == len(segs)
        rebases = binds = 0
        for i in range(nseg):
            o = struct.unpack_from('<I', self.d, so + 4 + 4 * i)[0]
            if not o:
                continue
            rec = so + o
            _, page_size, fmt, _, _, page_count = struct.unpack_from('<IHHQIH', self.d, rec)
            if fmt == 2:
                continue
            assert fmt == 6, f'{segs[i][0]}: pointer_format {fmt}'
            seg_fileoff = segs[i][3]
            for p in range(page_count):
                ps = struct.unpack_from('<H', self.d, rec + 22 + 2 * p)[0]
                if ps == 0xFFFF:
                    continue
                assert not ps & 0x8000, 'multi-start page'
                loc = seg_fileoff + p * page_size + ps
                while True:
                    v = struct.unpack_from('<Q', self.d, loc)[0]
                    nxt = (v >> 51) & 0xFFF
                    if v >> 63:
                        binds += 1
                    else:
                        t = (v & 0xFFFFFFFFF) + base
                        assert t < (1 << 36)
                        struct.pack_into('<Q', self.d, loc, (v & ~0xFFFFFFFFF) | t)
                        rebases += 1
                    if not nxt:
                        break
                    loc += nxt * 4
            struct.pack_into('<H', self.d, rec + 6, 2)
        return rebases, binds


def dylib_cmd(cmd, path, cur=0x10000, compat=0x10000):
    p = path.encode() + b'\0'
    size = (24 + len(p) + 7) & ~7
    return [cmd, struct.pack('<6I', cmd, size, 24, 2, cur, compat) + p.ljust(size - 24, b'\0')]


def rpath_cmd(path):
    p = path.encode() + b'\0'
    size = (12 + len(p) + 7) & ~7
    return [LC_RPATH, struct.pack('<3I', LC_RPATH, size, 12) + p.ljust(size - 12, b'\0')]


class Resolver:
    """Exported-symbol sets for install names: dyld cache (via dyldex) or bundle files."""

    def __init__(self, dyldex, cache, workdir):
        self.dyldex, self.cache, self.workdir = dyldex, cache, workdir
        os.makedirs(workdir, exist_ok=True)
        self.memo = {}

    def image(self, path):
        """Return MachO for a system install name, or None if not in the cache."""
        out = os.path.join(self.workdir, path.strip('/').replace('/', '__'))
        if not os.path.exists(out):
            subprocess.run([self.dyldex, '-e', path.lstrip('/'), '-o', out, self.cache],
                           capture_output=True)
        if not os.path.exists(out):
            return None
        return MachO(open(out, 'rb').read())

    def exports(self, path, file=None):
        """All symbols visible through `path` (following re-exports). None = image absent."""
        key = file or path
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = set()  # cycle guard
        m = MachO(open(file, 'rb').read()) if file else self.image(path)
        if m is None:
            self.memo[key] = None
            return None
        s = set(m.exports())
        for r in m.reexports():
            sub = self.exports(r)
            if sub:
                s |= sub
        self.memo[key] = s
        return s


def bind_entries(m, which):
    """[(seg_index, seg_offset, ordinal, flags, name)] from one LC_DYLD_INFO opcode stream
    ('bind', 'weak_bind', 'lazy_bind'), plus the file offset where a non-lazy stream's
    DONE sits (None for lazy / no DONE). Weak-bind entries have no ordinal (0)."""
    b = m.linkedit(LC_DYLD_INFO_ONLY) or m.linkedit(LC_DYLD_INFO)
    if b is None:
        return [], None
    fields = dict(zip(('rebase', 'bind', 'weak_bind', 'lazy_bind', 'export'),
                      zip(*[iter(struct.unpack_from('<10I', b, 8))] * 2)))
    off, size = fields[which]
    d, i, end = m.d, off, off + size
    o = fl = seg = so = 0
    name = None
    out = []
    while i < end:
        at = i
        op, imm = d[i] & 0xF0, d[i] & 0x0F
        i += 1
        if op == 0x00:                          # DONE (lazy table has one per entry)
            if which != 'lazy_bind':
                return out, at
        elif op == 0x10:                        # SET_DYLIB_ORDINAL_IMM
            o = imm
        elif op == 0x20:                        # SET_DYLIB_ORDINAL_ULEB
            o, i = uleb(d, i)
        elif op == 0x30:                        # SET_DYLIB_SPECIAL_IMM
            o = (imm | 0xF0) - 0x100 if imm else 0
        elif op == 0x40:                        # SET_SYMBOL_TRAILING_FLAGS_IMM
            e = d.index(b'\0', i)
            name, fl, i = d[i:e].decode(), imm, e + 1
        elif op == 0x50:                        # SET_TYPE_IMM
            pass
        elif op == 0x60:                        # SET_ADDEND_SLEB
            _, i = uleb(d, i)
        elif op == 0x70:                        # SET_SEGMENT_AND_OFFSET_ULEB
            seg = imm
            so, i = uleb(d, i)
        elif op == 0x80:                        # ADD_ADDR_ULEB
            v, i = uleb(d, i)
            so = (so + v) & (2**64 - 1)
        elif op == 0x90:                        # DO_BIND
            out.append((seg, so, o, fl, name))
            so += 8
        elif op == 0xA0:                        # DO_BIND_ADD_ADDR_ULEB
            out.append((seg, so, o, fl, name))
            v, i = uleb(d, i)
            so = (so + 8 + v) & (2**64 - 1)
        elif op == 0xB0:                        # DO_BIND_ADD_ADDR_IMM_SCALED
            out.append((seg, so, o, fl, name))
            so += 8 + imm * 8
        elif op == 0xC0:                        # DO_BIND_ULEB_TIMES_SKIPPING_ULEB
            n, i = uleb(d, i)
            skip, i = uleb(d, i)
            for _ in range(n):
                out.append((seg, so, o, fl, name))
                so += 8 + skip
        elif op == 0xD0:                        # THREADED: 0 = ordinal-table size (uleb), 1 = apply
            if imm == 0:
                _, i = uleb(d, i)
        else:
            raise ValueError(f'bind opcode {op:#x}')
    return out, None


def classic_binds(m):
    """[(ordinal, weak_import, name)] from LC_DYLD_INFO bind + lazy-bind opcodes."""
    out = set()
    for which in ('bind', 'lazy_bind'):
        out |= {(o, fl & 1, n) for _, _, o, fl, n in bind_entries(m, which)[0]}
    return sorted(out, key=lambda t: (t[0], t[2] or ''))


def weak_lookup_only(m):
    """Weak-bind entries for symbols with no regular bind and no definition here:
    [(seg_index, seg_offset, name)]. ld-prime emits operator new/delete this way,
    relying on dyld4's weak-def lookup; iOS 14 dyld2 only coalesces when some non-cache
    image has weak definitions, so these slots stay 0 (call -> pc 0)."""
    strong = {n for _, _, n in classic_binds(m)}
    own = m.exports()
    return [(seg, so, n) for seg, so, _, fl, n in bind_entries(m, 'weak_bind')[0]
            if not fl & 8 and n not in strong and n not in own]   # 8 = NON_WEAK_DEFINITION


def append_binds(m, binds):
    """Append regular binds [(seg_index, seg_offset, ordinal, name)] to the bind stream.
    dyld2 requires rebase <= bind <= weak_bind <= lazy_bind <= export in the file, so the
    bind stream (extended) and everything after it in that order are copied to where the
    code signature starts, followed by the string table (ldid places the new signature at
    the string table's end). Lazy-bind offsets in __stub_helper are stream-relative, so the
    copies stay valid. Signature dropped (datasize 0): re-sign with ldid afterwards."""
    di = next(i for i, (c, _) in enumerate(m.cmds) if c in (LC_DYLD_INFO, LC_DYLD_INFO_ONLY))
    f = list(struct.unpack_from('<10I', m.cmds[di][1], 8))   # (off, size) x rebase..export
    _, done = bind_entries(m, 'bind')
    body = bytes(m.d[f[2]:done if done is not None else f[2] + f[3]])
    ops = bytearray(b'\x51\x60\x00')          # TYPE_POINTER, ADDEND 0 (state carries over)
    for seg, so, o, name in binds:
        assert 0 < o < 0xF0
        ops += bytes([0x10 | o]) if o < 16 else bytes([0x20]) + uleb_enc(o)
        ops += b'\x40' + name.encode() + b'\0'
        ops += bytes([0x70 | seg]) + uleb_enc(so) + b'\x90'
    ops.append(0x00)
    blobs = [body + ops] + [bytes(m.d[f[k]:f[k] + f[k + 1]]) for k in (4, 6, 8)]

    ci = next(i for i, (c, _) in enumerate(m.cmds) if c == LC_CODE_SIGNATURE)
    start = struct.unpack_from('<I', m.cmds[ci][1], 8)[0]
    si = next(i for i, (c, _) in enumerate(m.cmds) if c == LC_SYMTAB)
    stroff, strsize = struct.unpack_from('<II', m.cmds[si][1], 16)
    strtab = bytes(m.d[stroff:stroff + strsize])
    del m.d[start:]
    for k, blob in zip((2, 4, 6, 8), blobs):
        if f[k + 1] or k == 2:
            f[k], f[k + 1] = len(m.d), (len(blob) + 7) & ~7
            m.d += blob.ljust(f[k + 1], b'\0')
    new_so = len(m.d)
    m.d += strtab
    end = (len(m.d) + 15) & ~15
    m.d += b'\0' * (end - len(m.d))
    m.cmds[di][1] = m.cmds[di][1][:8] + struct.pack('<10I', *f) + m.cmds[di][1][48:]
    m.cmds[ci][1] = m.cmds[ci][1][:8] + struct.pack('<II', end, 0)
    m.cmds[si][1] = m.cmds[si][1][:16] + struct.pack('<I', new_so) + m.cmds[si][1][20:]
    for i, (c, cb) in enumerate(m.cmds):
        if c == LC_SEGMENT_64 and cstr(cb[8:24]) == '__LINKEDIT':
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<4Q', cb, 24)
            filesize = end - fileoff
            vmsize = max(vmsize, (filesize + 0x3FFF) & ~0x3FFF)
            m.cmds[i][1] = cb[:24] + struct.pack('<4Q', vmaddr, vmsize, fileoff, filesize) + cb[56:]
    m.write_cmds()


def linkedit_layout_errors(m):
    """14.3 dyld's LINKEDIT checks: dyld2 sniffLoadCommands order (rebase <= bind <=
    weak_bind <= lazy_bind <= export) and dyld3 validLinkeditLayout (inside __LINKEDIT,
    no overlaps, alignment)."""
    le = next(s for s in m.segments() if s[0] == '__LINKEDIT')
    lo, hi = le[3], le[3] + le[4]
    chunks = []   # (name, off, size, align)
    for c, b in m.cmds:
        if c in (LC_DYLD_INFO, LC_DYLD_INFO_ONLY):
            f = struct.unpack_from('<10I', b, 8)
            names = ('rebase', 'bind', 'weak_bind', 'lazy_bind', 'export')
            chunks += [(n, f[2 * k], f[2 * k + 1], 8) for k, n in enumerate(names)]
        elif c == LC_SYMTAB:
            symoff, nsyms, stroff, strsize = struct.unpack_from('<4I', b, 8)
            chunks += [('symtab', symoff, nsyms * 16, 8), ('strings', stroff, strsize, 1)]
        elif c == 0xB:   # LC_DYSYMTAB
            ioff, n = struct.unpack_from('<II', b, 56)
            chunks.append(('indirect', ioff, n * 4, 4))
        elif c in (0x26, 0x29, LC_DYLD_CHAINED_FIXUPS, LC_DYLD_EXPORTS_TRIE, LC_CODE_SIGNATURE):
            off, size = struct.unpack_from('<II', b, 8)
            chunks.append(({0x26: 'function_starts', 0x29: 'data_in_code',
                            LC_CODE_SIGNATURE: 'code_signature'}.get(c, hex(c)), off, size,
                           16 if c == LC_CODE_SIGNATURE else 8))
    chunks = [ch for ch in chunks if ch[2]]
    errs = []
    order = [ch for ch in chunks if ch[0] in ('rebase', 'bind', 'weak_bind', 'lazy_bind', 'export')]
    for (pn, po, ps, _), (n, o, s, _) in zip(order, order[1:]):
        if o < po + ps:
            errs.append(f'dyld2: {n} @{o:#x} before end of {pn} @{po + ps:#x}')
    prev = None
    for n, o, s, al in sorted(chunks, key=lambda ch: ch[1]):
        if o < lo or o + s > hi:
            errs.append(f'{n} outside __LINKEDIT')
        if o % al:
            errs.append(f'{n} @{o:#x} not {al}-aligned')
        if prev and o < prev[1] + prev[2]:
            errs.append(f'{n} overlaps {prev[0]}')
        prev = (n, o, s)
    return errs


def uleb_enc(v):
    out = bytearray()
    while True:
        b, v = v & 0x7F, v >> 7
        out.append(b | (0x80 if v else 0))
        if not v:
            return bytes(out)
