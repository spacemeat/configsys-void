'''xbps.py — the Void Linux driver (an example configsys code plugin).

Installs native Void packages via the `xbps-*` tools. Void is a rolling distro, but unlike
Alpine it has a native package *hold* (`xbps-pkgdb -m hold`), so this driver implements a real
lock/unlock — a slightly richer template than a hold-less manager.

This file is the whole "code" half of a configsys plugin: subclass Driver, implement the op
set with real commands, and export `DRIVERS` so the trusted loader registers it. Query ops
need no root; mutations run under sudo. Copy this as a starting point for another package
manager (zypper and apk graduated into base configsys this way).

Beyond the core op set it also implements the batch/enumeration hooks a first-class native
manager carries: `installed_index` (one `xbps-query -l` for the inspect prepass + orphan scan),
`explicit_keys` (`xbps-query -m` — user-installed, for the orphan scan and the System Updates
auto-dep dimming), and the System Updates lane (`upgradable_index` via `xbps-install -un`,
`held_keys` via `xbps-query -H`, and `upgrade_all` = `xbps-install -Suy`), so Void is a full
citizen of `configsys updates` / `upgrade --system` and the TUI System Updates group.

Everything it needs comes from the frozen ABI surface:
    from configsys.plugins import Driver, Result
'''

import re
import shlex

from configsys.plugins import Driver, Result

# An xbps pkgver is "<name>-<version>_<revision>"; the name may contain hyphens (gcc-fortran), so
# anchor the version at the last "-" whose tail is "<digit>…_<rev>" (no interior hyphen).
_PKGVER = re.compile(r'^(.*)-(\d[^-]*_\d+)$')


def _version_from_pkgver(stdout, name):
    '''`xbps-query -p pkgver <name>` prints "<name>-<version>_<revision>" (e.g.
    "vim-9.0.1_1"). Return the "<version>_<revision>" tail for exactly `name`, guarding that
    the char after "<name>-" is a digit (so `gcc` is not satisfied by `gcc-fortran-...`).'''
    prefix = name + '-'
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith(prefix) and line[len(prefix):len(prefix) + 1].isdigit():
            return line[len(prefix):]
    return None


def _split_pkgver(pkgver):
    '''"(name, version_rev)" from a bare pkgver, or (None, None) if it doesn't parse.'''
    m = _PKGVER.match(pkgver.strip())
    return (m.group(1), m.group(2)) if m else (None, None)


class Xbps(Driver):
    name = 'xbps'
    privileged = True
    default_scope = 'system'        # xbps packages are system-wide (a fixed scope)

    # -- read (no root needed) -------------------------------------------

    def installed_index(self):
        # ONE `xbps-query -l` lists every installed package ("ii <pkgver>  <desc>") -> {name: version}.
        # Feeds the batch inspection prepass (one enumeration instead of a probe per unit) + the
        # orphan/coexistence detectors, like apt/dnf/pacman's installed_index.
        r = self.runner.run('xbps-query -l')
        if not r.ok:
            return None
        idx = {}
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:                         # "ii <pkgver> <description…>"
                name, ver = _split_pkgver(parts[1])
                if name:
                    idx.setdefault(name, ver or 'installed')
        return idx

    def explicit_keys(self):
        '''`xbps-query -m` — packages installed MANUALLY (not pulled as dependencies). Feeds the
        orphan scan and the System Updates auto-dep dimming (the manager's "user-chosen" set).'''
        r = self.runner.run('xbps-query -m')
        if not r.ok:
            return None
        out = set()
        for line in r.stdout.splitlines():
            name, _ = _split_pkgver(line)
            if name:
                out.add(name)
        return out

    def get_version(self, rc):
        ver, hit = self._batched_version(rc)            # answer from the one xbps-query -l when batched
        if hit:
            return ver
        r = self.runner.run(f'xbps-query -p pkgver {shlex.quote(rc.name)}')
        return _version_from_pkgver(r.stdout, rc.name) if r.ok else None

    def get_latest(self, rc):
        # -R queries the remote repos (the candidate version).
        r = self.runner.run(f'xbps-query -R -p pkgver {shlex.quote(rc.name)}')
        return _version_from_pkgver(r.stdout, rc.name) if r.ok else None

    def is_locked(self, rc):
        # the `hold` property prints "yes" when the package is held back from upgrades.
        r = self.runner.run(f'xbps-query -p hold {shlex.quote(rc.name)}')
        return bool(r.ok and r.stdout.strip() == 'yes')

    # -- System Updates lane (upgradable / held / bulk) ------------------

    def upgradable_index(self):
        '''{name: (installed, candidate)} from `xbps-install -un` — a dry-run upgrade against the
        CURRENT (already-synced) repo index, no root needed. Rows read "<pkgver> update <arch> …";
        keep the `update` actions (new-dependency `install` rows aren't upgrades). Installed version
        from the local db. None on query failure.'''
        r = self.runner.run('xbps-install -un')
        if not r.ok:
            return None
        installed = self.installed_index() or {}
        idx = {}
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2 or parts[1] != 'update':  # only genuine upgrades, not new deps
                continue
            name, cand = _split_pkgver(parts[0])
            if name:
                idx.setdefault(name, (installed.get(name), cand))
        return idx

    def held_keys(self):
        # `xbps-query -H` lists packages on hold (Void has a real per-package hold, unlike apk).
        r = self.runner.run('xbps-query -H')
        if not r.ok:
            return None
        out = set()
        for line in r.stdout.splitlines():
            s = line.strip()
            if s:
                name, _ = _split_pkgver(s)
                out.add(name or s)
        return out

    def upgrade_all(self):
        # Void is rolling: the safe bulk is a full sync + system upgrade (like pacman -Syu / apk upgrade).
        return self.runner.run('xbps-install -Suy', sudo=True, capture=False)

    # -- mutate (under sudo) ---------------------------------------------

    def install(self, rc):
        return self.runner.run(f'xbps-install -Sy {shlex.quote(rc.name)}',
                               sudo=True, capture=False)

    def uninstall(self, rc):
        return self.runner.run(f'xbps-remove -y {shlex.quote(rc.name)}',
                               sudo=True, capture=False)

    def upgrade(self, rc):
        return self.runner.run(f'xbps-install -Suy {shlex.quote(rc.name)}',
                               sudo=True, capture=False)

    def set_version(self, rc, version):
        # best-effort exact edition (only resolvable while it's still in a configured repo).
        spec = f'{rc.name}-{version}'
        return self.runner.run(f'xbps-install -y {shlex.quote(spec)}',
                               sudo=True, capture=False)

    def lock(self, rc):
        return self.runner.run(f'xbps-pkgdb -m hold {shlex.quote(rc.name)}', sudo=True)

    def unlock(self, rc):
        return self.runner.run(f'xbps-pkgdb -m unhold {shlex.quote(rc.name)}', sudo=True)


# The registration export the trusted loader reads (docs/plugins.md §7a).
DRIVERS = [Xbps]
