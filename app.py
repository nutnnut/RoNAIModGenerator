"""Local web UI for the MAX SUSPECT generator.

Starts a small server on 127.0.0.1 and opens a browser at it.  Nothing is
sent anywhere: the page talks only to this process, which talks only to your
game folder.

    python app.py            # pick a free port, open the browser
    python app.py --port 8731 --no-browser
"""
import argparse
import http.server
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import traceback
import webbrowser

import gamedir
import paths
import generate
import presets

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = paths.data_file('settings.json')
UI_FILE = os.path.join(HERE, 'ui.html')

TOKEN = secrets.token_urlsafe(24)


def load_settings():
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(s):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(s, f, indent=2)
    except OSError:
        pass


def installed_paks(conf):
    """Where a generated pak is currently sitting, if anywhere."""
    out = []
    game_dir = conf['source']['game_dir']
    if not game_dir:
        return out
    roots = [gamedir.paks_dir(game_dir), gamedir.mods_dir(game_dir)]
    mods = gamedir.mods_dir(game_dir)
    if os.path.isdir(mods):
        roots += [os.path.join(mods, d) for d in os.listdir(mods)
                  if os.path.isdir(os.path.join(mods, d))]
    name = conf['mod']['pak_name']
    for root in roots:
        p = os.path.join(root, name)
        if os.path.isfile(p):
            out.append(p)
    return out


def other_difficulty_mods(game_dir):
    """Other installed paks that also override difficulty data - they conflict."""
    if not game_dir:
        return []
    import ronpak
    hits = []
    mods = gamedir.mods_dir(game_dir)
    roots = [gamedir.paks_dir(game_dir)]
    if os.path.isdir(mods):
        roots.append(mods)
        roots += [os.path.join(mods, d) for d in os.listdir(mods)
                  if os.path.isdir(os.path.join(mods, d))]
    ours = {presets.DEFAULT_PAK_NAME}
    for root in roots:
        if not os.path.isdir(root):
            continue
        for fn in sorted(os.listdir(root)):
            if not fn.lower().endswith('.pak') or fn in ours:
                continue
            if fn.lower().startswith('pakchunk') and '-windows' in fn.lower():
                continue          # shipping chunk
            full = os.path.join(root, fn)
            try:
                with ronpak.Pak(full) as pk:
                    for k in pk.files:
                        low = k.lower().replace('\\', '/')
                        clashes = (
                            'config/difficulties/' in low
                            or low.endswith('ailevaldata.ini')
                            or ('/leveldata/' in low and low.endswith(('.uasset', '.uexp')))
                        )
                        if clashes:
                            hits.append({'path': full, 'entry': k})
                            break
            except Exception:
                continue
    return hits


