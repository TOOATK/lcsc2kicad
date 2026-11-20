#!/usr/bin/env python3
"""Validate metadata.json, plugins/plugin.json and (if built) dist/pages/*.json against
KiCad's published schemas. Needs `pip install jsonschema`.

  python3 tools/validate.py [--schemas DIR]   # DIR with pcm.json/api.json, else download
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
URLS = {"pcm": "https://go.kicad.org/pcm/schemas/v1", "api": "https://go.kicad.org/api/schemas/v1"}


def load_schema(name: str, d: str | None) -> dict:
    if d:
        return json.loads((Path(d) / f"{name}.json").read_text(encoding="utf-8"))
    with urllib.request.urlopen(URLS[name], timeout=30) as r:
        return json.loads(r.read().decode())


def sub(schema: dict, definition: str) -> dict:
    return {**{k: v for k, v in schema.items() if k != "$ref"},
            "$ref": f"#/definitions/{definition}"}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schemas")
    a = ap.parse_args(argv)
    pcm, api = load_schema("pcm", a.schemas), load_schema("api", a.schemas)

    checks = [("metadata.json", ROOT / "metadata.json", pcm),
              ("plugins/plugin.json", ROOT / "plugins" / "plugin.json", api)]
    pages = ROOT / "dist" / "pages"
    if (pages / "packages.json").is_file():
        checks.append(("pages/packages.json", pages / "packages.json", sub(pcm, "PackageArray")))
        checks.append(("pages/repository.json", pages / "repository.json", sub(pcm, "Repository")))

    bad = 0
    for label, path, schema in checks:
        data = json.loads(path.read_text(encoding="utf-8"))
        errs = list(jsonschema.Draft7Validator(schema).iter_errors(data))
        print(f"{'ok ' if not errs else 'BAD'} {label}")
        for e in errs:
            print(f"     {'/'.join(map(str, e.path))}: {e.message}")
        bad += bool(errs)

    plugin = json.loads((ROOT / "plugins" / "plugin.json").read_text(encoding="utf-8"))
    meta = json.loads((ROOT / "metadata.json").read_text(encoding="utf-8"))
    for act in plugin["actions"]:
        for f in [act["entrypoint"], *act.get("icons-light", []), *act.get("icons-dark", [])]:
            if not (ROOT / "plugins" / f).is_file():
                print(f"BAD missing plugins/{f}")
                bad += 1
    if plugin["identifier"] != meta["identifier"]:
        print("BAD plugin.json identifier != metadata.json identifier")
        bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
