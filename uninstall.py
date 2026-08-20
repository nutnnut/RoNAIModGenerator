"""Remove any pak this tool has installed.

Finds the game the same way the app does, so it works from anywhere.
"""
import os
import sys

import gamedir
import presets

NAMES = [presets.DEFAULT_PAK_NAME, 'pakchunk9999-Mods_MaxSuspect_P.pak']


def targets(game_dir):
    paks = gamedir.paks_dir(game_dir)
    mods = gamedir.mods_dir(game_dir)
    roots = [paks, mods, os.path.join(mods, presets.DEFAULT_MODS_SUBFOLDER)]
    if os.path.isdir(mods):
        roots += [os.path.join(mods, d) for d in os.listdir(mods)
                  if os.path.isdir(os.path.join(mods, d))]
    seen, out = set(), []
    for r in roots:
        for n in dict.fromkeys(NAMES):
            p = os.path.join(r, n)
            if p not in seen:
                seen.add(p)
                out.append(p)
    return out


def main(argv=None):
    game_dir = gamedir.detect(argv[0] if argv else None)
    if not game_dir:
        print('Could not find Ready or Not.')
        print('Pass the game folder as an argument, e.g.')
        print('   python uninstall.py "D:\\SteamLibrary\\steamapps\\common\\Ready Or Not"')
        return 1
    print('Game folder: %s' % game_dir)
    removed = []
    for p in targets(game_dir):
        if os.path.isfile(p):
            try:
                os.remove(p)
                removed.append(p)
                print('Removed %s' % p)
            except OSError as exc:
                print('Could not remove %s (%s)' % (p, exc))
    empty = os.path.join(gamedir.mods_dir(game_dir), presets.DEFAULT_MODS_SUBFOLDER)
    if os.path.isdir(empty) and not os.listdir(empty):
        os.rmdir(empty)
    if not removed:
        print('Nothing to remove - no generated pak was installed.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
