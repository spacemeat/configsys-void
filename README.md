# configsys-void — Void Linux support for configsys

> **Void is now in configsys core** (the `void` / `void_musl` OS blocks, the `xbps` driver, and Void
> package names for the whole catalog), and core is authoritative. You don't need this plugin to run
> Void. It stays as the **worked example of an OS plugin**, kept in step with core:
> `test/test_parity.py` checks that it never contradicts core and that its driver behaves identically.
> If you do load it, its `xbps` driver **shadows** core's built-in one (`configsys check` and
> `configsys plugin list` report that). Drop it from your config if you only want Void support.

A complete, working [configsys](https://github.com/spacemeat/configsys) **code plugin** that
makes **Void Linux** a first-class OS in *both* its libc flavors — `void` (glibc) and `void_musl`
(musl): an `xbps` driver, verified package names for the components whose Void name differs, and a
name-existence sweep (both flavors) that keeps those names honest as Void rolls. It doubles as the
reference **code plugin** — the shape to copy for any package manager configsys doesn't ship (nix,
slackpkg, …); Alpine (`apk`) and openSUSE (`zypper`) began as plugins shaped exactly like this
before being folded into base.

It's three files — the shape of every code plugin:

| File | Role |
| --- | --- |
| `plugin.hu` | manifest — name, `requires-abi`, `data:` (the routing layers), `code:` (the module) |
| `routes.hu` | data — the `void`/`void_musl` OS blocks, a `via: xbps` component, and the `component-names:` name map |
| `driver.py` | code — the `Xbps(Driver)` subclass + `DRIVERS = [Xbps]` export |

## What it demonstrates

- **A new OS in one block.** `os: { void: { using: glibc_linux  native: xbps } }` makes every
  existing repo component that routes `via: native` install on Void — no per-component work.
- **libc as an orthogonal axis (the interesting bit).** Void ships glibc *and* musl builds of the
  same distro. `void` hangs off `glibc_linux` (so it provides the `glibc` capability — AppImages
  and glibc tarballs like neovim/julia/deno install normally); `void_musl` hangs off bare `linux`
  (like Alpine), so those same glibc-only bindings `requires: glibc` and cleanly **decline** —
  same xbps driver, same `component-names` map, just a different binary-compat surface, with zero
  per-component work. Both report `ID=void`, so `void_musl` is told apart by the musl loader's
  presence: `detect: { id: void  marker: /lib/ld-musl-x86_64.so.1 }` (pure data, no code).
- **A new driver.** `driver.py` subclasses `Driver` from the frozen ABI surface and implements
  the op set (`get_version`/`install`/`upgrade`/…) with real `xbps-*` commands. Query ops need
  no root; mutations run under sudo. Void is rolling but has a native package hold, so this
  driver implements a real `lock`/`unlock` via `xbps-pkgdb -m hold`.
- **Correct Void package names.** Most repo components already resolve to the right xbps name
  (Void is close to the generic default). A representative set that differs is patched in
  `component-names:` — `docker`, `R`, `openjdk21`, `fish-shell`, `apache-maven`, `openbsd-netcat`,
  `python3-pipx`, `fuse`, `wireshark` (for tshark) — a per-driver name map that corrects existing
  core components *without* redefining them. `rocm-hip` (Void doesn't package ROCm) is dropped with
  `{}`, so it's simply not offered rather than failing at install. (Core carries the complete set as
  `xbps:` entries in each binding's `name:` map, plus Void-only bindings a name map can't express.)
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

## Testing — parity with core

`test/test_parity.py` loads core from `$CONFIGSYS_REPO` (default `../configsys`) and checks four
things: the OS blocks equal core's; every `component-names:` entry agrees with core's resolution on
both flavors; this driver issues the same commands and parses the same answers as core's
`configsys/drivers/xbps.py`; and loading the plugin over core changes no resolution at all.

```console
$ ../configsys/.venv/bin/python -m pytest test/
```

## Testing — the name sweep

`test/run-name-sweep.sh` resolves the whole component catalog with this plugin loaded and checks
every xbps package name it maps to actually exists in Void's repos — for **both** flavors, against
`ghcr.io/void-linux/void-glibc` and `…/void-musl`. This is what keeps `component-names:` honest: if
Void renames or drops a package, the sweep turns red and points at the exact component.

```console
$ CONFIGSYS_REPO=../configsys test/run-name-sweep.sh
>> void (xbps): 397 packages in ghcr.io/void-linux/void-glibc:latest
name sweep: OK — void native names all exist.
>> void_musl (xbps): 398 packages in ghcr.io/void-linux/void-musl:latest
name sweep: OK — void_musl native names all exist.
```

xbps package names are libc-agnostic, so one `component-names` map covers both flavors — the sweep
confirms it against each. (The glibc/musl difference is the *binary-compat* surface, handled by the
`glibc` capability, not the package names.)

- `test/void-repo-setup.sh` — syncs the xbps repo index (plus the nonfree repo) in the container before the check.
- `test/run-name-sweep.sh` — invokes the plugin-OS mode of configsys's `tools/namesweep.py`, once
  per flavor.
- `test/namesweep-allowlist.hu` — the GPU/accelerator SDKs (CUDA/ROCm/oneAPI) that live in vendor
  repos, not Void's base (unioned with configsys's core allowlist).
