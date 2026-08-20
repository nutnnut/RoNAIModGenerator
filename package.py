"""Build the distributable zip.

    python package.py                 # everything bundled, runs on a bare PC
    python package.py --no-python     # smaller, needs Python 3.11+ installed
    python package.py --no-oodle      # smaller, downloads the DLL on first run

The result is one folder inside one zip.  Unpack it anywhere, double-click
"MAX SUSPECT Generator.cmd", done - there is no installer and nothing is
written outside the folder until you press Build.
"""
import argparse
import io
import os
import shutil
import sys
import urllib.request
import zipfile

import ronoodle

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = 'RoNAIModGenerator'
VERSION = '1.0'

# The embeddable build is a plain zip of a working interpreter - no installer,
# no registry, no PATH.  Exactly what we want to drop into a mod release.
PY_VERSION = '3.12.8'
PY_URL = ('https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip'
          % (PY_VERSION, PY_VERSION))

# Everything the tool needs at runtime.  out/, settings.json, __pycache__ and
# the git metadata are all deliberately absent.
PAYLOAD = [
    'MAX SUSPECT Generator.cmd',
    'Uninstall.cmd',
    'build.cmd',
    'README.md',
    'config.toml',
    'ai_options.json',
    'app.py',
    'gamedir.py',
    'generate.py',
    'paths.py',
    'presets.py',
    'ronoodle.py',
    'ronpak.py',
    'uini.py',
    'uninstall.py',
    'ui.html',
]


def fetch_python(dest):
    """Unpack the embeddable interpreter into dest/runtime/python."""
    target = os.path.join(dest, 'runtime', 'python')
    os.makedirs(target, exist_ok=True)
    print('[python] %s' % PY_URL)
    with urllib.request.urlopen(PY_URL, timeout=120) as r:
        blob = r.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        z.extractall(target)

    # The embeddable build reads its whole sys.path from this file and ignores
    # the script's own directory, so the tool's modules have to be named here
    # or every import fails.
    pth = [f for f in os.listdir(target) if f.endswith('._pth')]
    if not pth:
        raise RuntimeError('no ._pth in the embeddable zip - layout changed?')
    p = os.path.join(target, pth[0])
    with open(p, 'r', encoding='utf-8') as f:
        lines = [l.rstrip('\n') for l in f]
    for extra in ('..' + os.sep + '..', 'import site'):
        if extra not in lines:
            lines.append(extra)
    with open(p, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('[python] %s -> runtime/python (%d files)'
          % (PY_VERSION, len(os.listdir(target))))


def fetch_oodle(dest):
    src = ronoodle.ensure_dll()
    shutil.copy2(src, os.path.join(dest, 'oo2core.dll'))
    print('[oodle]  bundled %s' % os.path.basename(src))


def stage(opts):
    out = os.path.join(HERE, 'dist')
    root = os.path.join(out, NAME)
    if os.path.exists(root):
        shutil.rmtree(root)
    os.makedirs(root)

    for rel in PAYLOAD:
        src = os.path.join(HERE, rel)
        if not os.path.exists(src):
            raise SystemExit('missing payload file: %s' % rel)
        shutil.copy2(src, os.path.join(root, rel))
    print('[files]  %d' % len(PAYLOAD))

    if opts.oodle:
        fetch_oodle(root)
    if opts.python:
        fetch_python(root)

    with open(os.path.join(root, 'READ ME FIRST.txt'), 'w',
              encoding='utf-8') as f:
        f.write(FIRST_RUN % {
            'py': ('Included - nothing to install.' if opts.python else
                   'Not included. Install Python 3.11 or newer first:\n'
                   '  https://www.python.org/downloads/  (tick "Add python.exe to PATH")'),
            'oodle': ('Included.' if opts.oodle else
                      'Downloaded automatically the first time you build.'),
        })
    return out, root


FIRST_RUN = r"""MAX SUSPECT GENERATOR
=====================

1. Unpack this folder anywhere you like. It does not have to live in the
   game folder - the game is found through Steam.
2. Double-click "MAX SUSPECT Generator.cmd".
3. Your browser opens. Pick a preset, press Build.

Python:  %(py)s
Oodle:   %(oodle)s

The mod is installed as one file:
  ...\Ready Or Not\ReadyOrNot\Content\Paks\pakchunk9999-Mods_MaxSuspect_P.pak

To remove it, run Uninstall.cmd, or just delete that file.

Nothing is written outside this folder until you press Build, and nothing is
added to the registry or to PATH. Delete the folder to remove the tool.

Verify it loaded: the difficulty select screen shows the preset name under the
difficulty, e.g. "MaxSuspectGen: MAX SUSPECT".
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--no-python', dest='python', action='store_false',
                    help='do not bundle the embeddable interpreter')
    ap.add_argument('--no-oodle', dest='oodle', action='store_false',
                    help='do not bundle oo2core.dll')
    opts = ap.parse_args()

    out, root = stage(opts)
    tag_parts = [VERSION]
    if not opts.python:
        tag_parts.append('nopython')
    if not opts.oodle:
        tag_parts.append('nooodle')
    tag = '-'.join(tag_parts)
    zpath = os.path.join(out, '%s-%s.zip' % (NAME, tag))
    if os.path.exists(zpath):
        os.remove(zpath)
    n = 0
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for base, _, files in os.walk(root):
            for fn in files:
                full = os.path.join(base, fn)
                z.write(full, os.path.relpath(full, os.path.dirname(root)))
                n += 1
    print('\n%s\n  %d files, %.1f MB'
          % (zpath, n, os.path.getsize(zpath) / 1048576.0))


if __name__ == '__main__':
    sys.exit(main())
