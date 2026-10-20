# Proposed change to the business model: Plus launches without Gmail's one-click sign-in

For the functional designer's review (2026-10-20). A delta against `docs/project/business-model.md` as of commit
`5d8aa39`. Nothing here is decided: once reviewed, the accepted parts go into that page, `docs/decisions.md` and the
design, as before.

## The problem

Google's security assessment (CASA, yearly, placeholder $1,000 to $5,000) is the price of shipping Gmail's one-click
sign-in. It is the plan's largest cost and its longest lead time, and it sits in front of the first sale. Early rollout
can't wait on it or pay for it before there are users.

## The proposal

**Plus launches with every pack, one-click Outlook and updates. Gmail's one-click sign-in comes later, when the numbers
support it.**

- Microsoft's publisher verification has no paid yearly assessment like Google's, so one-click Outlook stays at launch.
- Existing Plus licences get Gmail's one-click sign-in at no extra cost when it ships (a "You asked for" release).

## What changes in `business-model.md`

### The offer table

| | Free | Plus at launch | Plus once Gmail one-click ships |
|---|---|---|---|
| Outlook | Own pasted registration | **One-click** | One-click |
| Gmail | Own pasted registration | Own pasted registration (or the tester registration, below) | **One-click** |
| Packs and updates | None | All | All |

### M1 splits in two

- **M1a, now (free):** ask Google the two questions (whether a local app sending mail to the person's own AI account is
  in scope, and what its user-data policy requires for AI processing), and get an assessor's quote. The real cost is
  then known.
- **M1b, at the trigger:** run the assessment and ship the add-on's Gmail registration.
- **The trigger:** whichever comes first:
  - Plus revenue covers a year of the assessment;
  - the tester registration (below) nears its user cap with people still asking for Gmail;
  - the Gmail drop-out count (below) shows the pasted path is losing people the assessment would keep.

### A new owner action: the tester registration

- **M7:** the owner makes a Google app registration of their own and leaves it in **Testing** status, for testers and
  founding members.
  - Google lets a registration in Testing serve a list of named test users (about 100) with no verification or
    assessment. The early rollout is under that number.
  - Each person is added by their address.
  - Their sign-in expires after seven days. The app already shows "Sign in again" at once when a renewal is refused,
    so this is a weekly nuisance, not a failure. The tester invitation says so.
  - The exact user cap and expiry are checked against Google's pages when M7 is done.
- **How it reaches them:** the add-on reads a tester registration from the person's own pasted values, so no build
  change is needed. The invitation gives the values and the steps.

### The break-even line, in two stages

| Stage | Fixed yearly costs | Break-even at $75 (each licence brings in $70.75) |
|---|---|---|
| Launch, without Google | about $319 (signing $219, website $100) | $319 ÷ $70.75 ≈ 4.5, so **5 paying users** |
| Once Gmail one-click ships | $1,319 to $5,319 (as now) | **19 to 76 paying users** (as now) |

### The free Gmail path needs the best walkthrough in the app

Until Gmail one-click ships, everyone outside the tester list connects Gmail through their own registration. Making
one in Google's developer console is hard for someone non-technical.

- The add-on's Gmail steps are written and tested as a walkthrough, with a screenshot per step and the "In production"
  step called out.
- A count of people who start the Gmail steps and don't finish feeds the trigger above. It is a count only, kept on the
  person's computer, and sent only inside a *Suggest something* report the person approves.
- **Gmail app passwords are not counted on as a fallback.** Google ended password sign-in for Workspace accounts in May
  2025. Whether app passwords still work for personal Gmail couldn't be confirmed, and one source suggests they are
  being phased out. If the owner's live check finds they still work, the Gmail steps can offer them second, as one
  more way in.

### What carries over unchanged, applied to Outlook first

- What a lapsed licence keeps: the rules apply to Outlook's one-click sign-in at launch, and to Gmail's once it ships.
- The registration can be lifted, and that is accepted: the same.
- Open promise P26: the add-on's registrations move to its release build; at launch that is Outlook's only.

### Tests added

- A tester registration pasted on the Sign-ins row signs in. A refused renewal after a week shows "Sign in again" at
  once, and signing in again resumes reading with nothing lost. This runs on the fake sign-in service the tests use.
- The Gmail drop-out count goes up only for a person who started the steps, and never leaves the computer except
  inside an approved report.

## Questions for the reviewer

1. Is the trigger right, or should Gmail one-click wait on one signal only?
2. Is a weekly "Sign in again" acceptable for testers, or does it spoil the two-week check-in (`tester-feedback-form.md`)?
3. Should the free Gmail walkthrough be in the core's setup guide or only in the add-on?
