# configsys-void — Void Linux support for configsys

A complete, working [configsys](https://github.com/spacemeat/configsys) **code plugin** that
makes **Void Linux** a first-class OS: a `void` OS block, an `xbps` driver, verified per-distro
package names for the components whose Void name differs, and a name-existence sweep that keeps
those names honest as Void rolls. It doubles as the reference **code plugin** — the shape to copy
for any package manager configsys doesn't ship (nix, slackpkg, …); Alpine (`apk`) and openSUSE
(`zypper`) began as plugins shaped exactly like this before being folded into base.

It's three files — the shape of every code plugin:

| File | Role |
| --- | --- |
| `plugin.hu` | manifest — name, `requires-abi`, `data:` (the routing layers), `code:` (the module) |
| `routes.hu` | data — the `void` OS block, a `via: xbps` component, and the `component-names:` name map |
| `driver.py` | code — the `Xbps(Driver)` subclass + `DRIVERS = [Xbps]` export |

## What it demonstrates

- **A new OS in one block.** `os: { void: { using: linux  native: xbps } }` makes every
  existing repo component that routes `via: native` install on Void — no per-component work.
- **A new driver.** `driver.py` subclasses `Driver` from the frozen ABI surface and implements
  the op set (`get_version`/`install`/`upgrade`/…) with real `xbps-*` commands. Query ops need
  no root; mutations run under sudo. Void is rolling but has a native package hold, so this
  driver implements a real `lock`/`unlock` via `xbps-pkgdb -m hold`.
- **Correct Void package names.** Most repo components already resolve to the right xbps name
  (Void is close to the generic default). The ~10 that differ are patched in `component-names:`
  — `docker`, `R`, `openjdk21`, `fish-shell`, `apache-maven`, `openbsd-netcat`, `python3-pipx`,
  `fuse`, `wireshark` (for tshark) — a per-driver name map that corrects existing core components
  *without* redefining them. `nmap` (not packaged for Void — only `masscan`) is dropped there,
  so it's simply not offered rather than failing at install.
- **The trust gate.** Because `plugin.hu` has a `code:` key, the plugin runs with your
  privileges during installs — so it stays inert until you approve its exact contents.

## Try it

```console
# point configsys at this plugin (or use a local path with `configsys plugin add <path>`)
$ configsys plugin add github:spacemeat/configsys-void --ref v0.1.0
$ configsys plugin list
  void   github:spacemeat/configsys-void @v0.1.0
         ok  [ships code — untrusted; run: configsys plugin trust void]

# its code — the xbps driver — won't load until you approve this content
$ configsys plugin trust void
configsys: trusted void @ <sha256> — its code will run during installs

# now `via: xbps` resolves; on a Void box, `btop` (a repo component) installs via xbps too
$ configsys where xtools
```

Until trusted, the data still loads (you'll see the `void` OS block and `xtools`), but
`via: xbps` is an unknown driver and the component degrades to an error row — never a crash.

## Writing your own

Copy this directory, then:

1. Rename in `plugin.hu` (`name`, `provides`) and keep `requires-abi: 1`.
2. In `driver.py`, set `name = '<your-driver>'`, implement the op set against your package
   manager, and list your classes in `DRIVERS = [ ... ]`. Import only from the frozen surface:
   `from configsys.plugins import Driver, Result`.
3. In `routes.hu`, add your `os:` block (if it's a new distro) and components with
   `{ via: <your-driver> ... }` bindings.

The contract your `Driver` codes against — class attributes, the ops to implement, and the
helpers you may call (`resolve_version`, `download_url`, `scoped_dir`, `sudo`, `scope`, …) — is
documented on the `Driver` base class (`configsys/driver.py`) and versioned by
`configsys.plugins.ABI_VERSION`.

## Testing — the name sweep

`test/run-name-sweep.sh` resolves the whole component catalog on `void` (with this plugin loaded)
and checks every xbps package name it maps to actually exists in Void's repos, against
`ghcr.io/void-linux/void-glibc`. This is what keeps `component-names:` honest: if Void renames or
drops a package, the sweep turns red and points at the exact component.

```console
$ CONFIGSYS_REPO=../configsys test/run-name-sweep.sh
>> void (xbps): 88 packages in ghcr.io/void-linux/void-glibc:latest
name sweep: OK — void native names all exist.
```

- `test/void-repo-setup.sh` — syncs the xbps repo index in the container before the check.
- `test/run-name-sweep.sh` — invokes the plugin-OS mode of configsys's `tools/namesweep.py`.
- `test/namesweep-allowlist.hu` — the GPU/accelerator SDKs (CUDA/ROCm/oneAPI) that live in vendor
  repos, not Void's base (unioned with configsys's core allowlist).

Void ships both **glibc** and **musl** variants; this plugin (and the sweep) target glibc, which
matches the `using: linux` glibc baseline. musl support would be a follow-on `when:`/name pass.
