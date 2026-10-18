"""Run explicit packaging steps in the build environment."""

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
from pathlib import Path

from build_model import release_versions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=("prepare", "dmg", "hashes"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    if args.step == "prepare":
        version, numeric = release_versions(os.environ["RELEASE_TAG"])
        with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as output:
            output.write(f"APP_VERSION={version}\nWINDOWS_VERSION={numeric}\n")
    elif args.step == "dmg":
        if platform.system() != "Darwin":
            raise SystemExit("Create a disk image on a native macOS builder")
        version, _ = release_versions("v" + os.environ["APP_VERSION"])
        architecture = platform.machine().lower()
        if architecture not in {"arm64", "x86_64"}:
            raise SystemExit("Unknown build architecture")
        app = root / "dist" / "Thimbleby.app"
        if not app.is_dir():
            raise SystemExit("The application bundle is missing")
        stage = root / "build" / "dmg-stage"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True)
        subprocess.run(["ditto", str(app), str(stage / app.name)], check=True)
        (stage / "Applications").symlink_to("/Applications")
        destination = root / "dist" / f"Thimbleby-{version}-macos-{architecture}.dmg"
        subprocess.run(
            [
                "hdiutil",
                "create",
                "-volname",
                "Thimbleby",
                "-srcfolder",
                str(stage),
                "-ov",
                "-format",
                "UDZO",
                str(destination),
            ],
            check=True,
        )
    else:
        artifacts = sorted(
            path for path in (root / "dist").iterdir() if path.suffix in {".dmg", ".exe"} and path.is_file()
        )
        if not artifacts:
            raise SystemExit("No installer artifacts were created")
        lines = []
        for artifact in artifacts:
            with artifact.open("rb") as payload:
                checksum = hashlib.file_digest(payload, "sha256").hexdigest()
            lines.append(f"{checksum}  {artifact.name}\n")
        (root / "dist" / "SHA256SUMS.txt").write_text("".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
