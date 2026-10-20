# How Thimbleby is offered, and how its users steer it

Decided by the owner on 2026-10-20 (`docs/decisions.md`, same date). This page holds the plan; the roadmap's batches
take its items when the main session folds them in (open promise P25).

## The offer: one free app, one paid upgrade

| | **Thimbleby** (free) | **Thimbleby Plus** (one licence) |
|---|---|---|
| What it is | The core: the daily steward, hand-in, any mailbox over IMAP, calendar links and files, the define-your-own kit and its templates, the person's own AI accounts, everything kept on the person's computer | Everything in the free app, plus one-click Gmail and Outlook sign-in, every pack (writing first, then project management, publishing and the ones that follow) and updates |
| Where it lives | Open source under Apache-2.0, published from the private working repository at each release | Private repositories, as the add-ons are today |
| Installers | Signed installers, free to download | The same installers; the licence turns the Plus add-ons on |
| Price | Free | A yearly licence; the person keeps the version they have if they stop paying. The amount is open (below) |

**Not built: a marketplace.** One licence covers every pack, so there is no per-pack price, no per-pack licence and no
store to run. A pack's catalog entry says whether it needs Plus; that is the only difference.

**Why this line:** most people need Gmail or Outlook, the free app still works without them (IMAP and calendar links),
and the services' own sign-in is what costs the owner money and paperwork (Google's verification, below). The core
stays open because an assistant that reads mail is easier to trust when its code can be read, and because companies
approve Apache-2.0 (decisions, 2026-10-09).

## Users steer what is built

The point of the free app is people using it and saying what they want next. The product already has the parts; they
become one loop.

1. **Ask from inside the app.** *Send feedback* (Help menu) and the assistant's `report.draft` (a request no op can do
   becomes a report for the makers, design 6.13) become one flow: *Suggest something*. The person sees and approves the
   exact text before it goes, as for everything outward. It carries the version, free or Plus, and which packs are on;
   never names, addresses or message content.
2. **The assistant notices the gaps.** When Ask or a correction hits something no op or pack can do, the assistant
   offers "Suggest this to the makers" with the draft ready. A count of these by kind is a better signal than a survey.
3. **Templates are the extension people touch.** The define-your-own kit already lets a person make item types,
   stages and checklists and save them as one template file. A shared template gallery (data, not code, so nothing to
   review for safety) lets people build for their own kind of work and share it. The templates people build most are
   the next packs. This is how "a base for almost anything" reaches people who don't write code.
4. **One public ideas board** on the open core repository (discussions with votes), so suggestions are seen and
   people can back each other's.
5. **Close the loop.** Each release's notes have a "You asked for" section, and the suggestion that led to a change is
   answered "shipped" with the version. People keep suggesting when they see suggestions land.
6. **Founding members.** The first Plus buyers (the testers first) get a price held for as long as they keep the
   licence, in return for the two-week check-in form (`tester-feedback-form.md`) and one short check-in a month.
7. **The owner's time stays small.** A weekly triage of about an hour: a session gathers the week's suggestions,
   groups them, and drafts the decision entries; the owner says yes, no or later.

**Contributions:** ideas, problem reports and templates are welcome; code pull requests are not accepted. That keeps
the paid edition's code the owner's own and the upkeep low. If that changes, a contributor agreement comes first.

## A base for almost anything, in stages

The core stays generic, as it is built: that is what makes every pack possible. Opening it to outside builders is
staged so the owner isn't supporting a public API before it has settled.

1. **Now to the paid 1.0:** packs are built by the owner's own sessions and invited builders, on plugin API 0.x.
   Product 1.0 does not wait for plugin API 1.0, and does not wait for every pack to be designed.
2. **Plugin API 1.0:** frozen once the writing pack and the project management pack run on it unchanged through a
   week of real use (the roadmap's existing test). Its generated guide (`docs/plugin-guide.md`) is the public contract.
3. **Then outside builders:** the catalog lists packs from other builders, marked as theirs, free or sold by them.
   Whether Thimbleby takes a share is decided then.

## The path to a paid 1.0

### Owner actions (the critical path; most aren't code)

| # | Action | Why it is first |
|---|---|---|
| M1 | Ask Google how the add-on's own Gmail sign-in is verified for an app that keeps mail on the person's computer but sends it to the person's chosen AI service. Restricted Gmail scopes need verification and may need a yearly paid security assessment (CASA); whether a local app is exempt isn't clear from Google's pages. | The longest lead time, and it may carry a yearly cost that sets the price. Until it is settled, Plus uses the "paste your own app registration" path already built. |
| M2 | Microsoft publisher verification for the Outlook add-on's registration. | Lighter than Google, but needs the website and a privacy policy. |
| M3 | Signing: Apple's developer programme and Windows signing (about $219 a year, decisions 2026-10-17). | "Unsigned to start" is fine for testers, not for paying customers. |
| M4 | Pick a payment service that is the merchant of record (for example Paddle, Lemon Squeezy or Polar): it takes payment, handles sales tax and VAT, refunds and receipts, and issues the licences. | The app never handles payment (decisions, 2026-10-11); this keeps tax and billing off the owner's desk. |
| M5 | Make the working repository private; publish the open core from it at each release as a fresh public repository (the roadmap's "Publish 1.0" already plans one starting commit). | `docs/project/` is public today and holds the owner's own plans, risks and test runs. |
| M6 | The website (open promise P24): pricing, privacy policy, terms, the ideas board's link. | Google and Microsoft both ask for the privacy policy. |

### Built in the product

Fits after phase S, beside phase I (installers). Each item gets its batch tag when the roadmap takes it.

- **Plus licence, checked offline.** A licence file signed by the owner's key, pasted or opened on a screen, kept in
  the workspace's private folder and checked with the public key the app ships with. No call home. Generic in the
  core: a catalog entry or a plugin manifest can say it needs an entitlement (`plus`), and the core checks a signed
  entitlement without knowing what it unlocks.
- **Downloads gated by the licence.** Today a private pack's release host takes a read token (P15), which can't be
  handed to customers. A small download address checks the licence and returns a short-lived link to the release
  file; the Add-ons screen's Install sends the licence instead of a token.
- **Suggest something** (the loop above, items 1 and 2), replacing the separate feedback button.
- **The template gallery** (item 3): share a template from Settings, browse and add one from the gallery. After the
  paid 1.0 if time is short; the loop works without it.
- **Repository files** for the public core: CONTRIBUTING (ideas welcome, no pull requests), SECURITY (how to report a
  problem privately), and a trademark note (Apache-2.0 doesn't license the name, so a changed copy can't be called
  Thimbleby).

### First audience

Freelancers, consultants and small-business owners. They own their mailboxes, which avoids the employer-mail problem
(risk R14), they juggle many people's promises, and they pay for tools. "Anyone juggling work" stays the direction.

## Open for the owner

- The yearly price, once M1 says what Google's verification costs. A starting guess: $50 to $100 a year, kept modest
  because people pay their own AI costs.
- Which payment service (M4).
- Whether the ideas board is on the code host or on the website.
