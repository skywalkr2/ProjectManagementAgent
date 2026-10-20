# How Thimbleby is offered, and how its users steer it

Decided by the owner on 2026-10-20 and revised the same day after the functional designer's review (`docs/decisions.md`,
both entries of that date). This page holds the plan; the roadmap's batches take its items when the main session folds
them in (open promise P25).

## The offer: one free app, one paid upgrade

| | **Thimbleby** (free) | **Thimbleby Plus** (one licence) |
|---|---|---|
| What it is | The core: the daily steward, hand-in, the define-your-own kit and its templates, the person's own AI accounts, everything kept on the person's computer. Mail and calendars from any service: IMAP and calendar links, and **Gmail and Outlook through the person's own app registration**, pasted on the Sign-ins row beside the add-on's numbered steps | Everything in the free app, plus **one-click** Gmail and Outlook sign-in (the add-on's own registration), every pack (writing first, then project management, publishing and the ones that follow) and updates |
| Where it lives | Open source under Apache-2.0, published from the private working repository at each release. The Gmail and Outlook add-on is open source under Apache-2.0 too, in its own public repository, and a free download from the catalog | The packs' private repositories, as today; the add-on's own registration, which only its release build carries |
| Installers | Signed installers, free to download | The same installers; the licence turns on the add-on's own registration and the packs |
| Price | Free | A yearly licence; what a lapse keeps is below. The amount follows from the break-even line below |

**The line is convenience and packs, never whether the app works.** Basic sign-in with a password, app passwords
included, is turned off for Microsoft's personal mail (since September 2024) and for its work mail, so IMAP alone
would leave many people unable to connect at all; Gmail's app passwords are fiddly and can be blocked by an
organization. The pasted registration is awkward but works for both. With nothing connected there is nothing to
suggest, and the loop below stalls.

**For the free Gmail path:** the add-on's steps tell the person to set their registration's status to "In production".
A Google registration left in "Testing" issues sign-ins that expire after seven days, so mail would stop every week.
The steps say that Google's "unverified app" screen is expected for a registration of one's own. Checked in the owner's
live run (below) before the steps ship.

**Not built: a marketplace.** One licence covers every pack, so there is no per-pack price, no per-pack licence and no
store to run. A pack's catalog entry says whether it needs Plus; that is the only difference.

**What a lapsed licence keeps.** Packs keep working at the version installed when the licence ended; updates stop. The
add-on's own registration stops: the Sign-ins row says the one-click sign-in needs Plus and offers the person's own
registration in place, and a Today line says mail isn't being read until they choose. So the owner never carries
Google's yearly costs for people who have stopped paying. Tested both ways (below).

**Why the core and the mail add-on stay open:** an assistant that reads mail is easier to trust when its code can be
read, and companies approve Apache-2.0 (decisions, 2026-10-09). For most people the Gmail and Outlook add-on is the code
that signs in and reads their mail, so it is open as well; nothing paid is given away, since Plus sells the one-click
registration and the packs, not the mail code. The add-on's repository leaves its registration empty and its release
build fills it in, as `catalog/product.yaml` does for the core.

**Accepted, not hardened:** the licence check in the open code can be patched out, and the add-on's own registration
can be lifted from the release build and used without a licence (a registration for an app on a person's computer
can't hold a secret). Someone who does so is covered by the owner's verification and assessment. Both are accepted for
this market and no effort goes into preventing them; if the registration is misused at scale, the owner replaces it in
the next release.

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
   stages and checklists and save them as one template file. A shared template gallery lets people build for their own
   kind of work and share it, and the templates people build most are the next packs. This is how "a base for almost
   anything" reaches people who don't write code.
   **A gallery template is untrusted content**, like outside mail: its stage descriptions, checklists and help text
   reach the assistant's packets, so a template can carry instructions. It is marked by origin, shown in full before it
   is added, enters packets marked "from outside", and is never followed as an instruction or turned into a rule,
   recipient or source. A test adds a template whose help text tries to change routing, and checks that nothing
   changes.
4. **One ideas board on the website**, fed by *Suggest something* and by a form on the website, so nobody needs a code
   host account. People can see and back each other's suggestions there.
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

## The price, from the numbers

Set once M1 says what Google's assessment costs. The fixed yearly costs divided by what each licence brings in give
the paying users needed to break even:

> paying users to break even = fixed yearly costs ÷ (price × (1 − the payment service's share) − its fee per sale)

| Fixed yearly cost | Assumed until known |
|---|---|
| Google's security assessment (CASA), yearly | $1,000 to $5,000: a placeholder until M1 brings a quote; it is the largest unknown |
| Apple developer programme and Windows signing | about $219 (decisions, 2026-10-17) |
| The website and its domain | about $100 |
| **Total** | **$1,319 to $5,319** |

At a price of **$75 a year**, with the payment service taking about 5% plus $0.50 a sale, each licence brings in
$70.75: $1,319 ÷ $70.75 ≈ 18.6 and $5,319 ÷ $70.75 ≈ 75.2, rounded up because a part of a user doesn't pay, so
**break-even is 19 to 76 paying users**. The page records the real number here once M1 is answered,
beside the price chosen.

## The path to a paid 1.0

### Owner actions (the critical path; most aren't code)

| # | Action | Why it comes when it does |
|---|---|---|
| M0 | **Before anything is sold:** read the intellectual-property and outside-business clauses of every employment or contractor agreement in force, or have a short consult. Risk R9 is reopened until it is done. | R9 was closed for a personal project where only ideas cross; selling it is a different question, and many agreements' clauses apply once something is sold. |
| M1 | Ask Google two things, and plan on the yearly assessment (CASA) rather than an exemption: (1) whether a local app that sends mail content to the person's own AI account is in scope of the assessment (Google's exemption was for apps that keep data only on the person's device, and this one sends it to an AI service of the person's choosing, which likely counts as a transfer to a third party); (2) what its Workspace user-data policy requires for AI processing (disclosure, and no use of the data to train models). Get an assessor's quote. | The longest lead time, and the yearly cost sets the price. Until it is done, everyone uses the pasted registration. |
| M2 | Microsoft publisher verification for the Outlook add-on's registration. | Lighter than Google, but needs the website and a privacy policy. |
| M3 | Signing: Apple's developer programme and Windows signing (about $219 a year, decisions 2026-10-17). | "Unsigned to start" is fine for testers, not for paying customers. |
| M4 | Pick a payment service that is the merchant of record (for example Paddle, Lemon Squeezy or Polar): it takes payment, handles sales tax and VAT, refunds and receipts, and issues the licences. | The app never handles payment (decisions, 2026-10-11); this keeps tax and billing off the owner's desk. |
| M5 | Make the working repository private; publish the open core from it at each release as a fresh public repository (the roadmap's "Publish 1.0" already plans one starting commit). Everything already published, `docs/project/` included, is assumed copied: going private hides plans from then on, not the past. Before the first public core is cut, a session lists what in `docs/project/` and the design is the owner's own business rather than the product's, and the owner decides what the public core carries. The mail add-on's repository goes public the same way: a fresh snapshot, checked first, with its registration left to the release build. | Plans and test runs shouldn't keep being published; what was published stays out there. |
| M6 | The website (open promise P24): pricing, privacy policy, terms, the ideas board and its form. | Google and Microsoft both ask for the privacy policy; the board lives there. |

### Built in the product

Fits after phase S, beside phase I (installers). Each item gets its batch tag when the roadmap takes it.

- **Plus licence, checked offline.** A licence file signed by the owner's key, pasted or opened on a screen, kept in
  the workspace's private folder and checked with the public key the app ships with. No call home. Generic in the
  core: a catalog entry, a plugin manifest or a sign-in's own registration can say it needs an entitlement (`plus`),
  and the core checks a signed entitlement without knowing what it unlocks.
- **The add-on's own registration needs the entitlement.** The core uses a sign-in's shipped registration only while
  the entitlement it names is held; otherwise the Sign-ins row offers the person's own registration with the add-on's
  steps, and says one-click sign-in comes with Plus. A lapse is handled as above.
- **Downloads gated by the licence.** Today a private pack's release host takes a read token (P15), which can't be
  handed to customers. A small download address checks the licence and returns a short-lived link to the release
  file; the Add-ons screen's Install sends the licence instead of a token. Free add-ons (the Gmail and Outlook add-on)
  download with no licence.
- **Suggest something** (the loop above, items 1 and 2), replacing the separate feedback button.
- **The template gallery** (item 3), with templates handled as untrusted content. After the paid 1.0 if time is short;
  the loop works without it.
- **Repository files** for the public core: CONTRIBUTING (ideas welcome, no pull requests), SECURITY (how to report a
  problem privately), and a trademark note (Apache-2.0 doesn't license the name, so a changed copy can't be called
  Thimbleby).

**Tests that come with them:**
- a journey test: a free install connects an Outlook.com mailbox through a pasted registration, on the fake sign-in
  service the tests use; and the owner's live check of the same on a real Outlook.com and a real Gmail account
  (registration "In production"), which confirms the add-on's steps;
- a lapsed licence: packs keep working at their version; the one-click sign-in stops, with the Sign-ins row's offer
  and the Today line; a renewed licence brings it back;
- a gallery template whose help text tries to change routing changes nothing, and reaches packets marked "from
  outside".

### First audience

Freelancers, consultants and small-business owners. They own their mailboxes, which avoids the employer-mail problem
(risk R14), they juggle many people's promises, and they pay for tools. "Anyone juggling work" stays the direction.

## Open for the owner

- The yearly price, once M1 gives the assessment's cost (the break-even line above).
- Which payment service (M4).
- How the ideas board is run on the website (a hosted board or a simple list the owner keeps).
