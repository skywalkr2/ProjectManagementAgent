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

Design 1.0 is complete and the launch slice is built: hand something in (your note plus pasted content), the assistant
files actions, questions, facts and notes with the evidence for each, names become people (or a "who is this?" question),
undo from the change log, What changed and Follow-ups by person with Copy and Mark sent, off-device backups with a nag, an
evaluation harness for choosing a model, and a web UI that works at any base path, by keyboard and on a phone. Not yet
real-world tested with a live AI account. See the plan in [`docs/project/`](docs/project/).

## Try it

Needs Python 3.12 or newer with [uv](https://docs.astral.sh/uv/), and Node 22.12 or newer with npm for the web UI.

```
uv sync
npm --prefix web ci && npm --prefix web run build            # the web UI
uv run cockpit init /tmp/lantern --from workspaces/demo-b   # a fictional imprint
uv run cockpit serve --workspace /tmp/lantern               # prints a link to open
```

The fictional workspace uses a stand-in AI that files whatever you hand in as a note. To use a real account, add it to the
workspace's `config/ai.yaml` with its key as a reference (`auth: env:MY_AI_KEY`, never the key itself) and point the
`routine` and `deep` tiers at it. Then check every tier with one small live call each:

```
MY_AI_KEY=... uv run cockpit ai test --workspace /tmp/lantern
``` Before relying on a model, score it on the fictional cases:

```
MY_AI_KEY=... uv run cockpit evaluate --from workspaces/demo-b --ai-config /tmp/lantern/config/ai.yaml \
    --account <provider>/<model> --runs 3
```

Checks, run before finishing any change:

```
uv run ruff check . && uv run pytest && uv run python -m engine.selfcheck
npm --prefix web test && npm --prefix web run build && npm --prefix web run e2e
```

## License

[Apache License 2.0](LICENSE). You may use, change and share it, including at work and in commercial settings, as long as
you keep the copyright notice and the [`NOTICE`](NOTICE) file. The license also grants a patent license from every
contributor, which ends for anyone who sues over patents in the project.

## Documents

- [`docs/design/`](docs/design/README.md): the full product design, one file per part, and the build plan
- [`docs/design/CHANGES.md`](docs/design/CHANGES.md): what changed since the first version of the design, and why
- [`docs/project/`](docs/project/): charter, scope, risks, schedule and the [roadmap to 1.0](docs/project/roadmap-to-1.0.md)
- [`docs/decisions.md`](docs/decisions.md): product decisions and why they were made
- [`CLAUDE.md`](CLAUDE.md): working rules for coding agents in this repository
