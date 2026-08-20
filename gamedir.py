"""Locate the Ready or Not install without asking the user."""
import os
import re

REL_MARKER = os.path.join('ReadyOrNot', 'Content', 'Paks')
FOLDER = 'Ready Or Not'


def looks_like_game(path):
    return bool(path) and os.path.isdir(os.path.join(path, REL_MARKER))


def _clean(path):
    return os.path.normpath(path) if path else path


def _steam_roots():
    roots = []
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam'),
                          (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam')):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for value in ('SteamPath', 'InstallPath'):
                        try:
                            roots.append(winreg.QueryValueEx(k, value)[0])
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    roots += [r'C:\Program Files (x86)\Steam', r'C:\Program Files\Steam']
    return roots


def _library_paths(steam_root):
    """Every Steam library folder, from libraryfolders.vdf."""
    libs = [steam_root]
    vdf = os.path.join(steam_root, 'steamapps', 'libraryfolders.vdf')
    if os.path.isfile(vdf):
        try:
            with open(vdf, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            libs += re.findall(r'"path"\s+"([^"]+)"', text)
            # very old format: "1" "D:\\Games\\Steam"
            libs += re.findall(r'"\d+"\s+"([A-Za-z]:\\\\[^"]+)"', text)
        except OSError:
            pass
    return [p.replace('\\\\', '\\') for p in libs]


def candidates():
    seen = []
    for root in _steam_roots():
        if not root or not os.path.isdir(root):
            continue
        for lib in _library_paths(root):
            p = os.path.join(lib, 'steamapps', 'common', FOLDER)
            p = _clean(p)
            if p not in seen and looks_like_game(p):
                seen.append(p)
    # last resort: a plain scan of drive roots for a manual/Epic install
    if not seen:
        for drive in 'CDEFGH':
            for base in (r'%s:\Program Files (x86)\Steam\steamapps\common',
                         r'%s:\SteamLibrary\steamapps\common',
                         r'%s:\Games', r'%s:\\'):
                p = os.path.join(base % drive, FOLDER)
                if looks_like_game(p) and p not in seen:
                    seen.append(p)
    return seen


def detect(preferred=None):
    """Best guess at the game directory, or ''."""
    if looks_like_game(preferred):
        return _clean(preferred)
    # the tool usually lives inside the game folder itself
    here = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    if looks_like_game(parent):
        return _clean(parent)
    found = candidates()
    return found[0] if found else ''


def paks_dir(game_dir):
    return os.path.join(game_dir, REL_MARKER)


def mods_dir(game_dir):
    return os.path.join(game_dir, REL_MARKER, '~mods')
