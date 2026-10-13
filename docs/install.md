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

## Start your own workspace

```sh
cockpit
```

The first time, this makes your workspace in a `Cockpit` folder in your home folder and opens it; after that it reopens
the workspace you used last. For a workspace elsewhere: `cockpit init <folder>`, then `cockpit serve -w <folder>`.

The workspace starts empty, and nothing in it needs a file edited. The first screen is the setup walkthrough: your
name, your AI account (with a test), your mail and calendar, a backup folder and the people you work with. Each step can
be skipped and done later from Settings. Keep workspaces in your home folder, not in a temporary folder.
[`getting-started.md`](getting-started.md) follows the same path step by step, with what each step costs.

## Update

- **A package install:** run the install step above again with the newer package file.
- **A source checkout:** run `cockpit update` (with `uv run` in front when you run from the checkout). It pulls the
  newest version, brings the Python environment up to date without removing add-ons you installed from the screen,
  installs the web tools and rebuilds the screens, printing each step. It stops at the first step that fails and names
  it with its exit code, and it refuses when you have changes of your own in the checkout. It ends with the old and new
  version, or "Already up to date", and tells you that a running app shows **Restart now**. If Node isn't installed it
  skips the web steps and says the screens weren't rebuilt. On a package install it prints the install step instead.

## Add an add-on from its file

When an add-on's publisher gives you a package file (a `.whl`) instead of a listing with an Install button, run:

```
cockpit install <the file>
```

From a source copy, use `uv run cockpit install <the file>` in its folder. It installs the same way as the Add-ons
screen's Install button: only add-ons of pure Python whose needs the app already has. `cockpit update` keeps it. Then
turn it on in the app (Add-ons, or the walkthrough's Mail and calendar step); it starts after a restart.

## Restore from a backup

Backups are dated folders in the backup folder you chose. To make a workspace from one:

```sh
cockpit restore --backup ~/Backups/cockpit-20261009-140000 ~/cockpit-restored
cockpit serve -w ~/cockpit-restored
```

The command checks the backup's database first, then copies it, with the settings, sources, files and texts the backup
holds, into the new folder. It refuses a folder that already has files and never changes the backup or the workspace
you are running. The restored workspace is free to open on this computer even if the backup was made while another
computer had it open.

## Try an add-on on made-up data

```sh
cockpit demo
```

This is a sandbox for trying an add-on (`cockpit demo --plugin <its folder>`), not a place to start. It makes a demo
workspace in `~/cockpit-demo` (a made-up small press with made-up people) and opens it in your browser. Every screen says
it is a demo. It works without an AI account: a stand-in answers instead, so you can see the whole loop.
`cockpit demo --fresh` starts the demo over; `cockpit demo --which demo-a` uses the other demo, the project office of a
made-up freight company. The two fictional workspaces are test fixtures; don't build real work in them.

## Uninstall

```sh
uv tool uninstall pm-cockpit
```

Your workspace folders stay where they are.
