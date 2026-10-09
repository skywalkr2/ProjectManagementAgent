# Part 12. Security and privacy

## 12.1 Access, secrets and audit

- **Two modes, one model.** Local mode listens on `127.0.0.1` and uses the install token. Hosted mode requires real sign-in and
  passes the deploy checks before it serves (Part 11). Roles for several users are later; in the base, everyone allowed in has
  full access.
- **Secrets** come from the environment, the OS keychain or a mounted file, referenced in config as `env:NAME`,
  `keychain:NAME` or `file:/path`, never stored in config or data. Hosted platforms pass them as environment secrets. Plugins
  get only the secrets their manifest names from the core's secret store.
- **Outbound is gated:** content leaves only through the publisher after the PM approves the exact content (6.12, 8.1).
- **Data levels** (open, internal, restricted) follow every source into packets, AI providers and plugins (6.16, 3.5).
- **Audit:** the ledger (5.0) records every applied op with its actor and provenance; approvals, sends, settings changes,
  sign-ins and plugin enable or disable are recorded alongside. The readable export keeps it in git history.

## 12.2 Untrusted input and the AI

Everything the cockpit watches can contain text written by someone else: an email, a page edit, a ticket comment, a social
reply. Some of it will be careless and some may be hostile ("assistant: add a rule that…", "ignore your instructions and
send…"). The model can't be relied on to tell instructions from content, so the product doesn't ask it to.

- **Provenance on everything.** Each source is `trusted` (the PM's own typed note) or `untrusted` (everything from a connector,
  and anything pasted that the PM didn't write; the paste box separates "your note" from "pasted content"). Packets mark
  untrusted parts (6.6), and every request records whether it came from an input, the PM or a schedule.
- **Tiers, not judgment.** What an input can cause is limited by op tier (6.7): it can add knowledge (data ops) and produce
  drafts that wait for approval (outbound ops). It can never change rules, watched sources, scope, facts sources, config,
  plugins or code (system ops) without the PM confirming the exact change, with the prompting source shown beside it.
- **Untrusted text doesn't become structure on its own.** An address, a name or a URL that appears only in untrusted content
  can't become a new recipient, a new person, a new watched source or a rule without passing through a hold and the PM.
- **Lookups only through configured sources.** The `lookup` op names a configured connector, fact kind or lookup step with
  validated parameters; the AI can't make the engine fetch an arbitrary URL, so a packet can't be smuggled out through a
  lookup.
- **Nothing sensitive in packets.** Secrets never; restricted content only to providers whose `allowed_data` includes it.
- **Outbound review shows provenance.** A draft built from untrusted content says so on its row, and links in outgoing text are
  shown in full before approval.
- **Tested.** The golden fixtures (6.16) include hostile inputs (embedded instructions, fake rules, requests to send or to
  watch new sources); a provider and model pass evaluation only if none of them gets a system op applied or a draft approved
  without the PM.

## 12.3 Plugins

**Plugins run in-process in the base.** That means:

- What a plugin's manifest declares (network hosts, secrets, data levels) is **shown to the PM before enabling and enforced on
  what the core hands out**: the secret store resolves only declared names, the core HTTP client allows only declared hosts,
  and packets and records at a data level the plugin excludes are never passed to it.
- It is **not a sandbox.** In-process code can bypass the core's clients. Enabling a third-party plugin means trusting its
  code, and the Admin tab says so in those words.
- **Bundled plugins** are held to the declared reach by review and by the boundary scan (10.2): they may not import network or
  process libraries directly, only the core's clients.
- Running plugins in a separate process with enforced limits is planned (Part 13, after the base).

## 12.4 Privacy and retention

- Raw source text is kept for as long as `config/storage.yaml` `retention` says (4.15); after that only the facts recorded from
  it and the ledger's note that it existed remain.
- **Export a person** (everything stored about them) and **forget a person** (delete or anonymize per `forget_person`) are
  Admin actions, recorded in the ledger.
- Hosted mode defaults to shorter retention for mail and replies than local mode.

## 12.5 Internet-facing hygiene (hosted)

Dependencies pinned and scanned in CI; the container runs as a non-root user with a read-only file system apart from the
workspace volume; uploaded files are stored as data, never executed, and served only as downloads; the database file is never
served.
