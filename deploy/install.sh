#!/bin/sh
# Installs or updates PM Cockpit from a downloaded package file, then tells you how to start.
# Usage: sh install.sh pm_cockpit-<version>-py3-none-any.whl
# Needs uv (the Python package tool). Running it again with a newer file updates the app; workspaces are untouched.
set -eu
if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  echo "Usage: sh install.sh <the downloaded .whl file>" >&2
  exit 2
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "This needs uv, the Python package tool. Install it from its documentation, open a new terminal, and run this again." >&2
  exit 1
fi
uv tool install --force --python 3.12 "$1"
uv tool update-shell >/dev/null 2>&1 || true
echo
echo "Installed. Open a new terminal, then:"
echo "  cockpit demo                      try it on made-up data"
echo "  cockpit init ~/cockpit/my-work    start your own workspace"
echo "  cockpit serve -w ~/cockpit/my-work"
