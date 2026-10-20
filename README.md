# PM Cockpit

An AI-assisted cockpit for running projects. It watches your sources, has an assistant draft updates, questions and action
items, and gives you one screen to review, correct and send them out. **The AI drafts; you approve everything that goes out.**

It is becoming Thimbleby, a daily assistant for anyone juggling work, not only project managers: it keeps track of what you
promised and what was promised to you, and gets the next step ready. Until the installers phase renames things, the code
and these docs still say PM Cockpit.

The core is a generic base: the watch, triage, draft, review and send-out loop, plus the safety rules around it. Everything
specific to one kind of work comes from plugins:

- **Connectors** bring inputs in (wikis, trackers, folders, mailboxes, feeds).
- **Channels** take approved content out (pages, messages, email, posts). Only Copy is built so far: you paste the approved
  text where it goes, and nothing is sent for you.
- **Packs** bundle record types, templates, prompts and panels for one use. Packs live in their own repositories; the first
  in real use are a writing pack, a project management pack and a publishing pack for a small imprint, and a workplace
  status-reporting pack is the reference (design Part 9). This repository holds the core, the define-your-own kit and an
  example add-on.

Any AI vendor can be used through configuration.

It runs on your own computer today, reachable only from that computer. Running it on a server you control, for example under
a path such as `https://example.com/admin`, with sign-in and start-up security checks, is planned (design Part 11) and isn't
available yet: the app refuses to start in hosted mode. Branding, layout, wording, schedules and storage are settings, so you
can change an installation without changing code.

## Status

The core loop and the screens are built: hand something in (one box, and whose words they are); the assistant files
actions, questions, facts, notes and promises with the evidence for each; names become people (or a "who is this?"
question); Today is the home, a ranked list of what needs you, with Top priorities and This week beside it; What changed
and Follow-ups, by person or by project, with Copy (formatted and plain together) and Mark sent; undo from the change log;
off-device backups with a reminder; learning from corrections; opt-in notices; calendars from .ics links and files; several
accounts of one mail or calendar service; and an evaluation harness for choosing a model. The web UI works at any base
path, by keyboard and on a phone.

Not built yet: sending mail or changing a calendar for you (only Copy); installers for people who never open a terminal
(today you install from a package file with a script, or run a checkout); running it on a server (it refuses to start in
hosted mode); and the rest of the daily assistant (reminders, briefings, meeting prep). Its owner has run it on a real AI
account and fixed what that found; the measured week on real mail and any outside testing are still ahead. The plan is in
[`docs/project/`](docs/project/), and what is built and what is left is in its
[roadmap](docs/project/roadmap-to-1.0.md).

## Try it

New here? [`docs/getting-started.md`](docs/getting-started.md) takes you from the install command to your first
result, step by step, with what each step costs. To install from a package file, without the source or Node, see [`docs/install.md`](docs/install.md). From a
checkout:

Needs Python 3.12 or newer with [uv](https://docs.astral.sh/uv/), and Node 22.12 or newer with npm for the web UI.

```
uv sync
npm --prefix web ci && npm --prefix web run build   # the web UI
uv run cockpit                                      # starts your workspace and opens it
```

That one command is all you need: the first time it makes your workspace (a `Cockpit` folder in your home folder) and
opens the walkthrough; after that it reopens the workspace you used last (never one in a temporary folder, such as a
test run's). `uv run cockpit update` updates.
The first time you run it from the checkout (on macOS or Linux), it also makes `cockpit` work in any folder, so after
that you can leave out `uv run` and the trip to the checkout.

The workspace starts empty. The first screen is a setup walkthrough of about 10 to 20 minutes: your name, your AI account
(a recommended service with numbered steps; the key is checked as you paste it), your mail and calendar (installed, turned
on and signed in on the screen, with one restart you press), a backup folder (the cloud-drive folders found on the computer
are offered by name) and the people you work with. You never edit a file, and nothing is spent until you press Go at the end. For a workspace elsewhere, `uv run cockpit init <folder>`
then `uv run cockpit serve -w <folder>`.

Keep the workspace in your home folder: the system's temporary folders (`/tmp`) are emptied when the computer restarts,
and the setup would go with them. `cockpit serve` says when the web screens are out of date.

To update a checkout, run `uv run cockpit update`. It pulls the newest version, brings the Python environment up to date
without removing add-ons you installed from the screen, rebuilds the web screens, and says whether the running app
shows Restart now. It stops if you have changes of your own in the checkout. To make a new workspace from one of your
backups, run `uv run cockpit restore --backup <the dated backup folder> <a new folder>`; it never changes the backup.

### Trying an add-on on made-up data

`uv run cockpit demo` makes a sandbox workspace of made-up data and serves it, for trying an add-on
(`cockpit demo --plugin <its folder>`). The two fictional workspaces in `workspaces/` are test fixtures and that
sandbox, never a place to start real work.

### Choosing a model

Before relying on a model, score it on the fictional cases. This costs real money on your own account, so it is a
deliberate step, not part of the start:

```
uv run cockpit evaluate -w ~/cockpit --from workspaces/demo-b --runs 3
```

`--from workspaces/demo-b` supplies the cases; `-w` supplies your workspace's AI account. Add
`--account <provider>/<model>` to score another account.

### Checks

Run before finishing any change:

```
uv run ruff check . && uv run ruff format --check . && uv run pytest && uv run python -m engine.selfcheck
npm --prefix web test && npm --prefix web run build && npm --prefix web run e2e
```

For development, set `COCKPIT_CHECK_WORDING=1` to check the words the screen shows. With it on, a response field the
server writes for a person to read, or an error message, that names a settings file, a secret reference, a settings key,
a manifest field or a command is refused with the problem found. The tests and the browser tests' server turn it on
themselves. It is a developer switch, not a setting, and does nothing when unset.

## Troubleshooting

- **`Failed to spawn: cockpit`**: run the command from the repository folder (where `pyproject.toml` is), or use
  `uv run --project <the repository folder> cockpit ...` from elsewhere.
- **`No module named 'engine'`** on a Mac with iCloud Drive's Desktop & Documents folders turned on: iCloud can hide the
  installed package's link file. Move the repository out of Documents (for example to `~/code`) and run `uv sync` again, or
  run `uv run python -m engine.cli ...` from the repository folder instead of `uv run cockpit ...`.
- **"The AI account refused the key"**: the message gives the account's own reason in parentheses. Check the key with the
  provider, then run `cockpit ai test`; it says which environment variable or file the key was read from (never the key).
- **The screens look old after `git pull`**: run `uv run cockpit update`, or `npm --prefix web run build`.

## License

[Apache License 2.0](LICENSE). You may use, change and share it, including at work and in commercial settings, as long as
you keep the copyright notice and the [`NOTICE`](NOTICE) file. The license also grants a patent license from every
contributor, which ends for anyone who sues over patents in the project.

## Documents

- [`docs/design/`](docs/design/README.md): the full product design, one file per part, and the build plan
- [`docs/design/CHANGES.md`](docs/design/CHANGES.md): what changed since the first version of the design, and why
- [`docs/project/`](docs/project/): charter, scope, risks, schedule and the [roadmap to 1.0](docs/project/roadmap-to-1.0.md)
- [`docs/decisions.md`](docs/decisions.md): product decisions and why they were made
- [`CLAUDE.md`](CLAUDE.md): working rules for coding agents in this repository ([`AGENTS.md`](AGENTS.md) points other agents to it)
