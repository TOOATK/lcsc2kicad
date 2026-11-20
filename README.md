# LCSC to KiCad (lcsc2kicad)

Add JLCPCB/LCSC parts (symbol + footprint + 3D model) to your **existing** KiCad libraries.
Nothing new is created: the symbol library, footprint folder and 3D folder must already exist.
Part data comes from EasyEDA via [easyeda2kicad](https://github.com/uPesy/easyeda2kicad.py).

Works with KiCad 9 and later (IPC plugin). Can also run standalone (GUI or CLI) without KiCad.

## Install in KiCad (Plugin and Content Manager)

1. **Enable the API once:** KiCad → Preferences → Plugins → tick **Enable KiCad API**.
   Check that **Python interpreter** points to KiCad's own Python
   (macOS: `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`
   — adjust the folder if your KiCad app is named differently, e.g. `KiCad9/KiCad9.app`).
2. **Add the repository:** Plugin and Content Manager → **Manage…** → **Add** →
   `https://tooatk.github.io/lcsc2kicad/repository.json`
3. Select the repository, install **LCSC to KiCad**, Apply.
   (Or download `lcsc2kicad-x.y.z-pcm.zip` from [Releases](https://github.com/TOOATK/lcsc2kicad/releases)
   and use **Install from File…**.)
4. Restart the PCB Editor. A toolbar button (chip with an arrow) opens the importer.
   KiCad installs `easyeda2kicad` into the plugin's own Python environment the first time.

## Use

1. Pick or create a **profile** and choose:
   - **Symbol library**: your existing `.kicad_sym`
   - **Footprint library**: your existing `.pretty` folder (the nickname is auto-filled from
     KiCad's fp-lib-table; it goes into each symbol's Footprint field)
   - **3D folder** (or None to skip 3D) and **3D path in footprint**
     (e.g. `${KIPRJMOD}/...` or `${MY_VAR}/3D`; blank = absolute folder path)
2. Paste part numbers (`C2040, C25804`) and **Import** (⌘↵ / Ctrl+↵).
3. Reopen KiCad's symbol/footprint chooser to see the new parts.

- Existing parts are skipped unless **Overwrite existing** is ticked.
- A copy of the symbol library is saved to `backups/` before every import.
- New symbols get an `LCSC` field with the part number.

### Profiles
A profile is one complete import target: symbol library + footprint library + 3D folder.
Keep one per library set and switch with the drop-down; **New…**, **Rename…**, **Delete**
(only removes the saved choices, never your libraries).

### Where settings live
`config.json` and `backups/` are kept per user, outside the plugin folder (so PCM updates
don't erase them):

| OS      | Folder                                        |
|---------|-----------------------------------------------|
| macOS   | `~/Library/Application Support/lcsc2kicad/`   |
| Windows | `%APPDATA%\lcsc2kicad\`                       |
| Linux   | `~/.config/lcsc2kicad/`                       |

Set `LCSC2KICAD_HOME` to use another folder. A `config.json` from a pre-1.0 checkout is
copied there automatically on first run.

## Standalone (without KiCad)

```bash
./setup.sh                          # once: .venv with easyeda2kicad
./LCSC2KiCad.command                # GUI (double-click in Finder)
./lcsc C2040 C25804                 # CLI, active profile
./lcsc -p KT C2040                  # another profile, this run only
./lcsc --profiles | --use KT | --delete KT | --status
./lcsc -p KT --sym-lib FILE --fp-dir DIR --model-dir DIR --save   # create/update KT
./lcsc C2040 --overwrite
```
One-off overrides: `--sym-lib FILE --fp-dir DIR --fp-nick NAME --model-dir DIR --model-ref TEXT`
(add `--save` to store them in the profile). Any Python 3.9+ with easyeda2kicad also works:
`PYTHONPATH=plugins python3 -m lcsc2kicad ...`

## Development

```
metadata.json            PCM package manifest (one version entry = the current version)
plugins/                 installed by PCM as the plugin folder
  plugin.json            IPC plugin: toolbar action -> action.py
  action.py              entrypoint (opens the GUI)
  requirements.txt       installed by KiCad into the plugin venv
  icons/                 toolbar icons (tools/make_icons.py)
  lcsc2kicad/            core.py (logic), gui.py (Tk), cli.py
resources/icon.png       64x64 PCM icon
tools/build_pcm.py       build dist/ (zip + GitHub Pages repository files)
tools/validate.py        check manifests against KiCad's schemas (needs jsonschema)
```

**Release:** bump `__version__` in `plugins/lcsc2kicad/__init__.py` and the version in
`metadata.json`, commit, then `git tag vX.Y.Z && git push --tags`. The GitHub Action builds
the zip, creates the Release and updates `repository.json`/`packages.json` on GitHub Pages
(older versions are kept). One-time: Settings → Pages → deploy from branch `gh-pages`.

## License

GPL-3.0. easyeda2kicad (AGPL-3.0) is installed as a separate dependency, not bundled.
