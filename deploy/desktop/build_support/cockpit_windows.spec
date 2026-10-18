# Build a windowed executable and a folder containing its dependencies.
import sys
from pathlib import Path

sys.path.insert(0, SPECPATH)
from freeze_common import freeze_inputs

root = Path(SPECPATH).parent
inputs = freeze_inputs(root, "win32")
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
    contents_directory="_internal",
)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Thimbleby")
