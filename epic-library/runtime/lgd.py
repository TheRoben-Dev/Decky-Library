"""Entry point for the bundled Legendary (GPL-3.0-or-later, https://github.com/derrod/legendary).

Run with the system Python in isolated mode: `python3 -I lgd.py <legendary arguments>`.
Legendary and its dependencies live unmodified in ./site (see THIRD_PARTY.md); this file only puts
that folder on the import path and starts Legendary's own command line.
"""
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "site"))

from legendary.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.argv[0] = "legendary"
    main()
