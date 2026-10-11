# Kickoff template for a plugin repository

Every plugin kept in its own repository is built by its own autonomous session, so its feedback on the plugin API is
independent (decisions, 2026-10-11). When this project suggests a new plugin repository, it gives the owner a kickoff
brief built from this template: the sections below, with the plugin's own purpose, scope and order of work filled in.
The owner pastes it as the new session's first message.

---

## 1. The host and the contract

- PM Cockpit's public repository is the host. Read it read-only (clone it into a scratch folder); never write to it,
  and never open issues or pull requests there.
- **The contract is the generated developer guide**, `docs/plugin-guide.md` on the host's working branch, plus the
  change notes in `docs/plugin-api-0.x.md`. Build only against names that appear there. Something the design
  describes but the guide doesn't have doesn't exist yet: ask (section 4).
- Import only `engine.plugin_api`. Never the host's internals, never another plugin. Identifiers are namespaced
  `<plugin>/<name>`. Declare everything in `plugin.yaml`.
- One source of truth: refer to core records by id (`RefTo`), never copy their names or fields into your own records;
  fields with a known set of values take them from a value list, not free text.
- For tests, install the host without its web screens:
  `PM_COCKPIT_WITHOUT_SCREENS=1 uv pip install "pm-cockpit @ git+<host repository>@<branch>"`, and test connectors
  with `engine.plugin_api.testing`. Try the plugin on made-up data with `cockpit demo --plugin <its folder>`.

## 2. What you build

The plugin's purpose, what it adds, what it reaches (services, programs, data levels), and what is out of scope.

## 3. How you work

- Python 3.12+, uv, pytest, ruff; tests never touch the network; fixtures are fictional.
- Write `CLAUDE.md` first with these rules, then `docs/decisions.md`, `docs/host-questions.md` and `docs/friction.md`.
- Small commits with tests passing, pushed to your working branch. No pull request unless the owner asks.
- Never commit a secret, a token, an account id or anything from a person's real data.

## 4. How you talk to the host

- **Questions:** rounds in `docs/host-questions.md` (`# Round N (not yet sent, YYYY-MM-DD)`), each question saying
  what you need, why, what you do meanwhile and whether it blocks you. Write them generically, as features any plugin
  could use: the host's public repository never names private plugins.
- **Tell the host** with `send_message` to the host's session (its id is in your kickoff message): one short line per
  question. The host also reads your file on its own schedule.
- **Answers** come as plugin API versions: record "sent; answered in 0.3.N" on the round and adopt them.
- **Friction log:** `docs/friction.md`, everything in the guide that was unclear, wrong, missing or needed a
  workaround, with the guide section. Send it with a round. Be blunt.
- Arm a check-in about every 60 minutes with `send_later` while you work.

## 5. Publishing

Follow the guide's "Publishing a pack" section exactly; in short:

1. Release in your own repository: version in `plugin.yaml`, what changed, tests, a tag, the package built by your
   own checks.
2. Keep your catalog entry in `catalog/pack.yaml` (the catalog repository's README has the format).
3. Run `cockpit pack check <your plugin folder> --entry catalog/pack.yaml`; every line must pass.
4. Add a **Publish request** to `docs/host-questions.md`: the pack, version and tag, what changed, the check's
   output, and whether the owner has said it may be listed publicly. Tell the host's session.
5. The host verifies and opens a pull request on the catalog; **the owner merges it**. You never write to the
   catalog.

## 6. What the owner does

Anything only the owner can do (accounts, app registrations, keys, listing decisions), as numbered steps in your
README, kept current.

## 7. Order of work

The smallest useful slice end to end first, then the rest, then the owner's live check, then publishing.
