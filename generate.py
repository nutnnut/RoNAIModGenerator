"""MAX SUSPECT mod generator for Ready or Not - core engine.

Reads the *current* stock difficulty configs straight out of the game's
.pak files, rewrites the values you asked for, and packs the result into a
mod .pak.  Nothing is hard-coded per map, so re-running this after a game
update automatically covers newly added maps and spawn groups.

Normally you drive this from the web UI (`MaxSuspectGen.cmd`).  The command
line still works for scripted builds:

    python generate.py                 # build + deploy using config.toml
    python generate.py --dry-run       # show what would change, write nothing
    python generate.py --list-maps     # print the maps the game exposes
"""
import argparse
import os
import re
import shutil
import sys
import time

import paths
import ronoodle
import ronpak
import uini

HERE = os.path.dirname(os.path.abspath(__file__))
# Output goes next to the tool when the folder is writable, and into
# %LOCALAPPDATA% when it is not - see paths.py.
OUT = paths.data_file('out')

DIFF_DIR = 'ReadyOrNot/Config/Difficulties/'
PAK_DIFF_DIR = 'Config/Difficulties/'

# MinSuspects, MaxCivilians_Group3, ...
COUNT_KEY = re.compile(r'^(Min|Max)(Suspects|Civilians)(?:_Group(\d+))?$', re.I)

# Only the shipping chunks count as a source of vanilla data.  Our own output
# lives in the same folder and would otherwise be read back in, compounding
# every setting on each rebuild - and other people's mods would leak in too.
STOCK_PAK = re.compile(r'^pakchunk\d+-Windows(Server)?(_\d+_P)?\.pak$', re.I)

MARKER_KEY = 'DifficultySubtextKey'

# MaxTraps counts pre-placed and suspect-placed together, so it must never end
# up below the pre-placed numbers.
TRAP_COUNT_KEYS = ['MaxTraps', 'MinTrapsPrePlaced', 'MaxTrapsPrePlaced']


# --------------------------------------------------------------------- input

def load_config(path):
    """Read config.toml, resolving 'auto' (or a stale path) to the real install.

    Keeps the tool runnable from anywhere - nothing here assumes it lives
    inside the game folder.
    """
    import tomllib
    import gamedir
    with open(path, 'rb') as f:
        conf = tomllib.load(f)
    src = conf.setdefault('source', {})
    want = src.get('game_dir', '')
    src['game_dir'] = gamedir.detect(None if want in ('', 'auto') else want)
    mod = conf.setdefault('mod', {})
    if mod.get('deploy_to', '') in ('', 'auto'):
        mod['deploy_to'] = gamedir.paks_dir(src['game_dir'])
    return conf


def find_stock_difficulties(game_dir, wanted, oodle, progress=None):
    """Pull the requested difficulty .ini files out of the shipping paks."""
    paks_dir = os.path.join(game_dir, 'ReadyOrNot', 'Content', 'Paks')
    if not os.path.isdir(paks_dir):
        raise SystemExit('No ReadyOrNot\\Content\\Paks folder under %s' % game_dir)
    pak_files = sorted(p for p in os.listdir(paks_dir) if STOCK_PAK.match(p))
    if not pak_files:
        raise SystemExit('No shipping pakchunk files found in %s' % paks_dir)
    found = {}
    for name in pak_files:
        if progress:
            progress(name)
        try:
            pk = ronpak.Pak(os.path.join(paks_dir, name))
        except Exception:
            continue
        with pk:
            for key in pk.files:
                norm = key.replace('\\', '/')
                if DIFF_DIR not in norm and PAK_DIFF_DIR not in norm:
                    continue
                stem = os.path.splitext(os.path.basename(norm))[0]
                if wanted and stem not in wanted:
                    continue
                found[stem] = (name, pk.read(key, oodle=oodle))
    missing = [w for w in wanted if w not in found]
    if missing:
        raise SystemExit('Could not find these difficulties in the game paks: %s'
                         % ', '.join(missing))
    return found


def collect_difficulties(game_dir, oodle):
    """Every stock difficulty file, as {name: (pak, bytes)}."""
    return find_stock_difficulties(game_dir, [], oodle)


def list_available_difficulties(game_dir, oodle):
    return sorted(collect_difficulties(game_dir, oodle))


