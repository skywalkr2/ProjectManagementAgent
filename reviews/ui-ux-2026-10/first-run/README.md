# First run and Settings, for someone with no IT background

**Reviewed:** branch `claude/tender-tesla-16a8ob` at `dda256d`.
**How:**
- I made a brand-new empty workspace with `cockpit init`, not the pre-filled demo, and opened it with `cockpit serve`.
  Then I walked the setup guide and every Settings section the way a first-time user would.
- I read `docs/install.md` and `docs/getting-started.md` as that person.
- I scanned the 1,001 setup and Settings strings in the wording sheet for technical terms.

**Files:**
- `screens/`: the current build.
- `mockup-first-run.html` and `mock-*.png`: the proposal for the three hardest steps.

**The person:** Jordan runs projects for a small team. They use email, a calendar, spreadsheets and a cloud drive every
day. They have never opened a terminal, don't know what an API key, IMAP or a time-zone id is, and will give up if a
step needs them to ask IT.

## Verdict

**Jordan can't get through setup alone today.** They'd stop at one of four walls, and the first comes before the app
even opens:

| Step | Could Jordan do it alone? | Why |
|---|---|---|
| Install | **No** | A terminal, a separate Python tool (`uv`), and on Windows `-ExecutionPolicy Bypass` |
| You | Yes | Clear. The time zone list is raw ids (below) |
| Your AI account | **No** | 12 services, no recommendation, a one-link "get a key", and a default that blocks their own material |
| Mail and calendar | **No** | On a fresh install it lists nothing. The only path is a raw IMAP form with "secret reference (env:NAME or file:/path)" |
| Your promises | — | Needs AI and mail first |
| Backups | Mostly | A blank path box; the chooser shows raw system paths and no cloud-drive folders |
| People | Yes | — |
| Done | Confusing | Broken layout. "Templates for your items, stages and Today page" means nothing to them |
| Settings | Partly | The basic sections are fine. Time zone, writing variety, notices and Advanced speak IT |

The look of the screens is good now. What fails is the **vocabulary and the assumptions**: the setup is written for the
person who built it. The fixes are mostly words, defaults and a few guided paths, not new features.

---

## Findings

### F1 [P0] Install needs a terminal

**Seen:** `docs/install.md` and `getting-started.md` say:
- install `uv` "from its documentation"
- run `sh install.sh …` or `powershell -ExecutionPolicy Bypass -File install.ps1 …`
- then type `cockpit`
- and "leave the terminal window open while you work: closing it stops the app"

When an add-on needs a restart that fails, the fix is "close the terminal's program with Ctrl+C and run the same
`cockpit serve` command again".

**Do:**
- **M0 (the one-click installer) must land before any non-technical person uses this,** not after launch. The roadmap
  has it first in version 1. For this person it's the front door.
- The installer should leave a normal app that starts from the dock or Start menu, sits in the menu bar or tray while
  running, restarts itself, and updates itself.
- No instruction anywhere on the person's path mentions a terminal.

### F2 [P0] The AI account step assumes you know the AI market

**Seen** (`screens/02-ai-account.png`, `03-…`, `04-…`):
- **Twelve services, no recommendation.** The descriptions assume knowledge: "Fast answers from open models", "Low
  prices; check where it keeps what you send", "in its read-only sandbox", "it asks before using tools, so here it
  can't use them".
- **"Use an app you're signed in to"** lists command-line tools (Claude Code, Copilot CLI, Codex CLI, Gemini CLI). Each
  needs a terminal install. To Jordan, "I pay for ChatGPT" sounds like the right choice, and it leads to a CLI they
  can't install.
- **"Get an access key"** is one link to a developer site. Nothing explains that they need to:
  1. make an account
  2. **add credit** (a key with no credit fails)
  3. copy the key, which is shown only once
- **"What it may see"** has only "Open material" ticked by default. The small print says "Your notes, mail and meetings
  are internal, so the assistant can work on them only once Internal is ticked." So **with the defaults, the
  assistant can't work on Jordan's own material.** The getting-started guide has to say "tick Internal". That is a trap
  in the defaults.
- **The model picker shows a raw model id** ("sonnet").
- **Four separate commit buttons in one step:** Check, Add account, Save (spending), then Back or "Skip for now". The
  order isn't explained.
