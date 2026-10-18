# Desktop build draft

Copy `build_support/` and `.github/workflows/desktop.yml` into the application repository. The supplied `tests/`, `pytest.ini`, and `ruff.toml` are optional draft checks; merge them with existing test configuration. Do not replace the application's package metadata. This directory is a build-file draft, not a copy of the application.

## What it produces

Pushing a matching version tag builds three unsigned test artifacts:

| Runner | Python architecture | Output |
| --- | --- | --- |
| `macos-15` | arm64 | `Thimbleby-VERSION-macos-arm64.dmg` containing `Thimbleby.app` |
| `macos-15-intel` | x64 | `Thimbleby-VERSION-macos-x86_64.dmg` containing `Thimbleby.app` |
| `windows-2022` | x64 | `Thimbleby-VERSION-windows-x64-setup.exe` |

Every job uploads its installer and `SHA256SUMS.txt` as a workflow artifact. It does not create a public release, send a notification, or install the application for a tester. Hashes detect changed bytes; they do not authenticate a download source.

## Choices

1. **Build natively per architecture.** PyInstaller is not a cross-compiler. Native Python and dependency wheels avoid pretending an Intel-only dependency supports arm64. The macOS spec uses the current interpreter's architecture explicitly. This draft declares macOS 15 as its minimum; lower that only after building and testing compatible native dependencies on the intended older systems.
2. **Use one-folder builds.** Dependencies remain beside the executable, avoiding one-file extraction at launch. The macOS folder becomes an app bundle; the Windows folder is copied in full by the installer. UPX and binary stripping are off to reduce avoidable packaging changes.
3. **Wrap the actual console entry function.** `launcher.py` calls `engine.cli:main`, matching `cockpit`, and calls `freeze_support()` before importing application code. It invents no command-line subcommand. Verify that running `cockpit` with no arguments already starts the server and opens the browser; if a subcommand is required, supply that explicit startup contract before changing the wrapper.
4. **Use windowed executables.** `console=False` suppresses the Windows console and creates a normal macOS app. A runtime hook supplies null stdout/stderr for libraries that inspect streams. Configure real application logs in the user's writable logs folder; terminal output is not a substitute. The app must not prompt for terminal input during desktop startup.
5. **Bundle resources with their relative layout.** `web/dist`, `engine/defaults`, `engine/guide`, `prompts`, and `plugins` are required and bundled at those destinations. Missing folders and missing `web/dist/index.html` fail the build. Screens must already be built; no unpinned frontend toolchain is run here. Engine and bundled plugin modules are collected for dynamic imports, along with installed distribution metadata. Conditional imports in third-party add-ons may still need targeted hooks after testing.
6. **Install per user.** `PrivilegesRequired=lowest` avoids requesting administrator rights. The default location is `{localappdata}\Programs\Thimbleby`; Start menu and optional desktop shortcuts are user-specific. The stable AppId enables upgrades. Restart Manager is asked to close running application files. The installer removes the old `_internal` bundle before replacing it so obsolete bundled files do not survive upgrades; do not store user data there. Uninstall does not explicitly delete user data folders.
7. **Leave public signing out for now.** There is no signing identity, notarization step, or Windows signing command. PyInstaller still performs its necessary ad-hoc macOS signing; “unsigned” here means no verified publisher identity. Testers may encounter operating-system security prompts. No protections are disabled by the scripts.
8. **Pin the tools and require locked app dependencies.** Python is 3.12.15, pip 25.2, PyInstaller 6.22.3, and the installer compiler 6.4.3. Action revisions are pinned by full commit SHA with version comments. The compiler installer is downloaded from a versioned release and checked against its recorded SHA-256 before execution. Hosted runner images and bundled system tools still change under their versioned labels, so this is not a claim of byte-for-byte reproducible builds.

## Required integration before tagging

The application's dependencies and build backend were not supplied. Commit these three complete dependency locks; the workflow refuses to resolve floating dependencies during a release:

```text
build_support/locks/macos-arm64.txt
build_support/locks/macos-x86_64.txt
build_support/locks/windows-x64.txt
```

Generate each on its matching native builder using Python 3.12.15. A starting command, using a separately installed pinned pip-tools 7.5.0 environment, is:

```text
python -m piptools compile pyproject.toml build_support/requirements-build.in --all-build-deps --generate-hashes --output-file build_support/locks/TARGET.txt
```

Replace TARGET with the corresponding name. Include any desktop extras the project actually requires using that tool's `--extra` option. If the project uses a different dependency system, export its equivalent complete, hash-locked requirements instead. Review the generated locks, confirm the project's build backend is included, and commit them. This draft intentionally contains no fabricated application lockfiles.

The workflow installs the lock with `--require-hashes`, then the source project with `--no-deps --no-build-isolation`. All backend dependencies must therefore already be in the lock. Dynamic build-backend behavior may require adapting the lock procedure to this project. `pip check`, the pinned PyInstaller check, and console-entry discovery catch some integration errors.

The package version in the tagged source must equal the tag after dropping `v`. Supported examples are `v0.1.0`, `v0.1.0rc1`, and `v0.1.0.post1`. Numeric version components must fit 16 bits. Installer and bundle numeric versions use the three release components; prerelease/post-release suffixes remain in filenames and display metadata. They are not distinct numeric installer build revisions in this draft. Decide a monotonic numeric build scheme before relying on automatic upgrades between such builds.

Confirm `app.thimbleby.desktop` is the intended permanent bundle identifier before shipping. No custom icon was supplied; add `.icns` and `.ico` resources when available.

## Runtime requirements and manual checks

Read bundled files relative to the frozen resource root, normally `sys._MEIPASS`, or a package's frozen `__file__`, rather than the current working directory. PyInstaller rearranges resources inside macOS bundles and provides its runtime resource paths. Finder does not promise the repository working directory. Treat the whole installed bundle as read-only; store data, logs, cache, and installed add-ons in user folders outside it. Bundled plugins are starting resources, not a writable add-on installation directory.

Binding to loopback, waiting for readiness, opening the browser once, enforcing a single instance, and offering a clean Quit path belong to `engine.cli:main` and its launcher. Build files cannot add those behaviors to an unknown entry point. Uvicorn should run with reload off and one worker in a frozen desktop process. Confirm any dynamically selected protocols or external add-on dependencies are actually bundled.

Before distributing, run the resulting artifact on each target: open it outside the repository, confirm the browser loads prebuilt screens, check guide/default/prompt/plugin reads, launch a second copy, quit cleanly, upgrade over the prior version, and uninstall without deleting personal data. Test Windows with a standard account and macOS from the copied Applications bundle. Native builders and these launch checks have not been run in this draft workspace.

## Draft validation

The included pytest file checks tag validation, resource destinations, the entry-point wrapper, both specs with mocked builder APIs, installer policy, tool pins, and workflow structure. These are structural checks, not native build or launch verification. Tests use no sleeps or network calls; reading the draft files is necessary for validating build configuration. Packaging scripts themselves necessarily access files and execute native tools.

Local validation used Python 3.12.15, packaging 26.3, pytest 9.1.1, ruff 0.17.1, and PyYAML 6.0.3. Run `python -m pytest -q`, `ruff check .`, and `ruff format --check .`. Spec files suppress lint warnings only for builder-injected names and imports that follow the spec's path setup.

Sources by name: PyInstaller 6.22.3 spec-file, runtime-information, multiprocessing, windowed-stream, and macOS-signing documentation; hosted-runner documentation; action release pages; Inno Setup PrivilegesRequired, constants, and release documentation; Python 3.12.15 release notes. The compiler checksum was checked against its official release asset metadata.
