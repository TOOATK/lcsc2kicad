#!/usr/bin/env python3
"""Build the KiCad PCM package and the repository files for GitHub Pages.

  python3 tools/build_pcm.py [--previous OLD_packages.json]

Writes to dist/:
  lcsc2kicad-<ver>-pcm.zip     the package (install via PCM "Install from File" or a release)
  pages/packages.json          all versions (merged with --previous) incl. this one
  pages/repository.json        the URL users add in PCM > Manage Repositories
  pages/resources.zip          package icon for the PCM list
The version comes from plugins/lcsc2kicad/__init__.py and must match metadata.json.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OWNER, REPO = "TOOATK", "lcsc2kicad"
RELEASE_URL = f"https://github.com/{OWNER}/{REPO}/releases/download"
PAGES_URL = f"https://{OWNER.lower()}.github.io/{REPO}"
SKIP = re.compile(r"(__pycache__|\.pyc$|\.DS_Store$)")
ZIP_DATE = (2020, 1, 1, 0, 0, 0)  # fixed timestamps -> reproducible zips


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write_zip(dst: Path, entries: list[tuple[str, bytes]]) -> int:
    """Write entries (arcname, data); returns the total uncompressed size."""
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(entries):
            zi = zipfile.ZipInfo(name, ZIP_DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, data)
    return sum(len(d) for _, d in entries)


def pkg_version() -> str:
    text = (ROOT / "plugins" / "lcsc2kicad" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--previous", help="existing packages.json to merge older versions from")
    ap.add_argument("--out", default=str(ROOT / "dist"))
    a = ap.parse_args(argv)

    meta = json.loads((ROOT / "metadata.json").read_text(encoding="utf-8"))
    ver = pkg_version()
    if [v["version"] for v in meta["versions"]] != [ver]:
        print(f"metadata.json versions must be exactly [{ver}] (from __init__.py)", file=sys.stderr)
        return 1
    ident = meta["identifier"]

    out = Path(a.out)
    pages = out / "pages"
    pages.mkdir(parents=True, exist_ok=True)

    # ---- package zip: metadata.json + plugins/ + resources/
    entries = [("metadata.json", (json.dumps(meta, indent=2) + "\n").encode())]
    for sub in ("plugins", "resources"):
        for f in sorted((ROOT / sub).rglob("*")):
            rel = f.relative_to(ROOT).as_posix()
            if f.is_file() and not SKIP.search(rel):
                entries.append((rel, f.read_bytes()))
    zname = f"{REPO}-{ver}-pcm.zip"
    zpath = out / zname
    install_size = write_zip(zpath, entries)

    entry = {**meta["versions"][0],
             "download_url": f"{RELEASE_URL}/v{ver}/{zname}",
             "download_sha256": sha256(zpath),
             "download_size": zpath.stat().st_size,
             "install_size": install_size}

    # ---- packages.json (merge older versions)
    versions = [entry]
    if a.previous and Path(a.previous).is_file():
        old = json.loads(Path(a.previous).read_text(encoding="utf-8"))
        for p in old.get("packages", []):
            if p.get("identifier") == ident:
                versions += [v for v in p.get("versions", []) if v.get("version") != ver]
    versions.sort(key=lambda v: [int(x) for x in v["version"].split(".")], reverse=True)
    pkg = copy.deepcopy(meta)
    pkg.pop("$schema", None)
    pkg["versions"] = versions
    packages = pages / "packages.json"
    packages.write_text(json.dumps({"packages": [pkg]}, indent=2) + "\n", encoding="utf-8")

    # ---- resources.zip: <identifier>/icon.png shown in the PCM list
    resources = pages / "resources.zip"
    write_zip(resources, [(f"{ident}/icon.png", (ROOT / "resources" / "icon.png").read_bytes())])

    # ---- repository.json
    now = int(time.time())
    utc = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now))

    def res(p: Path) -> dict:
        return {"url": f"{PAGES_URL}/{p.name}", "sha256": sha256(p),
                "update_timestamp": now, "update_time_utc": utc}

    repo = {"$schema": "https://go.kicad.org/pcm/schemas/v1#/definitions/Repository",
            "name": "lcsc2kicad repository",
            "maintainer": meta["maintainer"],
            "packages": res(packages),
            "resources": res(resources)}
    (pages / "repository.json").write_text(json.dumps(repo, indent=2) + "\n", encoding="utf-8")

    print(f"{zpath}  ({entry['download_size']} B, sha256 {entry['download_sha256'][:12]}…)")
    print(f"{pages}/  packages.json repository.json resources.zip  ({len(versions)} version(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
