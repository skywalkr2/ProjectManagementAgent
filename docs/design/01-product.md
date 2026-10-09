# Part 1. The product

## 1.1 The idea

Someone running several projects (a program manager supporting a leader, an author with books in progress, a person with side
projects) spends much of the day noticing what changed, updating the places other people read, chasing people for answers and
keeping follow-ups straight. The information is spread across sources: pages, trackers, folders, mailboxes, feeds, meetings and
chats.

The cockpit does the noticing and the drafting. It watches the sources, has an AI assistant turn each change into proposed
updates, questions and action items, and gives the PM one screen to review, correct and send out.

**The AI drafts. The human approves everything that goes out.**

## 1.2 Who it's for

- **The PM (primary user):** reviews, approves, sends, publishes. Wants one screen that says what to do today.
- **Readers:** people who read what the PM publishes (a leader reading status pages, subscribers reading a newsletter). They
  shouldn't have to confirm routine updates.
- **Contacts:** people who receive questions and action items. They never use the tool; they get paste-ready messages, or
  messages sent through a channel after the PM approves them.
- **The assistant:** an AI with a configurable display name (e.g. "Archie"). The underlying model's name never appears in
  anything a person sees.

## 1.3 The core loop

1. **Watch** sources on a schedule through connectors, plus anything the PM hands in (pasted notes, emails, screenshots, files).
2. **Triage by rules first:** configurable rules close cosmetic edits, items outside the portfolio, repeats and other known
   no-op cases before the AI sees them. Every auto-closed item stays findable with its reason and can be pulled back.
3. **Package and dispatch:** remaining items are batched into packets (the change, the related records, the open actions and
   questions, the rules) and handed to the AI provider layer.
4. **The AI writes a changeset:** a structured file of typed ops. It never edits records, pages or files directly.
5. **Check and apply:** a deterministic applier checks the changeset (hard invariants, then softer lints), resolves names to
   ids, and applies it in one transaction, recording every field it changed in a ledger so any of it can be undone. Ops that
   would change the product's own behavior never apply automatically from an input. Invalid changesets go back to the AI once with the reasons before any human sees them.
6. **Review:** the PM sees each change with the AI's work nested under it and one set of buttons: Looks good, Send back, Undo.
7. **Send out:** records render into drafts for channels (a page, a message, a post). Each draft waits with a readable diff or
   preview. Nothing leaves the cockpit until the PM approves that exact content.
8. **Follow up:** questions and action items grouped by person, copied or sent as one clean message, marked sent, aged until
   answered. A pasted reply goes back to the AI, which records it and acts on it.

Every step is generic. What gets watched, what records exist, what gets drafted and where it goes are supplied by plugins and
configuration.

## 1.4 What's core and what's a plugin

| Core (always present, generic) | Extensions (plugins) |
|---|---|
| The loop: watch, triage, dispatch, apply, review, send out, follow up | Where inputs come from: wikis, trackers, mailboxes, feeds, accounts (connectors) |
| Records, changesets, the applier, undo, history | Where outputs go: pages, email, blogs, social posts (channels) |
| Questions, actions, meetings, people and ids, the ledger and undo | Kinds of things to track and extra fields on core records (record types) |
| The AI provider layer: routing, fallbacks, budgets, evaluation | Domain ops, triage matchers, AI task kinds and their prompts |
| The approval gate, diffs, the publisher | Templates and renderers for pages, posts and messages |
| Scheduler, governor, automation problems and reports | UI panels, Today lines, scheduled jobs, lookups, event handlers |
| UI shell and core panels | Vendor adapters for AI models and for outside services |
| Plugin host, config schemas, self-check | Packs: bundles of the above for one kind of work |

So the whole product runs offline on demo data, the core ships with minimal built-ins: a fake connector and fake channel backed by
fixture files, a local-folder connector, paste-in and upload, a clipboard channel (copy a message to paste anywhere) and a stub AI
adapter.

## 1.5 An assistant, not a methodology

The cockpit assists the person running projects; it doesn't replace their judgment or impose a methodology. It knows good
practice and applies it where it helps: in the core, how to support projects well (clear follow-ups, questions written for
their reader, risks and dependencies kept current, slips caught early); in each pack, how its kind of work is done well. That
knowledge lives in **playbooks** (3.8), which the PM can switch off entry by entry or override with their own rules.

Anything a playbook doesn't build in, the PM can still ask for: "what's on the critical path?", "draft a risk review for the
launch". The assistant answers from the records with the same playbooks in hand (6.25). Built-in features are for what
happens every day; everything else is a question away.

## 1.6 Not goals for the base

- **Autonomous sending.** Nothing goes out without the PM approving the exact content. A scheduled post is approved content
  that the PM scheduled; the cockpit never decides on its own to send.
- **Changing its own code.** The product never writes or applies code changes to itself. A problem the automation can't solve,
  or a request no op can do, becomes a report the PM approves and sends to the maintainers (6.13). Developing the product is
  done in its repository, with whatever tools the developer chooses, outside any installation.
- **Multi-tenant hosting.** One deployment serves one workspace. It runs on the PM's own machine or on a web host the PM
  controls (Part 11), never as a shared service holding several customers' data. Storage sits behind a repository layer so a
  multi-user build can come later without rewriting the engine.
- **Real-time collaborative editing.** One writer at a time per workspace.
