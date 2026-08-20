"""Oodle decompressor binding.

Ready or Not's .pak files are Oodle-compressed, so reading the stock
difficulty configs out of them needs the Oodle runtime.  Epic ships it
statically linked inside the game .exe, so we use the freely
redistributable OodleUE build instead (same one FModel / repak use).

The DLL is downloaded once into this folder and reused afterwards.
"""
import ctypes
import os
import shutil
import zipfile

import paths

HERE = os.path.dirname(os.path.abspath(__file__))
# A bundled copy shipped in the zip wins; otherwise we download one into
# whichever folder we are allowed to write to.
_BUNDLED = os.path.join(HERE, "oo2core.dll")
DLL_PATH = _BUNDLED if os.path.exists(_BUNDLED) else paths.data_file("oo2core.dll")

_RELEASES = "https://api.github.com/repos/WorkingRobot/OodleUE/releases"
_ASSET = "msvc-x64-release.zip"
_MEMBER = "bin/oodle-data-shared.dll"

_dec = None
_cmp = None


def ensure_dll(quiet=False):
    """Return a path to a usable oo2core.dll, downloading it if needed."""
    if os.path.exists(DLL_PATH):
        return DLL_PATH
    import json
    import urllib.request

    if not quiet:
        print("[oodle] no local oo2core.dll - fetching OodleUE redistributable...")
    with urllib.request.urlopen(_RELEASES, timeout=60) as r:
        releases = json.load(r)
    url = None
    for rel in releases:
        for a in rel.get("assets", []):
            if a["name"] == _ASSET:
                url = a["browser_download_url"]
                break
        if url:
            break
    if not url:
        raise RuntimeError(
            "Could not find %s in OodleUE releases. Drop any oo2core*.dll next to "
            "this script and rename it oo2core.dll." % _ASSET
        )
    tmp = DLL_PATH + ".zip"
    urllib.request.urlretrieve(url, tmp)
    with zipfile.ZipFile(tmp) as z, z.open(_MEMBER) as src, open(DLL_PATH, "wb") as dst:
        shutil.copyfileobj(src, dst)
    os.remove(tmp)
    if not quiet:
        print("[oodle] saved %s" % DLL_PATH)
    return DLL_PATH


def load(path=None, quiet=False):
    global _dec, _cmp
    if _dec is not None:
        return
    path = path or ensure_dll(quiet=quiet)
    dll = ctypes.CDLL(path, winmode=0)
    _dec = dll.OodleLZ_Decompress
    _dec.restype = ctypes.c_ssize_t
    _dec.argtypes = [
        ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_ssize_t,
        ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_int,
    ]
    _cmp = dll.OodleLZ_Compress
    _cmp.restype = ctypes.c_ssize_t
    _cmp.argtypes = [
        ctypes.c_int, ctypes.c_void_p, ctypes.c_ssize_t, ctypes.c_void_p,
        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_ssize_t,
    ]


def decompress(data, usize):
    if _dec is None:
        load()
    out = ctypes.create_string_buffer(usize)
    n = _dec(data, len(data), out, usize, 1, 0, 0, None, 0, None, None, None, 0, 3)
    if n != usize:
        raise RuntimeError("Oodle decompress returned %d, expected %d" % (n, usize))
    return out.raw[:usize]