- **The bad-key message** for a hosted service: "The service couldn't be reached. Check the address, or start it if it
  runs on this computer." There is no address to check and nothing to start. That advice is for a local service.
- **Spending** is typed as "0.1" in a field labelled "(USD)".

**Do** (`mock-ai.png`):
- **One recommended choice** (with a "Recommended" tag), plus one alternative and "Something else" for the rest. The
  recommendation comes from the catalog and the capability measurements, never from code, so the boundary holds.
  CLIs, local models and custom services live under "Something else", with a note that they need a technical setup.
- **Four numbered steps,** each with a button to the right page: make an account, add credit (with what it typically
  costs, from the app's own estimates), make a key and copy it ("shown only once"), paste it.
- **Check on paste.** No separate Check button. Show "✓ Works" or a specific reason: key not accepted, no credit, or
  can't reach the service (check your internet).
- **Ask about data in plain words, with the default matching the purpose:** "Can the AI service read your work mail and
  notes? · Yes, that's what it's for / Only things that could be public". Keep the three levels in Advanced, for
  people who need them.
- **Model:** choose it automatically for each kind of work. Show "Recommended" and hide the id. The picker moves to
  Advanced.
- **Spending as a sentence:** "It asks you before anything over **$0.10**, and stops for the day at **$2** · Change".
- **One Continue** that saves everything. "I'll do this later" is secondary.

### F3 [P0] Mail and calendar: a dead end on a fresh install

**Seen** (`screens/05-mail-dead-end.png`, `06-add-mailbox-imap.png`):
- **The step says** "No services listed. Connect a mail folder or private calendar address below. Connect another service
  using a mail server folder or a private calendar address." It repeats itself, and nothing is "below".
- **The only path is "Another mail or calendar",** a raw IMAP form:
  - "The mail server's address (its IMAP host)"
  - "Its IMAP port with TLS" (993)
  - "A secret reference (env:NAME or file:/path) to the password or app password"
  - "How long to wait for the server" (no unit)
  - "Default: (empty)" under the fields
- **The calendar option** is "its private address".
- **Gmail and Outlook need an add-on,** installed and turned on, then a restart, then a sign-in. The guide warns that the
  sign-in may show "a warning page for this app" (Google's unverified-app screen), which looks like a security alert
  to Jordan.
- **The `env:NAME or file:/path` label comes from a config schema,** not from the wording sheet. So the C44 wording test
  ("no secret reference on the default path") doesn't see it.

**Do** (`mock-mail.png`):
- **Ship the common mail and calendar connectors with the installer.** Show tiles: Gmail and Google Calendar, Outlook
  and Microsoft 365, iCloud, Other email. No add-on screen and no restart on the person's path.
- **"Other email":** type the address, and the app fills the server from known providers. App passwords get a short
  how-to per provider.
- **Server, port, timeout and secret settings** move under "Advanced", in plain words ("Server name", "Port").
- **The unverified-app warning** gets an explanation right where it appears: what it means, how to continue, and how to
  remove access later.
- **The calendar's "private address"** gets per-provider instructions to find it, or is replaced by the sign-in tiles.
- **Extend the C44 wording check** to labels generated from config schemas and add-on manifests, not just the wording
  sheet.

### F4 [P1] Backups: offer the folders people already have

**Seen** (`screens/07-backups.png`, `08-folder-chooser.png`):
- A blank "Folder" box with Check and Choose….
- The chooser shows "You are in /Users/…/…" (a raw path), lists the folders in the home folder, and has "Go up one
  folder".
- It doesn't suggest cloud-drive folders.

**Do** (`mock-backup.png`):
- **Look for iCloud Drive, OneDrive, Dropbox and Google Drive folders** and offer them by name, with "Recommended" on
  the first one found. The path shows as "Backups › PM Cockpit".
- **Say why in one sentence:** "If this computer is lost or breaks, your work is still there."
- **"Back up now and continue"** as one button, so the "Backup needed" warning clears during setup.

### F5 [P1] The Done step: broken layout and builder's words

**Seen** (`screens/09-done-layout.png`):
- The step cards are about 330px tall and mostly empty.
- The template cards are squeezed into a narrow column, so words wrap one per line ("Details: / Title, / Client, /
  Contact").
- "Turn on your add-ons" says **Done** although nothing was turned on.
- "Choose a template for your items, stages and Today page… A restart may be needed".

**Do:**
- A compact summary list (step · done or skipped · Set up).
- Templates in plain words ("What kind of work is this? Client requests / A content calendar / Start empty"), each
  with one line on what it changes.
- Never say Done for a step the person didn't do.
- Never mention restarts. The app handles them.

### F6 [P1] Today's first screen says the wrong thing to a new person

**Seen** (`screens/10-today-first.png`): "Nothing needs you right now. Did your assistant miss something? · Missed one".
Jordan hasn't handed anything in yet, and has no AI account.

**Do:** Today's empty state should depend on setup:
- **No AI account:** "Connect an AI service to get started · [Continue setup]".
- **AI connected, nothing in yet:** "Paste an email or meeting notes to see what your assistant does · [Hand something
  in]".
- "Missed one" only appears after the assistant has worked on something.

### F7 [P1] Settings vocabulary

| Where | Now | Suggested |
|---|---|---|
| You → time zone | A raw list: "Africa/Abidjan, Africa/Accra…" (in setup too) | A searchable picker by city: "New York (Eastern time)" |
| You → writing | "Writing preferences: en-AU, en-CA, en-GB…" | "English spelling: American / British / Australian / Canadian…" |
| AI spending | "Maximum cost per AI task (USD)", "Ask for a go before a run…", "runs" | "Most one piece of work may cost: $0.25". "Ask me before starting anything over $0.10". "Work" instead of "run"; "Ask me" instead of "a go" |
| AI spending | "Ask before starting AI work with an unknown cost… (an account with no prices, such as a subscription)" | Move to Advanced |
| Today → notices | "A chat app or a push topic. Give the address that service made for incoming messages." | "Send to my phone" with per-app instructions (a guided step), or move it to Advanced |
| Today → notices | The checkbox label repeats the description: "Turn on “Tell me when something needs me. A notice goes out only for…”" | "Turn on notices" |
| Advanced topics | "App connection", "Dispatch knowledge", "Checks tuning", "Language reported speech", "Watch", "Prepare incoming material" | Plain topic names ("How mail is read", "What the assistant is told", "Checks on its work"), or keep Advanced clearly labelled "for the person who set this up" |
| AI account, model | "AI model: sonnet" | "Recommended model" (in Advanced) |
| Wording sheet, overall | "model" in 49 strings, "key" in 48, "environment variable", "tokens", "command-line instructions", "pass mark" | Keep the words where they are needed (a key is a key), but explain them once, in plain words ("A key is like a password for the app"), and keep tokens, environment variables and the command line off the person's path |

### F8 [P2] Smaller things

- **"About 10 minutes"** under the walkthrough title. Mail sign-in and getting an AI key can take longer the first time.
  Say "About 10–20 minutes. You can stop and come back."
- **The setup guide's primary** is "Save and continue" on You, but there's no Continue on the AI step (see F2).
  Use the same primary on every step.
- **"Skip for now"** is an underlined link at the far right. Make it a secondary button beside Continue: "I'll do this
  later".
- **"Let the assistant sort what the rules can't"** (mail step) means nothing yet. Say "Set aside newsletters and
  personal mail automatically".

---

## Acceptance for "a non-technical person can set it up"

Add these as the bar for first run, beside C1–C53:
- [ ] N1. A person who has never used a terminal installs and opens the app from a downloaded file. (F1)
- [ ] N2. On a fresh install, Gmail or Microsoft 365 connects with a sign-in, without an add-on screen, a restart or a
  server setting. (F3)
- [ ] N3. With the default choices on the AI step, the assistant can work on the person's own mail and notes. (F2)
- [ ] N4. The AI step has one recommended service, numbered steps that cover account, credit and key, a check on paste
  with specific error reasons, and one Continue. (F2)
- [ ] N5. No string on the setup path (wording sheet, schema label or add-on manifest) contains an IANA id, a locale
  tag, `env:`, `file:/`, IMAP, port, TLS, token, CLI or "command". A test enforces it. (F3, F7)
- [ ] N6. Backups offer the cloud-drive folders found on the computer, by name. (F4)
- [ ] N7. Today's first screen says what to do next for each setup state. (F6)
- [ ] N8. **A real test:** three people who match the persona each complete setup alone, with the task "set it up and
  see what it does with one of your emails", while someone watches without helping. Each finishes in under 20 minutes.
  Every place one of them stops or asks a question becomes a finding. The "friends' preview" on the roadmap is the
  natural place for this.