DOCS_FILE = os.path.join(HERE, 'ai_options.json')
_GROUP_KEY = re.compile(r'_Group\d+$', re.I)


def load_docs():
    """Community documentation for the AI options, keyed by lowercase name."""
    try:
        import json
        with open(DOCS_FILE, 'r', encoding='utf-8') as f:
            groups = json.load(f)
    except (OSError, ValueError):
        return {}
    out = {}
    for grp in groups:
        for opt in grp.get('options', []):
            key = opt.get('key')
            if key:
                out[key.lower()] = {'name': key, 'group': grp.get('name', ''),
                                    'doc': opt.get('description') or ''}
    return out


def global_key_catalogue(raw, docs=None):
    """Every setting the app's key picker offers.

    Two sources, merged: the [Global] block of the difficulty file that is
    installed right now (authoritative for what exists and its stock value)
    and the community documentation (authoritative for what a key means).
    Keys the docs describe but the stock file omits are still offered - the
    game reads them, it just does not set them by default.
    """
    docs = load_docs() if docs is None else docs
    ini = uini.Ini.loads(raw)
    sec = ini.section('Global')
    out, seen = [], set()
    for _i, key, val, m in (sec.keys() if sec else []):
        low = key.lower()
        if low in seen:
            continue
        seen.add(low)
        info = docs.get(low, {})
        out.append({'key': key, 'value': val,
                    'comment': m.group('tail').strip().lstrip(';').strip(),
                    'doc': info.get('doc', ''), 'group': info.get('group', ''),
                    'in_file': True})
    for low, info in docs.items():
        # The spawn-group keys are per-map; offering all 64 of them in a
        # global picker would bury everything else.
        if low in seen or _GROUP_KEY.search(low):
            continue
        out.append({'key': info.get('name') or low, 'value': '',
                    'comment': '', 'doc': info.get('doc', ''),
                    'group': info.get('group', ''), 'in_file': False})
    out.sort(key=lambda d: d['key'].lower())
    return out


# ------------------------------------------------------------------- helpers

def _num(text):
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        try:
            return float(str(text).strip())
        except (TypeError, ValueError):
            return None


def _scaled_count(vanilla, factor):
    """Scale a spawn count, never turning a populated slot into an empty one."""
    v = _num(vanilla)
    if v is None:
        return None
    out = int(round(v * factor))
    if v > 0 and out < 1:
        out = 1
    return max(out, 0)


def is_map_section(sec):
    """A map section is any section that carries suspect/civilian counts."""
    return any(COUNT_KEY.match(k) for _i, k, _v, _m in sec.keys())


# ------------------------------------------------------------------ rewriting

def apply_counts(sec, cfg, kind, log, stats=None, include_groups=False):
    """Rewrite Min/Max<kind>[_GroupN] in one section.

    mode "multiply" scales whatever the map already declares; mode "fixed"
    writes absolute numbers.

    `include_groups` is off by default and that matters.  A per-group value
    is bounded by the spawn points that group actually contains, and asking a
    group for far more than it holds makes the map spawn *nothing*.  The
    reliable way to raise counts is to turn UseSpawnGroups off and let the
    flat per-map total drive spawning - which is what every working
    high-count mod does.  See `rewrite`.
    """
    mode = cfg.get('mode', 'off')
    if not cfg.get('enable', True) or mode == 'off':
        return
    factor = float(cfg.get('factor', 1.0))
    cap = int(cfg.get('cap', 0) or 0)
    for _i, key, val, _m in list(sec.keys()):
        m = COUNT_KEY.match(key)
        if not m or m.group(2).lower() != kind.lower():
            continue
        is_min = m.group(1).lower() == 'min'
        grouped = m.group(3) is not None
        if grouped and not include_groups:
            continue
        if mode == 'multiply':
            want = _scaled_count(val, factor)
        else:
            want = cfg['group_min' if grouped else 'total_min'] if is_min \
                else cfg['group_max' if grouped else 'total_max']
        if want is None:
            continue
        if cap:
            want = min(int(want), cap)
        if str(want) != str(val).strip():
            log.append('    %-28s %s -> %s' % (key, val, want))
        sec.set(key, want)
        if stats is not None and not grouped:
            stats['%s_%s' % (kind.lower(), 'min' if is_min else 'max')] = (
                _num(val), _num(want))


