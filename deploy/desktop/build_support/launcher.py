"""Run the installed console entry point from a desktop executable."""

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from engine.cli import main

    raise SystemExit(main())
