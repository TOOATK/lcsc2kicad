#!/usr/bin/env python3
"""lcsc2kicad CLI - adds parts to your EXISTING KiCad libraries.

  python -m lcsc2kicad C2040 C25804                 import into the active profile
  python -m lcsc2kicad -p KT C2040                  import into profile "KT" (this run only)
  python -m lcsc2kicad C2040 --overwrite            replace existing symbol/footprint/3D
  python -m lcsc2kicad --status                     show the selected profile's choices

  Profiles (each = symbol lib + footprint lib + 3D folder, stored in config.json,
  see --status for its location):
    --profiles                 list profiles (* = active)
    -p, --profile NAME         use NAME for this run
    --use NAME                 make NAME the active (default) profile
    --delete NAME              delete profile NAME

  Choices (saved into the selected profile with --save, otherwise this run only;
  --save on a new -p NAME creates that profile):
    --sym-lib FILE.kicad_sym   existing symbol library
    --fp-dir DIR               existing footprint library folder
    --fp-nick NAME             KiCad nickname of that folder (default: auto)
    --model-dir DIR            existing 3D folder ("" = no 3D)
    --model-ref TEXT           3D path written in footprints (default: model-dir)
"""
from __future__ import annotations

import argparse
import logging
import sys

from . import core


def list_profiles() -> None:
    active = core.active_name()
    for name in core.profile_names():
        p = core.get_profile(name)
        mark = "*" if name == active else " "
        print(f"{mark} {name}")
        for k in ("sym_lib", "fp_dir", "model_dir"):
            print(f"      {k:<10}: {p[k] or '(not set)'}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Import JLCPCB/LCSC parts into existing KiCad libs")
    ap.add_argument("parts", nargs="*", help="LCSC numbers, e.g. C2040 C25804 (commas ok)")
    ap.add_argument("-p", "--profile", help="profile to use for this run")
    ap.add_argument("--use", metavar="NAME", help="make NAME the active profile")
    ap.add_argument("--profiles", action="store_true", help="list profiles")
    ap.add_argument("--delete", metavar="NAME", help="delete a profile")
    ap.add_argument("--sym-lib")
    ap.add_argument("--fp-dir")
    ap.add_argument("--fp-nick")
    ap.add_argument("--model-dir")
    ap.add_argument("--model-ref")
    ap.add_argument("--save", action="store_true",
                    help="save the given choices into the selected profile (creates it if new)")
    ap.add_argument("--overwrite", action="store_true", help="replace existing parts")
    ap.add_argument("--status", action="store_true", help="show the selected profile")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.ERROR, format="  [%(levelname)s] %(message)s")

    given = {k: getattr(a, k) for k in core.KEYS}
    try:
        if a.delete:
            core.delete_profile(a.delete)
            print(f"Deleted profile '{a.delete}'.")
        if a.use:
            core.set_active(a.use)
            print(f"Active profile: {a.use}")
        name = a.profile or a.use or core.active_name()
        if a.save:
            core.save_profile(name, **given)
            print(f"Choices saved to profile '{name}'.")
        if a.profiles:
            list_profiles()
            if not a.parts:
                return 0
        saved = core.get_profile(name)  # raises if -p names an unknown profile
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    c = {k: (given[k] if given[k] is not None else saved[k]) for k in core.KEYS}
    if c["fp_dir"] and not c["fp_nick"]:
        c["fp_nick"] = core.guess_fp_nick(c["fp_dir"])
    # model_ref: keep the saved one so paths written in footprints stay Mac paths
    if given["model_ref"] is None:
        c["model_ref"] = saved["model_ref"] or saved["model_dir"] or c["model_dir"]

    # bare `./lcsc` (or --status) shows the selected profile
    if a.status or not (a.parts or a.delete or a.use or a.save):
        print(f"{'profile':<10}: {name}")
        for k in core.KEYS:
            print(f"{k:<10}: {c[k] or '(not set)'}")
        print(f"{'config':<10}: {core.CONFIG_PATH}")
        print(f"{'kicad':<10}: {core.kicad_version()}")
    if not a.parts:
        return 0

    try:
        ids = core.parse_ids(" ".join(a.parts))
        print(f"Profile: {name}", flush=True)
        res = core.import_parts(ids, c["sym_lib"], c["fp_dir"], c["fp_nick"],
                                c["model_dir"] or None, c["model_ref"], overwrite=a.overwrite)
    except (ValueError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print("\nSummary:")
    rc = 0
    for pid, r in res.items():
        print(f"  {pid:<10} {r}")
        if r.startswith("failed"):
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