# ------------------------------------------------------------------- handlers

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'MaxSuspectGen'

    def log_message(self, fmt, *a):
        pass

    # -- plumbing ---------------------------------------------------------
    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode('utf-8')
        elif isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def _guard(self):
        """Only accept API calls carrying this run's token.

        A custom header cannot be set cross-origin without a preflight we
        never answer, so this keeps other pages in the browser from poking
        at the tool.
        """
        if self.headers.get('X-MSG-Token') != TOKEN:
            self._send(403, {'error': 'bad token'})
            return False
        return True

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(n) or b'{}')

    # -- routes -----------------------------------------------------------
    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path in ('/', '/index.html'):
            with open(UI_FILE, 'r', encoding='utf-8') as f:
                html = f.read().replace('__TOKEN__', TOKEN)
            return self._send(200, html, 'text/html; charset=utf-8')
        if path == '/api/init':
            if not self._guard():
                return
            return self._send(200, self.init_payload())
        self._send(404, {'error': 'not found'})

    def do_POST(self):
        if not self._guard():
            return
        path = self.path.split('?', 1)[0]
        try:
            if path == '/api/preview':
                return self._send(200, self.run_build(self._body(), dry_run=True))
            if path == '/api/build':
                return self._send(200, self.run_build(self._body(), dry_run=False))
            if path == '/api/uninstall':
                return self._send(200, self.run_uninstall(self._body()))
            if path == '/api/reveal':
                return self._send(200, self.reveal(self._body()))
            if path == '/api/shutdown':
                threading.Timer(0.3, lambda: os._exit(0)).start()
                return self._send(200, {'ok': True})
        except Exception:
            return self._send(500, {'error': traceback.format_exc(limit=4)})
        self._send(404, {'error': 'not found'})

    # -- work -------------------------------------------------------------
    def init_payload(self):
        saved = load_settings()
        game_dir = gamedir.detect((saved.get('advanced') or {}).get('game_dir'))
        data = presets.catalogue()
        data['saved'] = saved
        data['game_dir'] = game_dir
        data['game_dir_ok'] = gamedir.looks_like_game(game_dir)
        data['game_dir_candidates'] = gamedir.candidates()
        data['difficulties_available'] = []
        data['global_keys'] = []
        data['conflicts'] = []
        if data['game_dir_ok']:
            try:
                import ronoodle
                ronoodle.load(quiet=True)
                stock = generate.collect_difficulties(game_dir, ronoodle.decompress)
                data['difficulties_available'] = sorted(stock)
                ref = ('HardDifficulty' if 'HardDifficulty' in stock
                       else (sorted(stock)[0] if stock else None))
                if ref:
                    data['global_keys'] = generate.global_key_catalogue(stock[ref][1])
            except Exception as exc:
                data['warning'] = str(exc)
            try:
                data['conflicts'] = other_difficulty_mods(game_dir)
            except Exception:
                pass
        return data

    def run_build(self, settings, dry_run):
        conf = presets.build_conf(settings)
        if not conf['source']['game_dir']:
            return {'error': 'Ready or Not was not found. Set the game folder '
                             'in Advanced.'}
        steps = []
        res = generate.build(conf, dry_run=dry_run, deploy=True,
                             progress=steps.append)
        if not dry_run:
            save_settings(settings)
        rows = []
        first = conf['source']['difficulties'][0] if conf['source']['difficulties'] else None
        for m in res['maps'].get(first, []):
            st = m['stats']
            rows.append({
                'map': pretty_map(m['name']),
                'section': m['name'],
                'suspects': fmt_range(st.get('suspects_min'), st.get('suspects_max')),
                'civilians': fmt_range(st.get('civilians_min'), st.get('civilians_max')),
            })
        return {
            'ok': True,
            'dry_run': dry_run,
            'steps': steps,
            'log': res['log'],
            'rows': rows,
            'map_count': len(rows),
            'difficulties': conf['source']['difficulties'],
            'pak': res['pak'],
            'size': res['size'],
            'deployed': res['deployed'],
            'preview_dir': res['preview_dir'],
            'installed': installed_paks(conf),
            'marker': conf['mod']['marker'],
        }

    def run_uninstall(self, settings):
        conf = presets.build_conf(settings)
        return {'ok': True, 'removed': generate.uninstall(conf)}

    def reveal(self, body):
        path = body.get('path') or ''
        if not path:
            return {'ok': False}
        path = os.path.abspath(path)
        if os.path.isfile(path):
            subprocess.Popen(['explorer', '/select,', path])
        elif os.path.isdir(path):
            subprocess.Popen(['explorer', path])
        else:
            return {'ok': False}
        return {'ok': True}


def fmt_range(pair_min, pair_max):
    """Render 'before -> after' for a map's total count."""
    def one(pair):
        if not pair:
            return None
        before, after = pair
        return {'before': before, 'after': after}
    return {'min': one(pair_min), 'max': one(pair_max)}


def pretty_map(section):
    """RoN_Meth_Apartments_BarricadedSuspects_Core -> 'Meth Apartments'."""
    name = section
    for suffix in ('_BarricadedSuspects_Core', '_BombThreat_Core',
                   '_ActiveShooter_Core', '_HostageRescue_Core', '_Core'):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    if name.lower().startswith('ron_'):
        name = name[4:]
    return name.replace('_', ' ')


# ---------------------------------------------------------------------- entry

def free_port(preferred=0):
    if preferred:
        try:
            s = socket.socket()
            s.bind(('127.0.0.1', preferred))
            s.close()
            return preferred
        except OSError:
            pass
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', type=int, default=8731)
    ap.add_argument('--no-browser', action='store_true')
    args = ap.parse_args(argv)

    port = free_port(args.port)
    url = 'http://127.0.0.1:%d/' % port
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print('MAX SUSPECT generator running at %s' % url)
    print('Leave this window open. Close it (or press Ctrl+C) when you are done.')
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nbye')
    return 0


if __name__ == '__main__':
    sys.exit(main())
