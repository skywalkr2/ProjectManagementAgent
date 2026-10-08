# PM Cockpit

An AI-assisted cockpit for running projects. It watches your sources, has an assistant draft updates, questions and action
items, and gives you one screen to review, correct and send them out. **The AI drafts; you approve everything that goes out.**

The core is a generic base: the watch, triage, draft, review and send-out loop, plus the safety rules around it. Everything
specific to one kind of work comes from plugins:

- **Connectors** bring inputs in (wikis, trackers, folders, mailboxes, feeds).
- **Channels** take approved content out (pages, messages, email, posts).
- **Packs** bundle record types, templates, prompts and panels for one use. The first is a workplace status-reporting pack;
  publishing support, personal projects and social media are planned.

Any AI vendor can be used through configuration.

## Status

Design stage. Nothing is built yet.

## Documents

- [`docs/DESIGN.md`](docs/DESIGN.md): the full product design and build plan
- [`docs/decisions.md`](docs/decisions.md): product decisions and why they were made
- [`CLAUDE.md`](CLAUDE.md): working rules for coding agents in this repository
