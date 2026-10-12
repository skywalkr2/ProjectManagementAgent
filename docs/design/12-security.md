# Part 12. Security and privacy

## 12.1 Access, secrets and audit

- **Two modes, one model.** Local mode listens on `127.0.0.1` and uses the install token. Hosted mode requires real sign-in and
  passes the deploy checks before it serves (Part 11). Version 1 is local only; hosted mode is built after 1.0. Roles for
  several users are later; in the base, everyone allowed in has full access.
- **Secrets** come from the environment, the OS keychain or a mounted file, referenced in config as `env:NAME`,
  `keychain:NAME` or `file:/path`, never stored in config or data. Hosted platforms pass them as environment secrets. Plugins
  get only the secrets their manifest names from the core's secret store. Built: `env:` and `file:`, and a key pasted on a
  screen, which is kept in a private folder of the workspace that only its owner can read and referred to as `file:`. **Not yet
  built:** `keychain:NAME` is refused with a message, and the core mailbox and calendar sources still take their secrets only as
  `env:` or `file:` references, to be entered on screen like an AI key (roadmap A2).
- **Outbound is gated:** content leaves only through the publisher after the PM approves the exact content (6.12, 8.1).
- **Data levels** (open, internal, restricted) decide which AI providers and plugins may see a source (6.16, 3.5; built).
  **Audiences** decide where its content may appear: each destination is open or a named group, and each restriction names the
  audiences it allows (4.1, 6.7; not yet built).
- **Audit:** the ledger (5.0) records every applied op with its actor and provenance; approvals, sends, settings changes,
  sign-ins and plugin enable or disable are recorded alongside. The readable export keeps it in git history. Built: the
  ledger, approvals and settings changes (as `setting_change` records). **Partly built:** there is no separate log of
  sign-ins or of turning a plugin on or off. **Not yet built:** the scheduled export that would put the history in git
  (`storage.export.every_minutes` and `.remote` are read by nothing).

## 12.2 Untrusted input and the AI

