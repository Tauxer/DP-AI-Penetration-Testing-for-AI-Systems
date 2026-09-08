"""Punto de entrada del paquete: `python -m redturing`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
