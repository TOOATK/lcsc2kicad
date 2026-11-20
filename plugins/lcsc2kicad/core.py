"""lcsc2kicad core: fetch LCSC/JLCPCB parts via easyeda2kicad and add them to
EXISTING KiCad libraries chosen by the user (no new libraries are created).

config.json (in data_dir()) holds named profiles ({"active": name, "profiles": {name: {...}}});
each profile has these keys:
  sym_lib    existing .kicad_sym file        (symbols)
  fp_dir     existing footprint folder        (footprints)
  fp_nick    KiCad nickname of fp_dir         (written into symbol Footprint field)
  model_dir  existing folder for 3D models    (optional; empty = skip 3D)
  model_ref  3D path written in footprints    (optional; default = model_dir)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Callable

PKG_DIR = Path(__file__).resolve().parent


def data_dir() -> Path:
    """Per-user folder for config.json and backups/ (never inside the plugin folder,
    which KiCad's PCM replaces on every update). $LCSC2KICAD_HOME overrides it."""
    env = os.environ.get("LCSC2KICAD_HOME")
    if env:
        return Path(env).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "lcsc2kicad"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA") or Path.home()) / "lcsc2kicad"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "lcsc2kicad"


DATA_DIR = data_dir()
CONFIG_PATH = DATA_DIR / "config.json"
BACKUP_DIR = DATA_DIR / "backups"
# where config.json lived before 1.0 (next to core.py, i.e. the repo root)
LEGACY_CONFIGS = (PKG_DIR / "config.json", PKG_DIR.parent.parent / "config.json")
KEYS = ("sym_lib", "fp_dir", "fp_nick", "model_dir", "model_ref")
PART_FIELD = "LCSC"                    # symbol field holding the LCSC part number

Log = Callable[[str], None]


def _print(msg: str) -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------- config / profiles
# config.json = {"active": "<name>", "profiles": {"<name>": {<KEYS>}, ...}}
# A profile is one complete import target: symbol lib + footprint lib + 3D folder.
# Old flat configs (KEYS at top level) are migrated into one profile on load.
DEFAULT_PROFILE = "Default"


def _migrate(cfg: dict) -> dict:
    if not isinstance(cfg.get("profiles"), dict):
        flat = {k: cfg.pop(k) for k in KEYS if k in cfg}
        name = (flat.get("fp_nick") or "").strip() or DEFAULT_PROFILE
        cfg["profiles"] = {name: flat}
        cfg["active"] = name
    if not cfg["profiles"]:
        cfg["profiles"] = {DEFAULT_PROFILE: {}}
    if cfg.get("active") not in cfg["profiles"]:
        cfg["active"] = next(iter(cfg["profiles"]))
    return cfg


def _adopt_legacy_config() -> None:
    """First run after the move to DATA_DIR: copy an old repo-local config.json over."""
    if CONFIG_PATH.exists():
        return
    for old in LEGACY_CONFIGS:
        if old.is_file():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old, CONFIG_PATH)
            return


def load_config() -> dict:
    _adopt_legacy_config()
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            cfg = {}
    except (OSError, ValueError):
        cfg = {}
    return _migrate(cfg)


def save_config(cfg: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, CONFIG_PATH)  # atomic: never leaves a half-written config


def profile_names() -> list[str]:
    return list(load_config()["profiles"])


def active_name() -> str:
    return load_config()["active"]


def get_profile(name: str | None = None) -> dict[str, str]:
    """{key: value} for every KEY ('' when unset). Raises ValueError if unknown."""
    cfg = load_config()
    name = name or cfg["active"]
    if name not in cfg["profiles"]:
        raise ValueError(f"No profile named '{name}' (have: {', '.join(cfg['profiles'])})")
    p = cfg["profiles"][name]
    return {k: str(p.get(k) or "") for k in KEYS}


def _check_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("Profile name is empty")
    return name


def save_profile(name: str, **kw) -> dict[str, str]:
    """Create profile `name` if needed and store the given (non-None) KEYS in it."""
    name = _check_name(name)
    cfg = load_config()
    p = cfg["profiles"].setdefault(name, {})
    for k, v in kw.items():
        if k in KEYS and v is not None:
            p[k] = str(v)
    save_config(cfg)
    return get_profile(name)


def set_active(name: str) -> None:
    cfg = load_config()
    if name not in cfg["profiles"]:
        raise ValueError(f"No profile named '{name}' (have: {', '.join(cfg['profiles'])})")
    cfg["active"] = name
    save_config(cfg)


