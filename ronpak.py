"""Reader and writer for Unreal Engine .pak archives (format version 8-11).

Only what Ready or Not needs: no encryption, and the writer always emits
uncompressed entries (the files we ship are a few tens of KB of .ini text).

Verified against the shipping pakchunk*.pak files and against a known-good
community mod pak: the path-hash algorithm, index layout and footer layout
below all round-trip those files exactly.
"""
import hashlib
import os
import struct

MAGIC = 0x5A6F12E1
VERSION = 11              # PakFile_Version_Fnv64BugFix
FOOTER_SIZE = 221         # guid(16) + encrypted(1) + magic(4) + ver(4) + off(8) + size(8) + sha(20) + 5*32
MAX_METHODS = 5
M64 = (1 << 64) - 1


# ---------------------------------------------------------------- primitives

class R:
    def __init__(self, d, o=0):
        self.d = d
        self.o = o

    def u8(self):
        v = self.d[self.o]; self.o += 1; return v

    def i32(self):
        v = struct.unpack_from('<i', self.d, self.o)[0]; self.o += 4; return v

    def u32(self):
        v = struct.unpack_from('<I', self.d, self.o)[0]; self.o += 4; return v

    def i64(self):
        v = struct.unpack_from('<q', self.d, self.o)[0]; self.o += 8; return v

    def u64(self):
        v = struct.unpack_from('<Q', self.d, self.o)[0]; self.o += 8; return v

    def raw(self, n):
        v = self.d[self.o:self.o + n]; self.o += n; return v

    def fstring(self):
        n = self.i32()
        if n == 0:
            return ''
        if n < 0:
            return self.raw(-n * 2).decode('utf-16-le').rstrip('\0')
        return self.raw(n).decode('utf-8', 'replace').rstrip('\0')


