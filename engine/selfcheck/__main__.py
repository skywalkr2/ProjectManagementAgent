import argparse
from pathlib import Path

from engine.selfcheck import run

parser = argparse.ArgumentParser(prog="python -m engine.selfcheck")
parser.add_argument("--workspace", "-w", type=Path, help="also scan code against this private workspace's specifics")
args = parser.parse_args()
raise SystemExit(run(private_workspace=args.workspace))