Everything the cockpit watches can contain text written by someone else: an email, a page edit, a ticket comment, a social
reply. Some of it will be careless and some may be hostile ("assistant: add a rule that…", "ignore your instructions and
send…"). The model can't be relied on to tell instructions from content, so the product doesn't ask it to.

- **Provenance on everything.** Each source is `trusted` (the PM's own typed note) or `untrusted` (everything from a connector,
  and anything pasted that the PM didn't write; the paste box separates "your note" from "pasted content"). Packets mark
  untrusted parts (6.6), and every request records whether it came from an input, the PM or a schedule.
- **Tiers, not judgment.** What an input can cause is limited by op tier (6.7): it can add knowledge (data ops) and produce
  drafts that wait for approval (outbound ops). It can never change rules, watched sources, scope, facts sources, config,
  or plugins (system ops); and nothing can change the product's code at all (6.13) without the PM confirming the exact change, with the prompting source shown beside it. System
  ops from the PM's own note apply at once with a read-back and Undo; the risk there is misreading, not injection.
- **Untrusted stays untrusted.** Anything derived from untrusted content (a fact, a glossary meaning, a lesson) keeps that
  provenance, and packets show it as data wherever it appears. Lessons from inputs are only proposed until the PM accepts them,
  so an injected "lesson" can't become standing guidance (6.22). Records carry their trust today; lessons and the glossary are
  not built.
- **Evidence must exist.** Ops that claim something must quote words that are really in the cited source (6.7).
  Built.
- **Untrusted text doesn't become structure on its own.** An address, a name or a URL that appears only in untrusted content
  can't become a new recipient, a new person, a new watched source or a rule without passing through a hold and the PM.
- **Lookups only through configured sources.** The `lookup` op names a configured connector, fact kind or lookup step with
  validated parameters; the AI can't make the engine fetch an arbitrary URL, so a packet can't be smuggled out through a
  lookup. Not yet built: there is no `lookup` op.
- **Nothing sensitive in packets.** Secrets never; restricted content only to providers whose `allowed_data` includes it.
- **Outbound review shows provenance.** A draft built from untrusted content says so on its row, and links in outgoing text are
  shown in full before approval. Not yet built: there is no outbound review until the publisher and Waiting to go out exist.
- **Tested.** The golden fixtures (6.16) include hostile inputs (embedded instructions, fake rules, requests to send or to
  watch new sources); a provider and model pass evaluation only if none of them gets a system op applied or a draft approved
  without the PM. Partly built: two hostile cases exist (a standing rule, an admin mode); cases for requests to send and to
  watch new sources do not.

## 12.3 Plugins

**Plugins run in-process in the base.** That means:

- What a plugin's manifest declares (network hosts, secrets, data levels) is **shown to the PM before enabling and enforced on
  what the core hands out**: the secret store resolves only declared names, the core HTTP client allows only declared hosts,
  and packets and records at a data level the plugin excludes are never passed to it.
- It is **not a sandbox.** In-process code can bypass the core's clients. Enabling a third-party plugin means trusting its
  code, and the Admin tab says so in those words.
- **Bundled plugins** are held to the declared reach by review and by the boundary scan (10.2): they may not import network or
  process libraries directly, only the core's clients.
- **The network goes only through the core's client** (decisions, 2026-10-11 "Plugins reach the network only through the
  core's client, to declared hosts"). A connector's web client reaches only the hosts the manifest declares, over HTTPS, with
  redirects checked against the same list and a size cap, and it gets only the secrets the manifest names. The person sees
  where an add-on can reach before turning it on (built, on the Add-ons screen). Built; the "not a sandbox" wording on the Admin
  tab is not, because the Admin tab is not built.
- Running plugins in a separate process with enforced limits is planned (Part 13, after the base); not built.

## 12.4 Privacy and retention

- Not yet built: retention, exporting a person, forgetting a person, and the shorter hosted retention below. Raw source text is
  designed to be kept for as long as `config/storage.yaml` `retention` says (4.15); after that only the facts recorded from
  it and the ledger's note that it existed remain.
- **Export a person** (everything stored about them) and **forget a person** (delete or anonymize per `forget_person`) are
  Admin actions, recorded in the ledger.
- Hosted mode defaults to shorter retention for mail and replies than local mode.

## 12.5 Internet-facing hygiene (hosted)

Dependencies pinned (built: the lock file and exact web versions) and scanned in CI (not built); the container runs as a
non-root user with a read-only file system apart from the workspace volume (not built: there is no container image); uploaded files are stored as data, never executed, and served only as downloads; the UI never renders raw HTML and links from untrusted content show their real domain (7.11);
the database file is never
served.

## 12.6 Sign-ins, add-ons and what they keep

These rules cover the accounts a person signs in to and the code a person adds. They are built unless marked.

- **Sign-in tokens stay on the computer.** An add-on can declare a sign-in to a service (OAuth 2.0 with PKCE through the
  service's own page; plugin API 0.3.33, decisions 2026-10-11). The core takes the answer at the app's own callback route and
  keeps the tokens on this computer, in a private folder readable only by its owner, beside the plugin's other kept secrets. It
  renews them and hands the connector an access token for the call (`context.access_token(name)`); a withdrawn sign-in is
  reported as a sign-in problem, in words. Tokens are never written into config. For the app registration, the workspace's
  references win over the add-on's own, and a hosted app uses them. The operating system's keychain is not yet used.
- **An app registration of the person's own** (pasted on the account row) is kept the same way and can be set aside and brought
  back.
- **Reading does not change.** The core's mailbox source reads without marking anything as read. What an add-on may reach,
  keep and sign in to is what its manifest declares, shown before turning it on.
- **Plugins reach the network only through the core's client, to the hosts the manifest declares** (12.3). The core's own feed
  connector refuses documents that declare their own entities.
- **A release read token is a secret reference.** A private pack's release host takes a read token the person gives once; the
  workspace keeps a secret reference to it, never the value in a settings file. The token goes only to that release's own
  host.
- **Installed packages are checked against checksums.** The one-click install (11.7) downloads the release the catalog entry
  names, compares its SHA-256 with the entry's, and installs nothing on a mismatch. A pack installed this way is off until the
  person turns it on, after seeing what it adds, reaches and keeps (3.11). Phase A2 widens this to a pack's own libraries, each
  with a checksum, with conflicts with the app's own refused and Remove taking out only what the pack needed.
  Installing code is the person's choice, and an installed add-on is trusted code (12.3).
- **A catalog is untrusted text.** A feed is read only when the person looks and carries nothing about them; the maintainers'
  feed address ships with the release build and the repository holds none (3.11). Whether a pack is listed is the owner's
  decision, by a reviewed change to the catalog.

## 12.7 What is not yet built (2026-10-12)

| Item | Where designed | State |
|---|---|---|
| `keychain:NAME` secrets | 12.1 | Refused with a message |
| Audiences and restrictions on destinations | 12.1 | Not built |
| A log of sign-ins and of turning plugins on and off | 12.1 | Not built (the ledger and settings records exist) |
| The scheduled export to git and its remote | 12.1 | Not built; the settings are read by nothing |
| Retention, export a person, forget a person | 12.4 | Not built |
| Outbound review with provenance and full links | 12.2 | Not built until the publisher exists |
| The `lookup` op | 12.2 | Not built |
| Lessons and the glossary (proposed, untrusted until accepted) | 12.2 | Not built |
| Hostile cases for requests to send and to watch new sources | 12.2 | Not built |
| The Admin tab and its "not a sandbox" wording | 12.3 | Not built |
| Dependency scanning in CI | 12.5 | Not built; dependencies are pinned |
| The non-root container with a read-only file system | 12.5 | Not built; no container image |
| Sign-in providers, passkeys, CSRF tokens, lockout, the Security panel | Part 11 | Not built; hosted, after 1.0 |
| Plugins in a separate process with enforced limits | 12.3 | Not built; after the base |
