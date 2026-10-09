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

Design 1.0 is complete. The first half of the launch slice is built: the database with its change log, export and import,
configuration, the self-check, two fictional workspaces and a local server. See the plan in [`docs/project/`](docs/project/).

## Try it

Needs Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run cockpit init /tmp/lantern --from workspaces/demo-b   # a fictional imprint
uv run cockpit serve --workspace /tmp/lantern               # prints a link to open
uv run python -m engine.selfcheck                           # the product's own checks
uv run pytest
```

## Documents

- [`docs/design/`](docs/design/README.md): the full product design, one file per part, and the build plan
- [`docs/design/CHANGES.md`](docs/design/CHANGES.md): what changed since the first version of the design, and why
- [`docs/project/`](docs/project/): charter, scope, risks and schedule
- [`docs/decisions.md`](docs/decisions.md): product decisions and why they were made
- [`CLAUDE.md`](CLAUDE.md): working rules for coding agents in this repository
