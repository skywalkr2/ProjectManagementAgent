# Desktop build files: a phase I draft, not switched on

Drafted with an outside assistant (2026-10-18) and kept here, outside `.github/workflows/`, until phase I starts.
Before anything here runs:

1. **Verify every pin against its source:** the action commit hashes, PyInstaller 6.22.3, Python 3.12.15, pip 25.2,
   the `macos-15-intel` runner label, and the Inno Setup version, address and SHA-256. None was checked when drafted.
2. **One workflow per tag:** `.github/workflows/release.yml` already runs on `v*` tags; merge the desktop jobs into it
   (or give them their own tag pattern) instead of adding a second workflow on the same trigger.
3. **Commit the dependency locks** the README describes (`build_support/locks/<target>.txt`, hashed).
4. **Start the app, not the command line:** `build_support/launcher.py` calls `engine.cli:main()` with no arguments,
   which prints help. It must start the tray launcher (`engine/launcher.py`) on the workspace in the app-data folder
   (`engine/app_dirs.py`), with the base path and install token, as the roadmap's phase I items say.
5. **The name and icon** come with phase I's rename; the bundle id and Windows AppId are new identifiers to confirm.
6. Move `test_build_files.draft.py` into `tests/` once `build_support` is importable from the repository.