def fstring(s):
    """Serialise an FString the way UE does (ASCII when possible)."""
    if s == '':
        return struct.pack('<i', 0)
    try:
        b = s.encode('ascii') + b'\0'
        return struct.pack('<i', len(b)) + b
    except UnicodeEncodeError:
        b = s.encode('utf-16-le') + b'\0\0'
        return struct.pack('<i', -(len(b) // 2)) + b


def hash_path(path, seed):
    """FPakFile::HashPath - FNV-1a 64 over the lowercased UTF-16 path."""
    h = (0xcbf29ce484222325 + seed) & M64
    for b in path.lower().encode('utf-16-le'):
        h = ((h ^ b) * 0x100000001b3) & M64
    return h


# ------------------------------------------------------------------- entries

class Entry:
    __slots__ = ('offset', 'size', 'usize', 'cmethod', 'blocks', 'encrypted',
                 'blocksize', 'sha')

    def __init__(self):
        self.offset = 0
        self.size = 0
        self.usize = 0
        self.cmethod = 0
        self.blocks = []
        self.encrypted = 0
        self.blocksize = 0
        self.sha = b'\0' * 20


def _read_entry_full(r):
    e = Entry()
    e.offset = r.u64(); e.size = r.u64(); e.usize = r.u64(); e.cmethod = r.u32()
    e.sha = r.raw(20)
    if e.cmethod != 0:
        for _ in range(r.u32()):
            e.blocks.append((r.u64(), r.u64()))
    e.encrypted = r.u8(); e.blocksize = r.u32()
    return e


def _write_entry_full(e):
    b = struct.pack('<QQQI', e.offset, e.size, e.usize, e.cmethod) + e.sha
    if e.cmethod != 0:
        b += struct.pack('<I', len(e.blocks))
        for a, c in e.blocks:
            b += struct.pack('<QQ', a, c)
    return b + struct.pack('<BI', e.encrypted, e.blocksize)


def _decode_entry(buf, off):
    """Decode one FPakEntry from the primary index's encoded-entry blob."""
    r = R(buf, off)
    flags = r.u32()
    e = Entry()
    e.cmethod = (flags >> 23) & 0x3F
    e.encrypted = (flags >> 22) & 1
    nblocks = (flags >> 6) & 0xFFFF
    e.blocksize = flags & 0x3F
    e.blocksize = r.u32() if e.blocksize == 0x3F else e.blocksize << 11
    e.offset = r.u32() if flags & (1 << 31) else r.u64()
    e.usize = r.u32() if flags & (1 << 30) else r.u64()
    e.size = (r.u32() if flags & (1 << 29) else r.u64()) if e.cmethod else e.usize
    if e.cmethod and nblocks:
        e.blocks = [None] * nblocks   # real offsets come from the inline header
    return e


def _encode_entry(e):
    """FPakEntry::Encode - only the uncompressed case is exercised by the writer."""
    off32 = e.offset <= 0xFFFFFFFF
    us32 = e.usize <= 0xFFFFFFFF
    sz32 = e.size <= 0xFFFFFFFF
    packed_bs = 0
    if e.cmethod:
        if e.blocksize and (e.blocksize >> 11) <= 0x3E and (e.blocksize & 0x7FF) == 0:
            packed_bs = e.blocksize >> 11
        else:
            packed_bs = 0x3F
    flags = (packed_bs
             | (len(e.blocks) << 6)
             | (e.encrypted << 22)
             | (e.cmethod << 23)
             | ((1 << 31) if off32 else 0)
             | ((1 << 30) if us32 else 0)
             | ((1 << 29) if sz32 else 0))
    out = struct.pack('<I', flags & 0xFFFFFFFF)
    if packed_bs == 0x3F:
        out += struct.pack('<I', e.blocksize)
    out += struct.pack('<I' if off32 else '<Q', e.offset)
    out += struct.pack('<I' if us32 else '<Q', e.usize)
    if e.cmethod:
        out += struct.pack('<I' if sz32 else '<Q', e.size)
    return out


# -------------------------------------------------------------------- reader

class Pak:
    def __init__(self, path):
        self.path = path
        self.f = open(path, 'rb')
        self.f.seek(0, 2)
        size = self.f.tell()
        self.f.seek(max(0, size - 400))
        tail = self.f.read()
        foff = None
        for i in range(len(tail) - 4, -1, -1):
            if struct.unpack_from('<I', tail, i)[0] == MAGIC:
                foff = i
                break
        if foff is None:
            raise ValueError('%s is not a .pak file' % path)
        ft = tail[foff:]
        self.version = struct.unpack_from('<I', ft, 4)[0]
        idx_off, idx_size = struct.unpack_from('<QQ', ft, 8)
        self.methods = ['None']
        names_raw = ft[44:]
        for i in range(0, len(names_raw) - 31, 32):
            nm = names_raw[i:i + 32].split(b'\0')[0].decode('ascii', 'replace')
            if nm:
                self.methods.append(nm)
        self.f.seek(idx_off)
        idx = self.f.read(idx_size)
        r = R(idx)
        self.mount = r.fstring()
        self.count = r.u32()
        self.files = {}
        if self.version >= 10:
            self.seed = r.u64()
            if r.i32():
                r.i64(); r.i64(); r.raw(20)
            if not r.i32():
                raise ValueError('pak has no full directory index')
            fdoff, fdsize = r.i64(), r.i64()
            r.raw(20)
            encoded = r.raw(r.i32())
            legacy = [_read_entry_full(r) for _ in range(r.i32())]
            self.f.seek(fdoff)
            dr = R(self.f.read(fdsize))
            for _ in range(dr.i32()):
                dname = dr.fstring()
                for _ in range(dr.i32()):
                    fname = dr.fstring()
                    eoff = dr.i32()
                    self.files[dname + fname] = (legacy[eoff & 0x7FFFFFFF]
                                                 if eoff < 0 else _decode_entry(encoded, eoff))
        else:
            self.seed = 0
            for _ in range(self.count):
                self.files[r.fstring()] = _read_entry_full(r)

    def close(self):
        self.f.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def read(self, name, oodle=None):
        """Return the decompressed bytes of one entry."""
        e = self.files[name]
        self.f.seek(e.offset)
        rr = R(self.f.read(4096))
        ee = _read_entry_full(rr)
        data_start = e.offset + rr.o
        if ee.cmethod == 0:
            self.f.seek(data_start)
            return self.f.read(ee.usize)
        method = self.methods[ee.cmethod]
        # Block offsets are stored either relative to the entry or absolute.
        base = e.offset if ee.blocks[0][0] < rr.o + 64 else 0
        bs = ee.blocksize or ee.usize
        out = bytearray()
        for a, b in ee.blocks:
            self.f.seek(base + a)
            chunk = self.f.read(b - a)
            out += _decompress(method, chunk, min(bs, ee.usize - len(out)), oodle)
        return bytes(out[:ee.usize])


def _decompress(method, data, usize, oodle):
    m = method.lower()
    if m == 'zlib':
        import zlib
        return zlib.decompress(data)
    if m == 'gzip':
        import gzip
        return gzip.decompress(data)
    if m == 'oodle':
        if oodle is None:
            raise RuntimeError('this entry is Oodle-compressed; pass oodle=<decompressor>')
        return oodle(data, usize)
    raise RuntimeError('unsupported pak compression %r' % method)


# -------------------------------------------------------------------- writer

def write_pak(out_path, files, mount_point='../../../ReadyOrNot/', seed=0x5A5A5A5A):
    """Write an uncompressed version-11 pak.

    `files` maps a mount-relative path (forward slashes, e.g.
    'Config/Difficulties/HardDifficulty.ini') to its bytes.
    """
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or '.', exist_ok=True)
    names = sorted(files)
    entries = {}
    with open(out_path, 'wb') as f:
        for name in names:
            data = files[name]
            e = Entry()
            e.size = e.usize = len(data)
            e.cmethod = 0
            e.sha = hashlib.sha1(data).digest()
            record = _write_entry_full(e)          # inline header stores offset 0
            e.offset = f.tell()
            f.write(record)
            f.write(data)
            entries[name] = e

        # encoded entry blob + per-file offset into it
        encoded = bytearray()
        enc_off = {}
        for name in names:
            enc_off[name] = len(encoded)
            encoded += _encode_entry(entries[name])

        # full directory index: every intermediate directory gets its own record
        dirs = {}
        for name in names:
            d, _, fn = name.rpartition('/')
            d = (d + '/') if d else '/'
            dirs.setdefault(d, {})[fn] = enc_off[name]
            # make sure parent directories exist as (possibly empty) records
            parts = d.strip('/').split('/') if d != '/' else []
            for i in range(len(parts)):
                dirs.setdefault('/'.join(parts[:i + 1]) + '/', {})
        fdi = bytearray(struct.pack('<i', len(dirs)))
        for d in sorted(dirs):
            fdi += fstring(d)
            fdi += struct.pack('<i', len(dirs[d]))
            for fn in sorted(dirs[d]):
                fdi += fstring(fn) + struct.pack('<i', dirs[d][fn])

        # path hash index
        phi = bytearray(struct.pack('<i', len(names)))
        for name in names:
            phi += struct.pack('<Q', hash_path(name, seed)) + struct.pack('<i', enc_off[name])

        phi_off = f.tell()
        f.write(phi)
        fdi_off = f.tell()
        f.write(fdi)

        primary = bytearray()
        primary += fstring(mount_point)
        primary += struct.pack('<I', len(names))
        primary += struct.pack('<Q', seed)
        primary += struct.pack('<i', 1)
        primary += struct.pack('<qq', phi_off, len(phi)) + hashlib.sha1(bytes(phi)).digest()
        primary += struct.pack('<i', 1)
        primary += struct.pack('<qq', fdi_off, len(fdi)) + hashlib.sha1(bytes(fdi)).digest()
        primary += struct.pack('<i', len(encoded)) + bytes(encoded)
        primary += struct.pack('<i', 0)           # no non-encoded entries

        idx_off = f.tell()
        f.write(primary)

        footer = b'\0' * 16                        # EncryptionKeyGuid
        footer += b'\0'                            # bEncryptedIndex
        footer += struct.pack('<I', MAGIC)
        footer += struct.pack('<I', VERSION)
        footer += struct.pack('<qq', idx_off, len(primary))
        footer += hashlib.sha1(bytes(primary)).digest()
        footer += b'\0' * (32 * MAX_METHODS)       # all entries uncompressed
        assert len(footer) == FOOTER_SIZE, len(footer)
        f.write(footer)
    return out_path
