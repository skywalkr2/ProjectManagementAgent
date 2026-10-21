# O3: Research memo on mail sign-in rules at Google and Microsoft

**Why:** the free app connects Gmail and Outlook through a registration the person makes themselves; a paid upgrade may
later offer one-click sign-in. Several plans depend on facts about the services' current rules
(`docs/project/business-model-delta-gmail-later.md`, questions F26 to F29 in `docs/project/designer-questions.md`).

**Answer each question with sources:** for every claim, the page's address, the exact sentence it rests on, and the
date you read it. Where sources disagree or nothing official says, write "not confirmed" and why.

Google:
1. A registration in "Testing" status: how many test users, and does removing a user free a place (is the cap counted
   over the registration's whole life)?
2. Do sign-ins for a registration in Testing still expire after seven days? Any exception for the scopes a mail reader
   needs?
3. What a registration needs to move to "In production" for the restricted Gmail read scope, when only the person who
   made it uses it (their own registration, not shared): is verification needed, and what does the person see?
4. The yearly security assessment for restricted scopes: who must do it, what it costs (published ranges), and whether a
   desktop app that keeps data on the person's computer but sends mail text to an AI service the person chose is in
   scope.
5. App passwords for personal Gmail accounts today: still offered, being phased out, or gone? For Workspace accounts?

Microsoft:
6. Can a personal Outlook.com account still read mail over IMAP with a password or app password, or only with modern
   sign-in?
7. Publisher verification: what it requires, what it costs, and what the person sees without it.
8. For a registration the person makes themselves in their own tenant or personal account, what consent screens appear
   for mail and calendar read access?

**Produce:** `docs/project/research/mail-signin-2026-10.md`: a short answer per question, then its sources, then
"not confirmed" items. No speculation presented as fact.

**How it is checked:** the main session opens each source and checks the quoted sentence is there. The owner's live
check (roadmap I-3) confirms the steps before they ship.
