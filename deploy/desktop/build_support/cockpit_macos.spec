# Build a native application bundle with its read-only resources.
import sys
from pathlib import Path

sys.path.insert(0, SPECPATH)
from freeze_common import freeze_inputs

root = Path(SPECPATH).parent
inputs = freeze_inputs(root, "darwin")
a = Analysis(
    [str(root / "build_support" / "launcher.py")],
    pathex=[str(root)],
    binaries=[],
    datas=inputs["datas"],
    hiddenimports=inputs["hiddenimports"],
    hookspath=[],
    runtime_hooks=[str(root / "build_support" / "windowed_stdio.py")],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Thimbleby",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=inputs["architecture"],
    codesign_identity=None,
    entitlements_file=None,
)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Thimbleby")
app = BUNDLE(
    collection,
    name="Thimbleby.app",
    bundle_identifier="app.thimbleby.desktop",
    info_plist={
        "CFBundleName": "Thimbleby",
        "CFBundleDisplayName": "Thimbleby",
        "CFBundleShortVersionString": inputs["numeric_version"],
        "CFBundleVersion": inputs["numeric_version"],
        "CFBundleGetInfoString": "Thimbleby " + inputs["version"],
        "LSMinimumSystemVersion": "15.0",
        "NSHighResolutionCapable": True,
    },
)
