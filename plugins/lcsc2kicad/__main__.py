"""`python -m lcsc2kicad ...` runs the CLI."""
import sys

from .cli import main

sys.exit(main(sys.argv[1:]))
