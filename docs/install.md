# Installing PM Cockpit

PM Cockpit runs on your own computer (Windows, macOS or Linux) and opens in your browser. It needs no Node and no
copy of the source code: one package file holds the app and its screens.

## What you need

- **uv**, the Python package tool. Install it from its documentation; it fetches the right Python for you.
- **The package file**, `pm_cockpit-<version>-py3-none-any.whl`, and the install script for your computer:
  `install.sh` (macOS, Linux) or `install.ps1` (Windows).

## Install or update

In a terminal, in the folder where you saved the files:

```sh
sh install.sh pm_cockpit-<version>-py3-none-any.whl                                  # macOS, Linux
powershell -ExecutionPolicy Bypass -File install.ps1 pm_cockpit-<version>-py3-none-any.whl   # Windows
```

Updating is the same command with the newer file. Your workspaces are separate folders and are never touched by an
install or an update.

## Try the demo

```sh
cockpit demo
```

This makes a demo workspace in `~/cockpit-demo` (a made-up small press with made-up people) and opens it in your
browser. Every screen says it is a demo. It works without an AI account: a stand-in answers instead, so you can see the
whole loop. `cockpit demo --fresh` starts the demo over; `cockpit demo --which demo-a` uses the other demo, the project
office of a made-up freight company.

## Start your own workspace

```sh
cockpit init ~/cockpit/my-work
cockpit serve -w ~/cockpit/my-work --open
```

The first screen walks you through setup: your name, a starting template, your AI account (with a test), a backup
folder and your first hand-in. Keep workspaces in your home folder, not in a temporary folder.

## Uninstall

```sh
uv tool uninstall pm-cockpit
```

Your workspace folders stay where they are.
