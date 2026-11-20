# CLAUDE.md

Python tool that imports JLCPCB/LCSC parts (symbol, footprint, 3D model) into **existing**
KiCad libraries, using the `easyeda2kicad` package. Packaged as a KiCad 9+ **PCM IPC
plugin** (toolbar button → Tk GUI) and still runnable standalone (Tk GUI + CLI).
GitHub repo `TOOATK/lcsc2kicad`; no tests (CI does a smoke test + schema validation).

## Layout
- `plugins/` — exactly what PCM installs as the plugin folder.
  - `plugin.json` (IPC action, scopes pcb/schematic) → `action.py` (adds its dir to
    `sys.path`, runs `lcsc2kicad.gui.main`). `requirements.txt` is installed by KiCad into
    the plugin venv (`<cache>/KiCad/<ver>/python-environments/<identifier>`).
  - `lcsc2kicad/core.py` — everything that matters: config/profile store, LCSC id parsing,
    KiCad fp-lib-table lookup (`guess_fp_nick`), KiCad version detection, `import_parts()`.
  - `lcsc2kicad/cli.py` (argparse; `python -m lcsc2kicad`), `lcsc2kicad/gui.py` (Tk; import
    runs on a worker thread, log lines via `queue.Queue` pumped by `root.after`).
  - Inside the package use relative imports (`from . import core`).
- `metadata.json` — PCM manifest. Its single `versions` entry must equal `__version__` in
  `plugins/lcsc2kicad/__init__.py` (build fails otherwise).
- `tools/build_pcm.py` → `dist/` (package zip + `pages/` repository.json, packages.json,
  resources.zip). `tools/validate.py` checks against KiCad's schemas (vendored in `tools/schemas/`). `tools/make_icons.py`
  redraws icons. `.github/workflows/release.yml` publishes on tag `vX.Y.Z`.
- `lcsc`, `LCSC2KiCad.command`, `setup.sh` — standalone launchers (`.venv`,
  `PYTHONPATH=plugins`).
- `SKILL.md` — source for the claude.ai `lcsc-to-kicad` skill (how Claude runs the tool
  from the Linux VM). Keep it in sync when CLI flags, config format or paths change; the
  installed skill is a separate copy and must be re-uploaded.

## Run
```bash
./setup.sh                      # once
./lcsc C2040 C25804             # import into the active profile
./lcsc -p NAME C2040            # import into another profile, this run only
./lcsc --status                 # shows config path and detected KiCad version
./LCSC2KiCad.command            # GUI
python3 tools/build_pcm.py && <python with jsonschema> tools/validate.py
```
To try changes without touching the real config or libraries, set
`LCSC2KICAD_HOME=<scratch dir>` and point `--sym-lib/--fp-dir/--model-dir` at scratch
copies (the config is *copied* into the scratch dir on first run, never moved).
To mimic KiCad, make a venv from KiCad's bundled Python
(`/Applications/KiCad9/KiCad9.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`)
under a path containing `/9.0/python-environments/`.

## Config
- Lives in `core.DATA_DIR` (macOS `~/Library/Application Support/lcsc2kicad/`, Windows
  `%APPDATA%\lcsc2kicad`, Linux `~/.config/lcsc2kicad`; `$LCSC2KICAD_HOME` overrides),
  with `backups/` beside it. Never store anything in the plugin folder: PCM replaces it.
- A legacy `config.json` at the repo root (pre-1.0) is copied in once by
  `_adopt_legacy_config`; repo-root `config.json`/`backups/` are gitignored.
```json
{"active": "IvoryElectronics",
 "profiles": {"IvoryElectronics": {"sym_lib": "...kicad_sym", "fp_dir": "....pretty",
   "fp_nick": "IvoryElectronics", "model_dir": "....3dshapes", "model_ref": ""}}}
```
- A profile = one full import target. Keys are `core.KEYS`.
- Old flat configs (keys at top level) are migrated in memory by `core._migrate` and
  written in the new form on the next save. Unknown top-level keys (e.g. `lib_dir`) are kept.
- Always go through `core.save_profile / set_active / rename_profile / delete_profile`;
  `save_config` writes atomically (tmp + `os.replace`).
- `model_ref` is the 3D path text written into footprints (e.g. `${KIPRJMOD}/...`); blank
  means "use `model_dir`". The CLI deliberately keeps the *saved* `model_ref` even when
  `--model-dir` is overridden, so runs from the VM still write Mac/KiCad paths.

## KiCad specifics
- `core.kicad_version()`: `$LCSC2KICAD_KICAD_VERSION`, else the version in the plugin venv
  path, else the newest `<config>/kicad/N.M` with an fp-lib-table.
- `gui.py` sets `TCL_LIBRARY`/`TK_LIBRARY` from `sys.base_prefix` when in a venv: KiCad's
  relocated bundled Python can't find `init.tcl` otherwise. Keep that before `import tkinter`.
- PCM schema: identifier `[-a-zA-Z0-9.]` only (no `_`); tags must start with a letter;
  license must be from its enum (AGPL isn't, hence GPL-3.0).

## Rules
- Never create KiCad libraries; `_check_targets` must reject missing targets.
- Existing symbols/footprints/models are skipped unless `overwrite=True`.
- Keep the symbol-library backup before any write.
- The symbol field `"LCSC Part"` from easyeda2kicad is renamed to `LCSC` (`PART_FIELD`).
- Keep Python 3.9-compatible (`from __future__ import annotations`): KiCad 9/10 on macOS
  bundle Python 3.9.13, and CI tests on 3.9.
- Release = bump `__version__` + `metadata.json`, tag `vX.Y.Z`, push.