def rename_profile(old: str, new: str) -> None:
    new = _check_name(new)
    cfg = load_config()
    if old not in cfg["profiles"]:
        raise ValueError(f"No profile named '{old}'")
    if new == old:
        return
    if new in cfg["profiles"]:
        raise ValueError(f"Profile '{new}' already exists")
    # rebuild to keep the profile's position in the list
    cfg["profiles"] = {(new if k == old else k): v for k, v in cfg["profiles"].items()}
    if cfg["active"] == old:
        cfg["active"] = new
    save_config(cfg)


def delete_profile(name: str) -> None:
    cfg = load_config()
    if name not in cfg["profiles"]:
        raise ValueError(f"No profile named '{name}'")
    if len(cfg["profiles"]) == 1:
        raise ValueError("Can't delete the only profile")
    del cfg["profiles"][name]
    if cfg["active"] == name:
        cfg["active"] = next(iter(cfg["profiles"]))
    save_config(cfg)


# --------------------------------------------------------------------------- part ids
def parse_ids(text: str) -> list[str]:
    """'C2040, c25804 2040' -> ['C2040', 'C25804'] (dedup, order kept)."""
    out: list[str] = []
    for tok in re.split(r"[\s,;]+", text.strip()):
        if not tok:
            continue
        m = re.fullmatch(r"[Cc]?(\d+)", tok)
        if not m:
            raise ValueError(f"Not an LCSC part number: '{tok}'")
        pid = "C" + m.group(1)
        if pid not in out:
            out.append(pid)
    return out


# --------------------------------------------------------------------------- KiCad fp nicknames
def _kicad_config_root() -> Path:
    base = os.environ.get("KICAD_CONFIG_HOME")
    if base:
        return Path(base)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Preferences" / "kicad"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", "")) / "kicad"
    return Path.home() / ".config" / "kicad"


def kicad_version() -> str:
    """KiCad major.minor whose settings to read.
    1. $LCSC2KICAD_KICAD_VERSION
    2. run as a KiCad plugin: KiCad's per-version plugin venv path
       (e.g. .../KiCad/9.0/python-environments/<id>/...)
    3. newest version folder in KiCad's config dir (9.0 if none)."""
    v = os.environ.get("LCSC2KICAD_KICAD_VERSION")
    if v:
        return v
    m = re.search(r"[/\\](\d+\.\d+)[/\\]python-environments[/\\]", sys.prefix, re.I)
    if m:
        return m.group(1)
    found = []
    try:
        for d in _kicad_config_root().iterdir():
            if re.fullmatch(r"\d+\.\d+", d.name) and (d / "fp-lib-table").is_file():
                found.append(tuple(int(x) for x in d.name.split(".")))
    except OSError:
        pass
    return "%d.%d" % max(found) if found else "9.0"


def kicad_config_dir() -> Path:
    return _kicad_config_root() / kicad_version()


def _kicad_vars() -> dict[str, str]:
    try:
        v = json.loads((kicad_config_dir() / "kicad_common.json").read_text(encoding="utf-8")) \
            .get("environment", {}).get("vars") or {}
    except (OSError, ValueError):
        v = {}
    return {**os.environ, **v}


def fp_libraries() -> dict[str, str]:
    """{nickname: resolved path} from KiCad's global fp-lib-table (empty if unreadable)."""
    try:
        text = (kicad_config_dir() / "fp-lib-table").read_text(encoding="utf-8")
    except OSError:
        return {}
    vars_ = _kicad_vars()
    out = {}
    for name, uri in re.findall(r'\(lib\s+\(name\s+"?([^")]+)"?\).*?\(uri\s+"?([^")]+)"?\)', text):
        out[name] = re.sub(r"\$\{(\w+)\}", lambda m: vars_.get(m.group(1), m.group(0)), uri)
    return out


def guess_fp_nick(fp_dir: str | Path) -> str:
    """Nickname registered in KiCad for fp_dir, else the folder name without .pretty."""
    target = os.path.normpath(str(fp_dir))
    for nick, path in fp_libraries().items():
        if os.path.normpath(path) == target:
            return nick
    name = Path(fp_dir).name
    return name[:-7] if name.lower().endswith(".pretty") else name


# --------------------------------------------------------------------------- import
def _check_targets(sym_lib, fp_dir, fp_nick, model_dir) -> None:
    if not sym_lib or not Path(sym_lib).is_file():
        raise RuntimeError(f"Symbol library not found: {sym_lib or '(not chosen)'} "
                           "- choose an existing .kicad_sym")
    if not fp_dir or not Path(fp_dir).is_dir():
        raise RuntimeError(f"Footprint library folder not found: {fp_dir or '(not chosen)'}")
    if not fp_nick:
        raise RuntimeError("Footprint library nickname is empty")
    if model_dir and not Path(model_dir).is_dir():
        raise RuntimeError(f"3D folder not found: {model_dir}")


