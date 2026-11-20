#!/bin/bash
# Standalone setup (not needed when installed through KiCad PCM): creates .venv
# with plugins/requirements.txt. Safe to re-run.
set -e
cd "$(dirname "$0")"

PY=""
for c in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3,9))' 2>/dev/null; then
    PY="$c"; break
  fi
done
[ -z "$PY" ] && { echo "ERROR: Python 3.9+ not found. Install from python.org or 'brew install python'."; exit 1; }
echo "Python : $($PY --version) ($PY)"

if "$PY" -c 'import tkinter' 2>/dev/null; then
  echo "Tkinter: ok"
else
  echo "Tkinter: MISSING - GUI won't start (CLI still works)."
  echo "         Homebrew Python: brew install python-tk   |  or use the python.org installer"
fi

[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q --upgrade -r plugins/requirements.txt
echo "easyeda2kicad: $(.venv/bin/python -c 'import importlib.metadata as m; print(m.version("easyeda2kicad"))')"
chmod +x lcsc LCSC2KiCad.command 2>/dev/null || true
echo
echo "Ready.  GUI: double-click LCSC2KiCad.command   CLI: ./lcsc C2040 C25804"
