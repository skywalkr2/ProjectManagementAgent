# PM Cockpit

An AI-assisted cockpit for running projects. It watches your sources, has an assistant draft updates, questions and action
items, and gives you one screen to review, correct and send them out. **The AI drafts; you approve everything that goes out.**

The core is a generic base: the watch, triage, draft, review and send-out loop, plus the safety rules around it. Everything
specific to one kind of work comes from plugins:

- **Connectors** bring inputs in (wikis, trackers, folders, mailboxes, feeds).
- **Channels** take approved content out (pages, messages, email, posts).
- **Packs** bundle record types, templates, prompts and panels for one use. The first is publishing support for a small imprint;
  a workplace status-reporting pack is the reference, and personal projects and social media are planned.

Any AI vendor can be used through configuration.

It runs either on your own computer or on a web host you control, for example under a path such as
`https://example.com/admin`, with sign-in and start-up security checks. Branding, layout, wording, schedules, sign-in and
storage are all settings, so you can change an installation without changing code.

## Status

Design 1.0 is complete and the launch slice is built: hand something in (one box, and whose words they are), the assistant
files actions, questions, facts and notes with the evidence for each, names become people (or a "who is this?" question),
undo from the change log, What changed and Follow-ups by person with Copy and Mark sent, off-device backups with a nag, an
evaluation harness for choosing a model, and a web UI that works at any base path, by keyboard and on a phone. Not yet
real-world tested with a live AI account. See the plan in [`docs/project/`](docs/project/).

## Try it

Needs Python 3.12 or newer with [uv](https://docs.astral.sh/uv/), and Node 22.12 or newer with npm for the web UI.

```
uv sync
npm --prefix web ci && npm --prefix web run build            # the web UI
uv run cockpit init ~/cockpit-try --from workspaces/demo-b  # a fictional imprint
uv run cockpit serve --workspace ~/cockpit-try              # prints a link to open
```

Keep the workspace in your home folder: the system's temporary folders (`/tmp`) are emptied when the computer restarts, and
the AI setup would go with them. After a `git pull`, rebuild the web screens (`npm --prefix web run build`); the server shows
whatever was last built, and `cockpit serve` says when that is out of date.

The fictional workspace uses a stand-in AI that files whatever you hand in as a note. To use a real account, add it to the
workspace's `config/ai.yaml` with its key as a reference (`auth: env:MY_AI_KEY`, never the key itself) and point the
`routine` and `deep` tiers at it. Then check every tier with one small live call each:

```
MY_AI_KEY=... uv run cockpit ai test --workspace ~/cockpit-try
``` Before relying on a model, score it on the fictional cases:

```
MY_AI_KEY=... uv run cockpit evaluate --from workspaces/demo-b --ai-config ~/cockpit-try/config/ai.yaml \
    --account <provider>/<model> --runs 3
```

Your own workspace lives outside this repository (keep it on local disk, not in a synced folder):

```
uv run cockpit init ~/cockpit/my-press --you "Your Name" --name "My Press" --assistant "Quill"
```

Then copy the AI account setup into its `config/ai.yaml`, run `cockpit ai test`, start it with `cockpit serve`, and add
your people and projects under **People & projects**.

Checks, run before finishing any change:

```
uv run ruff check . && uv run pytest && uv run python -m engine.selfcheck
npm --prefix web test && npm --prefix web run build && npm --prefix web run e2e
```

## Troubleshooting

- **`Failed to spawn: cockpit`**: run the command from the repository folder (where `pyproject.toml` is), or use
  `uv run --project <the repository folder> cockpit ...` from elsewhere.
- **`No module named 'engine'`** on a Mac with iCloud Drive's Desktop & Documents folders turned on: iCloud can hide the
  installed package's link file. Move the repository out of Documents (for example to `~/code`) and run `uv sync` again, or
  run `uv run python -m engine.cli ...` from the repository folder instead of `uv run cockpit ...`.
- **"The AI account refused the key"**: the message gives the account's own reason in parentheses. Check the key with the
  provider, then run `cockpit ai test`; it says which environment variable or file the key was read from (never the key).
- **The screens look old after `git pull`**: run `npm --prefix web run build`.

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