def _backup(sym_lib: Path, log: Log) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dst = BACKUP_DIR / f"{sym_lib.stem}-{time.strftime('%Y%m%d-%H%M%S')}{sym_lib.suffix}"
    shutil.copy2(sym_lib, dst)
    log(f"Backup: {dst.name}")


def import_parts(
    ids: list[str],
    sym_lib: str | Path,
    fp_dir: str | Path,
    fp_nick: str,
    model_dir: str | Path | None = None,
    model_ref: str | None = None,
    overwrite: bool = False,
    log: Log = _print,
) -> dict[str, str]:
    """Import each part into the chosen libraries.
    Returns {id: 'added' | 'skipped' | 'failed: reason'}."""
    try:
        from easyeda2kicad.easyeda.easyeda_api import EasyedaApi
        from easyeda2kicad.easyeda.easyeda_importer import (
            Easyeda3dModelImporter,
            EasyedaFootprintImporter,
            EasyedaSymbolImporter,
        )
        from easyeda2kicad.kicad.export_kicad_3d_model import Exporter3dModelKicad
        from easyeda2kicad.kicad.export_kicad_footprint import ExporterFootprintKicad
        from easyeda2kicad.kicad.export_kicad_symbol import ExporterSymbolKicad
    except ImportError:
        raise RuntimeError("easyeda2kicad not installed - run setup.sh first")

    class SymExporter(ExporterSymbolKicad):
        # rename easyeda2kicad's "LCSC Part" field -> PART_FIELD (new symbols only)
        def export(self, footprint_lib_name: str) -> str:
            return super().export(footprint_lib_name).replace(
                '"LCSC Part"', f'"{PART_FIELD}"', 1)

    _check_targets(sym_lib, fp_dir, fp_nick, model_dir)
    sym_lib, fp_dir = Path(sym_lib), Path(fp_dir)
    model_ref = (model_ref or str(model_dir or "")).rstrip("/")
    _backup(sym_lib, log)

    api = EasyedaApi()
    results: dict[str, str] = {}

    for pid in ids:
        log(f"--- {pid}")
        try:
            cad = api.get_cad_data_of_component(lcsc_id=pid)
            if not cad:
                raise RuntimeError("no EasyEDA CAD data (wrong number or network blocked)")
            done = []

            # symbol -> existing lib; Footprint field = "<fp_nick>:<fp>", adds "LCSC" field
            sym = EasyedaSymbolImporter(easyeda_cp_cad_data=cad).get_symbol()
            if SymExporter(symbol=sym, lib_path=str(sym_lib)).save_to_lib(
                lib_path=str(sym_lib), footprint_lib_name=fp_nick, overwrite=overwrite
            ):
                log(f"  symbol    : {sym_lib.stem}:{sym.info.name}")
                done.append("sym")
            else:
                log(f"  symbol    : {sym.info.name} (exists, skipped)")

            # footprint -> existing folder
            fp = EasyedaFootprintImporter(easyeda_cp_cad_data=cad).get_footprint()
            fp_file = fp_dir / f"{fp.info.name}.kicad_mod"
            if fp_file.is_file() and not overwrite:
                log(f"  footprint : {fp.info.name} (exists, skipped)")
            else:
                if not model_dir:
                    fp.model_3d = None  # no 3D folder -> no (model ...) line
                ExporterFootprintKicad(footprint=fp).export(
                    footprint_full_path=str(fp_file), model_3d_path=model_ref
                )
                log(f"  footprint : {fp_nick}:{fp.info.name}")
                done.append("fp")

            # 3D model (WRL referenced by footprint, STEP saved alongside)
            if not model_dir:
                log("  3D model  : skipped (no 3D folder chosen)")
            else:
                m3d = Exporter3dModelKicad(
                    model_3d=Easyeda3dModelImporter(
                        easyeda_cp_cad_data=cad, download_raw_3d_model=True, api=api
                    ).output
                )
                if not m3d.output:
                    log("  3D model  : none available")
                elif m3d.export(output_dir=str(model_dir), overwrite=overwrite):
                    log(f"  3D model  : {m3d.output.name} (.wrl/.step)")
                    done.append("3d")
                else:
                    log(f"  3D model  : {m3d.output.name} (exists, skipped)")

            results[pid] = "added" if done else "skipped"
        except Exception as e:  # keep going with the next part
            results[pid] = f"failed: {e}"
            log(f"  FAILED    : {e}")

    return results
