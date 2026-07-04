"""PyInstaller entry point for the portable build (see scripts/build_portable.py)."""

import multiprocessing
import sys

from whisper_ptt.app import main

if __name__ == "__main__":
    # Insurance against respawn loops if any dependency ever spawns a child
    # process from the frozen exe; a no-op otherwise.
    multiprocessing.freeze_support()
    sys.exit(main())
