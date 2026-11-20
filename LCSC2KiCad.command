#!/bin/bash
# Double-click in Finder to open the GUI (standalone checkout, outside KiCad).
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || ./setup.sh || { read -p "Setup failed. Press Enter."; exit 1; }
PYTHONPATH="$PWD/plugins" exec .venv/bin/python -m lcsc2kicad.gui
