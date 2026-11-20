"""KiCad IPC plugin entrypoint: KiCad runs this with the plugin's own Python venv
(dependencies from requirements.txt) when the toolbar button is pressed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lcsc2kicad.gui import main  # noqa: E402

main()
