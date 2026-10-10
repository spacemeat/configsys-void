'''Parity with configsys core. Void graduated into core (configsys/drivers/xbps.py + the void/void_musl
os blocks + `xbps:` name entries); this plugin stays as the worked example of an OS plugin, so it must
never CONTRADICT core. Checks:

  1. its os blocks equal core's;
  2. every `component-names: { xbps: … }` entry agrees with what core resolves on Void (a `{}` drop
     must match a component core doesn't offer there);
  3. its Xbps driver behaves exactly like core's — same commands, same parsed answers — over the
     same canned xbps output;
  4. loading it over core changes NO resolution on either Void flavor.

Core is the checkout at $CONFIGSYS_REPO (default: ../configsys beside this repo). Run with core's venv:

    ../configsys/.venv/bin/python -m pytest test/
'''

import importlib.util
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
CORE = Path(os.environ.get('CONFIGSYS_REPO') or PLUGIN.parent / 'configsys').resolve()
sys.path.insert(0, str(CORE))

from configsys import routes                                            # noqa: E402
from configsys.componentObj import ResolvedComponent                    # noqa: E402
from configsys.drivers.xbps import Xbps as CoreXbps                     # noqa: E402
from configsys.layers import materialize_string                         # noqa: E402
from configsys.resolve import ResolveError                              # noqa: E402
from configsys.routes import Resolver                                   # noqa: E402
from configsys.runner import Result                                     # noqa: E402

CORE_ROUTES = str(CORE / 'routes.hu')
PLUGIN_DATA = materialize_string((PLUGIN / 'routes.hu').read_text(encoding='utf-8'))


def _plugin_driver():
    spec = importlib.util.spec_from_file_location('void_plugin_driver', PLUGIN / 'driver.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Xbps


# -- 1. os blocks ---------------------------------------------------------------

def test_os_blocks_match_core():
    cascade = routes.load(CORE_ROUTES)[0]
    for name, blk in PLUGIN_DATA['os'].items():
        assert cascade.blocks.get(name) == blk, f'os block {name!r} differs from core'


# -- 2. name map ----------------------------------------------------------------

@pytest.mark.parametrize('block', ['void', 'void_musl'])
def test_component_names_agree_with_core(block):
    r = Resolver(CORE_ROUTES, block, None, 'x86_64')
    for comp, name in PLUGIN_DATA['component-names']['xbps'].items():
        try:
            units = r.resolve_names([comp])
        except ResolveError:
            units = {}
        own = [u for u in units.values() if u.comp == comp and u.driver == 'xbps']
        if name in ({}, None):
            assert not own, f'plugin drops {comp} on Void, but core offers xbps:{own[0].name}'
        else:
            assert own, f'plugin renames {comp} -> {name}, but core has no xbps unit for it on {block}'
            assert own[0].name == name, f'{comp}: plugin says {name}, core says {own[0].name}'


# -- 3. driver behavior -----------------------------------------------------------

INSTALLED = ('ii acl-2.3.2_1                      Access Control List filesystem support\n'
             'ii gcc-fortran-14.2.1+20250405_4   GNU Compiler Collection - Fortran\n'
             'ii curl-8.20.0_1                    Client that groks URLs\n')
REMOTE = ('[-] 0ad-0.27.1_6                                       Historically-based RTS\n'
          '[*] curl-8.22.0_1                                      Client that groks URLs\n')
UPDATES = ('acl-2.4.0_1 update x86_64 https://repo-default.voidlinux.org/current 43080 20653\n'
           'libnew-1.0_1 install x86_64 https://repo-default.voidlinux.org/current 1 1\n')


class Rec:
    def __init__(self):
        self.calls = []

    def run(self, cmd, *, sudo=False, capture=True, **kw):
        self.calls.append(('sudo ' if sudo else '') + cmd)
        for needle, out in (('xbps-query -l', INSTALLED), ('xbps-query -Rs', REMOTE),
                            ('xbps-query -H', 'curl-8.20.0_1\n'), ('xbps-install -un', UPDATES),
                            ('xbps-query -m', 'curl-8.20.0_1\n'),
                            ('-p pkgver curl', 'curl-8.22.0_1\n'), ('-p hold curl', 'yes\n')):
            if needle in cmd:
                return Result(cmd, 0, stdout=out)
        return Result(cmd, 0, stdout='')


def _unit(name='curl', **fields):
    return ResolvedComponent(key=f'xbps\\{name}', driver='xbps', comp=name, fields={'name': name, **fields})


SCENARIOS = {
    'unbatched reads': lambda d: (d.get_version(_unit()), d.get_latest(_unit()), d.is_locked(_unit())),
    'batched reads': lambda d: (setattr(d, 'batch', d.batch_index([_unit()])),
                                d.get_version(_unit()), d.get_latest(_unit()), d.get_latest(_unit('0ad')),
                                d.is_locked(_unit()), d.is_locked(_unit('acl')))[1:],
    'indexes': lambda d: (d.installed_index(), d.explicit_keys(), d.held_keys(), d.upgradable_index()),
    'mutations': lambda d: (d.install(_unit()), d.uninstall(_unit()), d.upgrade(_unit()),
                            d.set_version(_unit(), '8.0_1'), d.lock(_unit()), d.unlock(_unit()),
                            d.upgrade_all()) and None,
    'package set': lambda d: (d.install(_unit('python-build-deps', packages=['gcc', 'zlib-devel'])),
                              d.lock(_unit('python-build-deps', packages=['gcc', 'zlib-devel'])),
                              d.index_key(_unit('python-build-deps', packages=['gcc', 'zlib-devel'])))[2],
}


@pytest.mark.parametrize('scenario', sorted(SCENARIOS))
def test_driver_matches_core(scenario):
    out = {}
    for label, cls in (('core', CoreXbps), ('plugin', _plugin_driver())):
        rec = Rec()
        d = cls(rec)
        out[label] = (SCENARIOS[scenario](d), rec.calls)
    assert out['plugin'] == out['core']


# -- 4. loaded over core: a no-op -------------------------------------------------

@pytest.mark.parametrize('block', ['void', 'void_musl'])
def test_loading_over_core_changes_no_resolution(block):
    base = Resolver(CORE_ROUTES, block, None, 'x86_64')
    both = Resolver(CORE_ROUTES, block, None, 'x86_64', plugin_files=[str(PLUGIN / 'routes.hu')])

    def res(r, c):
        try:
            return sorted((k, u.name) for k, u in r.resolve_names([c]).items() if u.comp == c)
        except ResolveError as e:
            return f'ERR {e}'
    changed = [c for c in sorted(base.components) if res(base, c) != res(both, c)]
    assert not changed, f'plugin changes core resolution on {block}: {changed}'
