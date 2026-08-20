"""A tiny, comment-preserving editor for Unreal .ini files.

Ready or Not's difficulty configs rely on things a normal ini parser
destroys: inline `;` comments that document each knob, duplicate keys
inside one section (the last one wins), and section ordering.  So this
works on raw lines and only rewrites the right-hand side of a key.
"""
import re

_SECTION = re.compile(r'^\s*\[(?P<name>[^\]]*)\]\s*$')
# key = value ; trailing comment
# Dots are part of the key: the morale settings are named like
# FireWeaponMorale.Gain and AIKilledMorale.Damage.
_KV = re.compile(r'^(?P<lead>\s*)(?P<key>[A-Za-z_][A-Za-z0-9_.]*)(?P<mid>\s*=\s*)'
                 r'(?P<val>[^;\r\n]*?)(?P<tail>\s*(?:;.*)?)$')


class Section:
    def __init__(self, name, header_line=None):
        self.name = name
        self.header = header_line          # None for the implicit pre-first section
        self.lines = []                    # raw lines, without the header

    def keys(self):
        """Yield (index, key, value, match) for every key line."""
        for i, line in enumerate(self.lines):
            m = _KV.match(line.rstrip('\r\n'))
            if m:
                yield i, m.group('key'), m.group('val').strip(), m

    def get(self, key):
        found = None
        for _, k, v, _m in self.keys():
            if k.lower() == key.lower():
                found = v                  # last wins, like UE
        return found

    def has(self, key):
        return self.get(key) is not None

    def set(self, key, value):
        """Rewrite every occurrence of `key`, keeping its inline comment.

        Appends the key at the end of the section if it is not present.
        """
        value = _fmt(value)
        hit = False
        for i, k, _v, m in list(self.keys()):
            if k.lower() != key.lower():
                continue
            hit = True
            eol = _eol(self.lines[i])
            self.lines[i] = (m.group('lead') + m.group('key') + m.group('mid')
                             + value + m.group('tail').rstrip() + eol)
        if not hit:
            eol = self._eol_style()
            while self.lines and not self.lines[-1].strip():
                self.lines.pop()
            self.lines.append('%s = %s%s' % (key, value, eol))
            self.lines.append(eol)
        return hit

    def _eol_style(self):
        for line in self.lines:
            if line.endswith('\r\n'):
                return '\r\n'
            if line.endswith('\n'):
                return '\n'
        return '\r\n'


def _eol(line):
    if line.endswith('\r\n'):
        return '\r\n'
    if line.endswith('\n'):
        return '\n'
    return ''


def _fmt(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, float):
        s = ('%.6f' % v).rstrip('0')
        return s + '0' if s.endswith('.') else s
    return str(v)


class Ini:
    def __init__(self, text):
        self.sections = []
        cur = Section('', None)
        self.sections.append(cur)
        for line in text.splitlines(keepends=True):
            m = _SECTION.match(line.rstrip('\r\n'))
            if m:
                cur = Section(m.group('name'), line)
                self.sections.append(cur)
            else:
                cur.lines.append(line)

    @classmethod
    def loads(cls, data):
        if isinstance(data, bytes):
            data = data.decode('utf-8-sig', 'replace')
        return cls(data)

    def dumps(self):
        out = []
        for s in self.sections:
            if s.header is not None:
                out.append(s.header)
            out.extend(s.lines)
        return ''.join(out)

    def dump_bytes(self):
        return self.dumps().encode('utf-8')

    def section(self, name, create=False):
        for s in self.sections:
            if s.name.lower() == name.lower():
                return s
        if not create:
            return None
        eol = '\r\n'
        s = Section(name, '[%s]%s' % (name, eol))
        self.sections.append(s)
        return s

    def named_sections(self):
        return [s for s in self.sections if s.header is not None]

    def prepend_banner(self, text):
        """Put a comment block above everything else."""
        pre = self.sections[0]
        eol = '\r\n'
        banner = [('; ' + ln).rstrip() + eol for ln in text.splitlines()]
        pre.lines = banner + [eol] + pre.lines
