# Working rules for coding agents

The rules for working in this repository are in [`CLAUDE.md`](CLAUDE.md). They apply to every coding agent and every person,
not only one tool: read it first and follow it exactly. In short:

- Read `docs/design/README.md` and the design parts it names before changing anything; the plan and the current checklist are
  in `docs/project/` (`roadmap-to-1.0.md`).
- A change to scope or design needs a one-line impact note in `docs/decisions.md` first.
- Keep the boundary: no specific people, companies, hosts or URLs in code; no vendor names outside `engine/ai/adapters/`.
- Before finishing, run all the checks and fix what fails:
  `uv run ruff check .` · `uv run ruff format --check .` · `uv run pytest` · `uv run python -m engine.selfcheck` ·
  `npm --prefix web test` · `npm --prefix web run build` · `npm --prefix web run e2e`
- After changing an API model, run `uv run python -m api.openapi`.
- Pull before you start and push only to the branch you were given. Never rewrite pushed history.
