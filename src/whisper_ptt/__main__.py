"""Allow `python -m whisper_ptt`."""

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main())
