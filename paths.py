"""Where the tool is allowed to write.

Everything normally lives next to the scripts, so the whole thing stays one
self-contained folder you can delete in one go.  That breaks the moment
somebody unpacks the zip somewhere read-only - Program Files, a network share,
or straight out of an archive viewer - so we probe first and fall back to
%LOCALAPPDATA% when the folder will not take a write.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_APP = 'MaxSuspectGen'
_cached = None


def _writable(d):
    probe = os.path.join(d, '.write-probe')
    try:
        os.makedirs(d, exist_ok=True)
        with open(probe, 'w') as f:
            f.write('')
        os.remove(probe)
        return True
    except OSError:
        return False


def data_dir():
    """The folder for generated output, downloads and saved settings."""
    global _cached
    if _cached:
        return _cached
    if _writable(HERE):
        _cached = HERE
    else:
        base = (os.environ.get('LOCALAPPDATA')
                or os.path.join(os.path.expanduser('~'), 'AppData', 'Local'))
        _cached = os.path.join(base, _APP)
        os.makedirs(_cached, exist_ok=True)
    return _cached


def data_file(name):
    return os.path.join(data_dir(), name)


def portable():
    """True when we are writing next to ourselves rather than into AppData."""
    return data_dir() == HERE