def apply_traps(sec, cfg, log, is_global=False):
    """Rewrite the trap keys in one section.

    Only ten maps declare traps; everything else inherits [Global], which is
    why "all maps" is mostly a matter of raising the global numbers and then
    bringing the maps that override them up to the same level.
    """
    mode = cfg.get('mode', 'vanilla')
    factor = float(cfg.get('factor', 1.0))
    if mode == 'vanilla' and factor == 1.0:
        return
    has_any = is_global or any(sec.has(k) for k in TRAP_COUNT_KEYS) or sec.has('TrapType')
    if not has_any:
        return

    if mode == 'removed':
        for k in TRAP_COUNT_KEYS:
            if is_global or sec.has(k):
                sec.set(k, 0)
                log.append('    %-28s -> 0 (traps removed)' % k)
        return

    if mode == 'all':
        base = int(cfg.get('base', 6))
        wanted = {'MaxTraps': base, 'MaxTrapsPrePlaced': base,
                  'MinTrapsPrePlaced': max(1, base // 2)}
        for k, v in wanted.items():
            if is_global or sec.has(k):
                cur = _num(sec.get(k))
                if cur is None or cur < v:
                    sec.set(k, v)
                    log.append('    %-28s %s -> %s (traps everywhere)' % (k, cur, v))
        types = cfg.get('types')
        if types and (is_global or sec.has('TrapType')):
            sec.set('TrapType', types)
            log.append('    %-28s -> %s' % ('TrapType', types))

    if factor != 1.0:
        for k in TRAP_COUNT_KEYS:
            cur = _num(sec.get(k))
            if cur is None:
                continue
            new = max(0, int(round(cur * factor)))
            if cur > 0 and new < 1:
                new = 1
            if new != cur:
                sec.set(k, new)
                log.append('    %-28s %s -> %s (traps x%s)' % (k, cur, new, factor))
    # keep the total at least as large as the pre-placed count it contains
    mx = _num(sec.get('MaxTraps'))
    pre = _num(sec.get('MaxTrapsPrePlaced'))
    if mx is not None and pre is not None and pre > mx:
        sec.set('MaxTraps', pre)


def _apply_scales(sec, scales, log, note):
    """Multiply the existing value of each key, where the key exists.

    A key written without a decimal point is a count - roamers, traps - and
    has to stay whole; 3 roamers times 1.5 is 5, not 4.5.
    """
    for k, factor in scales.items():
        raw = sec.get(k)
        cur = _num(raw)
        if cur is None:
            continue
        new = float(cur) * float(factor)
        if isinstance(cur, int) and '.' not in str(raw):
            new = int(round(new))
        else:
            new = round(new, 4)
            if float(new).is_integer() and isinstance(cur, int):
                new = int(new)
        sec.set(k, new)
        log.append('    %-28s %s -> %s (%s)' % (k, cur, new, note))


def rewrite(ini, conf, diff_name, log):
    susp = conf.get('suspects', {})
    civ = conf.get('civilians', {})
    opts = conf.get('options', {})
    keep_groups = opts.get('spawn_groups', 'flat') == 'keep'
    touches_counts = any(c.get('enable', True) and c.get('mode', 'off') != 'off'
                         for c in (susp, civ))
    g = ini.section('Global', create=True)

    # ---- [Global] fallback counts ---------------------------------------
    glog = []
    apply_counts(g, susp, 'Suspects', glog)
    apply_counts(g, civ, 'Civilians', glog)
    apply_traps(g, conf.get('traps', {}), glog, is_global=True)

    # ---- roaming ---------------------------------------------------------
    roam = conf.get('roaming', {})
    propagate = {}
    if roam.get('enable', True):
        for k, v in roam.items():
            if k != 'enable':
                g.set(k, v)
                propagate[k] = v

    # ---- free-form [Global] overrides -----------------------------------
    for k, v in conf.get('global', {}).items():
        before = g.get(k)
        g.set(k, v)
        if str(before).strip() != str(v):
            glog.append('    %-28s %s -> %s' % (k, before, v))
        propagate[k] = v
    for k, v in conf.get('global_by_difficulty', {}).get(diff_name, {}).items():
        g.set(k, v)
        propagate[k] = v

    # Set only where the key already exists.  Some keys live in map sections
    # under a different name than in [Global] (MaxMorale is SuspectMaxMorale's
    # map-local alias), and inventing a [Global] entry the game never reads is
    # a worse bet than leaving it out.
    for k, v in conf.get('global_if_present', {}).items():
        if g.has(k):
            g.set(k, v)
            glog.append('    %-28s -> %s' % (k, v))
        propagate[k] = v

    # ---- scaled keys -----------------------------------------------------
    # global_scale      : multiply every occurrence, keeping per-map variation
    # global_scale_flat : multiply the [Global] value, then force that one
    #                     number everywhere (a "consistent everywhere" knob)
    _apply_scales(g, conf.get('global_scale', {}), glog, 'scaled')
    for k, factor in conf.get('global_scale_flat', {}).items():
        cur = _num(g.get(k))
        if cur is None:
            continue
        new = round(float(cur) * float(factor), 4)
        g.set(k, new)
        propagate[k] = new
        glog.append('    %-28s %s -> %s (flat)' % (k, cur, new))
    if glog:
        log.append('  [Global]')
        log.extend(glog)

    if not opts.get('apply_global_to_map_sections', True):
        propagate = {}
    per_map_scale = conf.get('global_scale', {}) if \
        opts.get('apply_global_to_map_sections', True) else {}

    # ---- every map section ----------------------------------------------
    maps = []
    for sec in ini.named_sections():
        if sec.name.lower() == 'global' or not is_map_section(sec):
            continue
        seclog = []
        stats = {}
        apply_counts(sec, susp, 'Suspects', seclog, stats, keep_groups)
        apply_counts(sec, civ, 'Civilians', seclog, stats, keep_groups)
        apply_traps(sec, conf.get('traps', {}), seclog)
        # With spawn groups on, the per-group numbers - not the totals - decide
        # how many bodies appear, and each group is capped by the spawn points
        # it owns.  Switching the map to flat totals is what makes an arbitrary
        # count actually work.
        if not keep_groups and touches_counts and sec.has('UseSpawnGroups') \
                and str(sec.get('UseSpawnGroups')).strip().lower() != 'false':
            sec.set('UseSpawnGroups', False)
            seclog.append('    %-28s -> false (using flat totals)' % 'UseSpawnGroups')
        _apply_scales(sec, per_map_scale, seclog, 'scaled')
        # A map section that redefines a key you configured globally would
        # otherwise silently win, so overwrite it in place (never append).
        for k, v in propagate.items():
            if sec.has(k):
                sec.set(k, v)
                seclog.append('    %-28s -> %s (was map-local)' % (k, v))
        for k, v in conf.get('map', {}).get(sec.name, {}).items():
            sec.set(k, v)
            seclog.append('    %-28s -> %s (map override)' % (k, v))
        maps.append({'name': sec.name, 'stats': stats})
        if seclog:
            log.append('  [%s]' % sec.name)
            log.extend(seclog)
    return maps


def stamp(ini, conf, diff_name, src_pak):
    """Leave a visible fingerprint so a failed load is obvious in-game.

    The banner goes *inside* [Info] rather than above it: a stray block of
    comments before the first section is the kind of thing an ini parser is
    entitled to dislike, and there is nothing to gain by risking it.
    """
    info = ini.section('Info', create=True)
    tag = conf.get('mod', {}).get('marker', '')
    if tag:
        info.set(MARKER_KEY, '"%s"' % tag)
    eol = '\r\n'
    banner = [
        '; Generated by MaxSuspectGen %s' % time.strftime('%Y-%m-%d %H:%M'),
        '; Source: %s :: %s%s.ini' % (src_pak, DIFF_DIR, diff_name),
        '; Edit settings in the app, not in this file.',
    ]
    info.lines = [b + eol for b in banner] + info.lines


# ------------------------------------------------------------------ pipeline

def build(conf, dry_run=False, deploy=True, progress=None, oodle_quiet=True):
    """Run a full generation. Returns a result dict."""
    game_dir = conf['source']['game_dir']
    wanted = list(conf['source']['difficulties'])
    ronoodle.load(quiet=oodle_quiet)
    if progress:
        progress('Reading difficulty data from the game paks...')
    stock = find_stock_difficulties(game_dir, wanted, ronoodle.decompress)

    os.makedirs(os.path.join(OUT, 'vanilla'), exist_ok=True)
    os.makedirs(os.path.join(OUT, 'generated'), exist_ok=True)

    payload = {}
    log = []
    maps_by_diff = {}
    for name in wanted:
        src_pak, raw = stock[name]
        with open(os.path.join(OUT, 'vanilla', name + '.ini'), 'wb') as f:
            f.write(raw)
        ini = uini.Ini.loads(raw)
        log.append('== %s  (from %s)' % (name, src_pak))
        maps = rewrite(ini, conf, name, log)
        maps_by_diff[name] = maps
        stamp(ini, conf, name, src_pak)
        data = ini.dump_bytes()
        payload[PAK_DIFF_DIR + name + '.ini'] = data
        with open(os.path.join(OUT, 'generated', name + '.ini'), 'wb') as f:
            f.write(data)
        if progress:
            progress('%s: %d maps rewritten' % (name, len(maps)))

    result = {
        'log': log,
        'difficulties': wanted,
        'maps': maps_by_diff,
        'map_count': len(maps_by_diff.get(wanted[0], [])) if wanted else 0,
        'pak': None,
        'size': 0,
        'deployed': None,
        'preview_dir': os.path.join(OUT, 'generated'),
    }
    if dry_run:
        return result

    pak_path = os.path.join(OUT, conf['mod']['pak_name'])
    ronpak.write_pak(pak_path, payload)
    verify(pak_path, payload)
    result['pak'] = pak_path
    result['size'] = os.path.getsize(pak_path)
    if progress:
        progress('Packed %s' % os.path.basename(pak_path))

    dest = conf['mod'].get('deploy_to', '')
    if dest and deploy:
        os.makedirs(dest, exist_ok=True)
        target = os.path.join(dest, conf['mod']['pak_name'])
        shutil.copy2(pak_path, target)
        result['deployed'] = target
        if progress:
            progress('Installed to %s' % target)
    return result


def uninstall(conf):
    """Remove any pak this tool has installed, from every known location."""
    removed = []
    names = {conf['mod']['pak_name'], 'pakchunk9999-Mods_MaxSuspect_P.pak'}
    roots = []
    dest = conf['mod'].get('deploy_to', '')
    if dest:
        roots.append(dest)
    paks = os.path.join(conf['source']['game_dir'], 'ReadyOrNot', 'Content', 'Paks')
    roots += [paks, os.path.join(paks, '~mods')]
    for root in roots:
        for n in names:
            p = os.path.join(root, n)
            if os.path.isfile(p):
                os.remove(p)
                removed.append(p)
        if dest and root == dest and os.path.isdir(root) and not os.listdir(root):
            os.rmdir(root)
    return removed


def verify(pak_path, payload):
    """Read the pak back with our own reader and compare every byte."""
    with ronpak.Pak(pak_path) as pk:
        if set(pk.files) != set(payload):
            raise SystemExit('verify failed: file list mismatch in %s' % pak_path)
        for name, data in payload.items():
            if pk.read(name) != data:
                raise SystemExit('verify failed: %s does not round-trip' % name)


# ----------------------------------------------------------------------- cli

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('-c', '--config', default=os.path.join(HERE, 'config.toml'))
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--list-maps', action='store_true')
    ap.add_argument('--no-deploy', action='store_true')
    ap.add_argument('--uninstall', action='store_true')
    ap.add_argument('-q', '--quiet', action='store_true')
    args = ap.parse_args(argv)

    conf = load_config(args.config)
    if args.uninstall:
        for p in uninstall(conf):
            print('removed %s' % p)
        return 0

    say = (lambda m: None) if args.quiet else (lambda m: print(m))
    res = build(conf, dry_run=args.dry_run or args.list_maps,
                deploy=not args.no_deploy, progress=say, oodle_quiet=args.quiet)

    if args.list_maps:
        names = sorted({m['name'] for ms in res['maps'].values() for m in ms})
        print('%d map sections in this game build:' % len(names))
        for n in names:
            print('  ' + n)
        return 0
    if not args.quiet:
        print('\n'.join(res['log']))
    if args.dry_run:
        print('\n[dry run] nothing written. Previews in %s' % res['preview_dir'])
        return 0
    print('\nBuilt %s (%d bytes)' % (os.path.basename(res['pak']), res['size']))
    if res['deployed']:
        print('Installed to %s' % res['deployed'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
