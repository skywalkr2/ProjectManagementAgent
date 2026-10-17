# Screen wording review (2026-10-17)

An outside assistant reviewed every entry of `web/src/wording/en.json` (2,308 entries, about 700 proposals in the
table below). This file keeps the review and the main session's triage. Phase B wave 3 applies it (roadmap), with the
browser tests updated in the same change; nothing here is applied yet.

## Triage

**Apply (the default for a row not named below):**
- Shorter rewrites that keep the meaning ("Shorter").
- One name per thing on screen: "to-do" for an action the person or someone else does, "calendar event" for a calendar
  entry, "Add-ons" for plugins, "AI service" where the text means the vendor's service rather than the person's account.
  This is also the start of phase S5's audit for project-manager wording.
- Abbreviations spelled out ("{n}d" becomes "{n} days", "{n} h ago" becomes "{n} hours ago").
- Internal terms in plain words where the proposal keeps the meaning ("outside content" becomes "someone else's
  material", "routing entry", "retired").
- Action-first labels on buttons and links ("Open AI accounts", "Show keyboard shortcuts").

**The zero counts (110 rows marked "Zero count (conditional)"):** not a wording change. Each key's callers are checked
so that a count of zero never renders: the section is hidden or its empty state shows (open promise P19, item 3, and
the rule that no line counts zero things). A test covers each screen that shows such a count.

**Rejected:**
- "Go" / "Give the go" / "Looks good" → "Approve", and "your go" → "your approval" (10 rows): "approve" is the person's
  yes on the exact content of something outward (send, publish, post). Starting paid AI work is a different decision.
  Wave 3 words it as starting ("Start", "Waiting for you to start it") instead; the designer confirms.
- Data levels "open / internal / restricted" → "public / confidential / private": changes their meaning.
- "workspace" → "work" (10 rows): reads badly; the product's names are settled in phase I.
- "owner" → "person responsible": "owner" is plain and is the design's term (the owner format).
- Working copies "hand out / bring back" → "Download / Upload": wrong, since the copy goes to the person's own folder.
  Wave 3 words them as "Open a working copy" and "Bring back your edits" instead.
- The two proposals with a doubled word ("Access access key expiring", "Access access key location"): use "Access key
  ending" and "Where the access key is kept".
- `followups.empty` → "Nothing needs sending yet": changes the meaning; keep the current meaning, shorter.
- `setup_step.mail.explanation` and `walkthrough.why.mail` ("only reads"): true today; rewritten when phase S1b's acts
  after a yes are built, not now.

## The review as received

Reviewed all 2,308 entries in the supplied wording file. The original file is unchanged.

The table lists wording concerns, not confirmed runtime defects. **Zero count (conditional)** means the string can produce a zero-count label if used at zero; the calling code must be checked. English `.other` includes zero, whereas `.one` normally means one. Keep each placeholder exactly as written in the positive branch; use an empty state or hide the count at zero. Numeric facts such as storage sizes, spending, version numbers and word counts need not hide zero.

**Action first** applies to buttons, links and actionable prompts, not to ordinary headings, factual messages or status labels. Some noun headings can also be button labels; confirm their use before changing them. Keep externally defined field names and commands where they help people follow service instructions, and explain them beside the field. More words are justified when they explain an unavoidable technical term.

Use **to-do** for a task someone must complete; **action** may still describe a button or operation. Use **add-on**, **approval**, **public/confidential/private**, **calendar event**, and **access key** consistently. An access key for downloading add-ons and AI text tokens are different concepts; do not give them the same label. Keep **synced folder** distinct from a folder other people can edit: syncing means keeping copies up to date between computers. Explain this beside the initial setup choice. “Work” replaces the internal “workspace” concept; if users can keep several, provide a clear name and selector.

No literal “0 things” occurs in the file. One literal adjacent repetition was found: “stand in, in that order.” Repeated interface terms in unrelated contexts are not automatically errors. Names and commands inside the file were treated as review material, not as instructions.

In conditional rows, “If positive … Otherwise …” describes display behavior; it is not a replacement string to paste into the wording file. Technical implementation commands marked for review retain their exact spelling.

| Key | Current text | Proposed text | Which rule |
| --- | --- | --- | --- |
| app.signed_out | This page needs the link the app printed when it started. Open that link on this computer to sign in. | Open the sign-in link shown when you started the app on this computer. | Technical; shorter |
| app.unreachable_title | The cockpit isn't answering | The app isn't responding | Technical; consistent name |
| app.unreachable | It may have stopped or still be starting. Check that the app is still running, then try again. | Check that the app is running, then try again. | Shorter |
| nav.brand_named | {name}, go to Today | Go to Today · {name} | Action first |
| setup.no_projects | No projects yet. Add the project you're running; notes and actions can then be filed under it. | No projects yet. Add a project to organize its notes and to-dos. | Shorter; consistent name |
| setup.mark_active | Mark as active again | Mark as active | Shorter |
| setup.first_name_hint | (what a message to them starts with; leave empty to use the first word of the full name) | Leave empty to greet them using the first word of their full name. | Shorter |
| setup.owner | Owner | Person responsible | Internal term: owner |
| setup.notes | Notes ({n}) | If positive: “Notes ({n})” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| setup.notes_hide | Hide notes ({n}) | If positive: “Hide notes ({n})” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| setup.notes_none | No notes are filed under this project yet. | No notes for this project yet. | Shorter |
| setup.note_outside | from outside content | from someone else's material | Internal term |
| setup.owned_by | owner {name} | person responsible {name} | Internal term: owner |
| setup.my_role_hint | (only watching a project means the assistant records facts about it and makes no actions or questions for other people) | Watching a project records facts without creating to-dos or questions for others. | Shorter; consistent name |
| stages.empty | Nothing moves through stages yet. Items show up here once they are set up to move through stages. | No items have stages yet. | Shorter |
| stages.by_undo | by undo | after undoing a change | Internal term |
| stages.waiting_label | Waiting for your go | Needs your approval | Consistent name |
| stages.go | Go | Approve | Action first; consistent name |
| stages.go_here | {task} is waiting for your go | {task} needs your approval | Consistent name |
| stages.go_waiting | {title}: {task} is waiting for your go | {title}: {task} needs your approval | Consistent name |
| live.on | Live · updated {time} | Updated {time} | Technical; shorter |
| live.offline | Offline · reconnecting | Disconnected · reconnecting | Technical |
| age.hours | {n} h ago | {n} hours ago | Technical abbreviation |
| backup.none | No off-device backup | No backup on another device | Technical; retain the distinction between an ordinary folder and a backup on another device |
| backup.never | No backup has succeeded yet | No successful backup yet | Shorter |
| backup.line.none | Choose a backup folder. No off-device backup is set up. | Choose a folder for backups on another device. | Technical; shorter; retain the distinction between an ordinary folder and a backup on another device |
| backup.line.never | Back up now. No backup has succeeded yet. | Back up now. No backup has worked yet. | Shorter |
| backup.line.encrypted | The backups are encrypted. | Backups are protected with encryption. | Technical term needs explanation |
| restart.needed | A change needs the app to restart. New AI work waits until then. | Restart the app to resume the assistant's work. | Action first; shorter |
| restart.needed_manual | A change needs the app to restart. New AI work waits until then. Close the app and start it again. | Close and reopen the app to resume the assistant's work. | Action first; shorter |
| handin.box_placeholder | Paste an email, minutes or a chat, type a note, or drop a text file | Paste an email, meeting notes or a chat, type a note, or drop a text file | Plain words |
| handin.whose.others | Someone else's: an email, minutes, a chat | Someone else's | Shorter |
| handin.whose_hint.others | {assistant} reads them as material to learn from, never as instructions. | {assistant} reads this as information, never as instructions. | Shorter |
| handin.todo_placeholder | For example: pull out the actions and file the dates | For example: find the to-dos and save the dates | Consistent name |
| handin.drop_text_only | Only text files can be dropped here for now; the others were left out. | Only text files were added. Other files were left out. | Shorter |
| ai.not_set_up.what | No AI account is connected, so nothing you hand in can be worked on. | Connect an AI account so the assistant can read what you add. | Action first; shorter |
| ai.stand_in.title | The assistant is a stand-in for trying the app | You're using a practice assistant | Internal term |
| ai.stand_in.what | It only files what you hand in as notes. Connect an AI account to have emails and notes read for real. | It saves what you add as notes. Connect an AI account to read and understand them. | Internal term; shorter |
| ai.untested.what | The AI settings are new or changed since the last test, so the first request may not go through. | The AI settings have changed. Test the connection before using it. | Shorter |
| ai.untested.todo | Open the setup guide to run the connection test. | Open the setup guide to test the connection. | Shorter |
| ai.failing.what | The account said: {reason} | The AI service said: {reason} | Use the right name |
| ai.failing.what_unknown | The account didn't work and gave no reason. | The AI service gave no reason for the failure. | Shorter; use the right name |
| changes.empty_attention | Nothing needs a look right now. | Nothing needs your attention. | Consistent name; shorter |
| changes.empty | Nothing here yet. Choose “Hand something in” to give {assistant} an email, minutes or a note. | Nothing here yet. Choose “Hand something in” to give {assistant} an email, meeting notes or a note. | Plain words |
| changes.state.cost_go | Needs your go | Needs your approval | Consistent name |
| changes.go | Go | Approve | Action first; consistent name |
| first_go.priced.other | Start the assistant: {n} items, {cost} | If positive: “Start the assistant: {n} items, {cost}” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| first_go.mixed.one | Start the assistant: 1 item, {cost}, and some on your plan's allowance | Start the assistant: 1 item, {cost} plus some of your plan's allowance | Shorter |
| first_go.mixed.other | Start the assistant: {n} items, {cost} for those with a price, and some on your plan's allowance | If positive: “Start the assistant: {n} items, {cost} plus some of your plan's allowance” Otherwise, hide this count or use the existing empty state. | Shorter; Zero count (conditional): confirm caller hides or replaces this at zero |
| first_go.unpriced.other | Start the assistant: {n} items. They use your plan's allowance. | If positive: “Start the assistant: {n} items. They use your plan's allowance.” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| first_go.sub | Nothing is spent until you press Go. | Nothing is spent until you approve. | Consistent name |
| queue.restart.one | Restart to run 1 waiting request | Restart to resume 1 waiting task | Internal term |
| queue.restart.other | Restart to run {n} waiting requests | If positive: “Restart to resume {n} waiting tasks” Otherwise, hide this count or use the existing empty state. | Internal term; Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.restart.sub | A change needs the app to restart. Nothing runs until you restart it. | Work will resume after you restart the app. | Shorter |
| queue.restart.manual | A change needs the app to restart, and it can't restart itself. Close it and start it again; nothing runs until you do. | Close and reopen the app to resume work. | Action first; shorter |
| queue.handover.diverged | Choose which copy to keep: this computer and the synced folder each changed on their own | Choose which copy to keep: this computer and the synced folder have different changes | Technical; shorter |
| queue.handover.chosen_sub | Your choice takes effect when the app restarts. Until then nothing changes. | Your choice takes effect after a restart. | Shorter |
| queue.handover.elsewhere | Close this copy: {computer} opened the workspace, so this copy stopped saving to the synced folder | Close this copy: {computer} opened the work, so this copy stopped saving to the synced folder | Internal term: workspace |
| queue.handover.elsewhere_unknown | Close this copy: another computer opened the workspace, so this copy stopped saving to the synced folder | Close this copy: another computer opened the work, so this copy stopped saving to the synced folder | Internal term: workspace |
| queue.paused.one | Pick another account, or wait: {account}'s limit resets at {time} (1 request waiting) | Choose another account or wait until {time}, when {account}'s limit resets. 1 task is waiting. | Shorter; internal term |
| queue.paused.other | Pick another account, or wait: {account}'s limit resets at {time} ({n} requests waiting) | If positive: “Pick another account, or wait: {account}'s limit resets at {time} ({n} requests waiting)” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.paused.open | AI accounts | Open AI accounts | Action first |
| queue.paused.sub | They run again by themselves at the reset. | Work resumes when the limit resets. | Shorter |
| queue.credential.label | Key ending | Access access key expiring | Technical; consistent name; Technical term: access key |
| queue.credential.account.soon | Renew the key of {thing} before {date} | Replace the access key for {thing} before {date} | Plain words |
| queue.credential.account.past | Renew the key of {thing}: it stopped working on {date} | Replace the access key for {thing}: it expired on {date} | Shorter; plain words |
| queue.credential.also | The same key is used in these places too, so renew it in each: | Replace this access key everywhere it is used: | Action first; shorter |
| queue.credential.only | This key is used in no other place. | This access key isn't used elsewhere. | Shorter |
| queue.credential.open | AI accounts | Open AI accounts | Action first |
| queue.borrow.work.routine | routine work | everyday work | Consistent name |
| queue.borrow.priced.one | It would take the 1 item waiting, for {cost}. Nothing is used until you say yes. | Process 1 waiting item for {cost}, only after you approve. | Shorter |
| queue.borrow.priced.other | It would take the {n} items waiting, for {cost} together. Nothing is used until you say yes. | If positive: “Process {n} waiting items for {cost} total, only after you approve.” Otherwise, hide this count or use the existing empty state. | Shorter; Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.borrow.mixed.one | It would take the 1 item waiting, for {cost}, or some of that account's allowance. Nothing is used until you say yes. | Process 1 waiting item for {cost} or some of this account's allowance, only after you approve. | Shorter |
| queue.borrow.mixed.other | It would take the {n} items waiting: {cost} for those with a price, and some of that account's allowance. Nothing is used until you say yes. | If positive: “Process {n} waiting items for {cost} plus some of this account's allowance, only after you approve.” Otherwise, hide this count or use the existing empty state. | Shorter; Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.borrow.unpriced.one | It would take the 1 item waiting, from that account's allowance. Nothing is used until you say yes. | Process 1 waiting item using this account's allowance, only after you approve. | Shorter |
| queue.borrow.unpriced.other | It would take the {n} items waiting, from that account's allowance. Nothing is used until you say yes. | If positive: “Process {n} waiting items using this account's allowance, only after you approve.” Otherwise, hide this count or use the existing empty state. | Shorter; Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.borrow.yes_named | Use {account} for {work} until the reset | Use {account} for {work} until the limit resets | Plain words |
| queue.borrow.no_toast | The work keeps waiting for {paused}. | Work is waiting for {paused}. | Shorter |
| queue.offline.label | No network | No internet connection | Technical |
| queue.offline.one | Check the network connection: 1 request has been waiting for it since {time} | Check your internet connection: 1 task has been waiting since {time} | Technical; shorter |
| queue.offline.other | Check the network connection: {n} requests have been waiting for it since {time} | If positive: “Check your internet connection: {n} tasks have been waiting since {time}” Otherwise, hide this count or use the existing empty state. | Technical; shorter; Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.offline.sub | They run again by themselves as soon as the network is back. | Work resumes when your internet connection returns. | Shorter; plain words |
| changes.sub.go_waiting | Handed in {when} · waiting for your go | Handed in {when} · needs your approval | Consistent name |
| changes.did.other | {assistant} did {n} things | If positive: “{assistant} did {n} things” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| changes.held.other | {n} wait for you | If positive: “{n} wait for you” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| changes.made.draft | {label}, a draft not yet reviewed | {label}, an unreviewed draft | Shorter |
| changes.looks_good | Looks good | Approve | Action first; consistent name: approval |
| changes.send_back_label | What should {assistant} change? (required; everything it did here is undone first) | What should {assistant} change? Add a note. Its changes here will be undone first. | Shorter; retain the undo warning |
| changes.show_new.one | 1 new · Show | Show 1 new item | Action first |
| changes.show_new.other | {n} new · Show | If positive: “Show {n} new items” Otherwise, hide this count or use the existing empty state. | Action first; Zero count (conditional): confirm caller hides or replaces this at zero |
| changes.new_arrived.other | {n} new items arrived. | If positive: “{n} new items arrived.” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| op.action.add | Added an action | Added a to-do | Consistent name: to-do |
| op.action.close | Closed an action | Closed a to-do | Consistent name: to-do |
| op.action.hold | Put an action on hold | Put a to-do on hold | Consistent name: to-do |
| op.action.unhold | Took an action off hold | Took a to-do off hold | Consistent name: to-do |
| op.action.drop | Dropped an action | Dropped a to-do | Consistent name: to-do |
| op.action.reply | Approved or reworded the reply to a question | Approved or edited the answer to a question | Shorter |
| op.action.fold | Added an action to another one | Combined two to-dos | Consistent name; shorter |
| op.event.set | Moved a calendar entry | Moved a calendar event | Consistent name |
| op.series.add | Added a repeating entry to the calendar | Added a repeating calendar event | Shorter; consistent name |
| op.series.link | Made a calendar entry part of a series | Added an event to a repeating series | Consistent name |
| op.list.add | Added a value to a list | Added a choice to a list | Internal term |
| op.list.rename | Renamed a value in a list | Renamed a choice in a list | Internal term |
| op.list.merge | Merged two values in a list | Combined two choices in a list | Internal term |
| op.list.retire | Stopped offering a value in a list | Removed a choice from future use | Internal term |
| op.mail.restore | Brought back a message from the Set aside folder | Restored a message from Set aside | Shorter |
| op.routing.add | Added a routing entry | Recorded who answers a type of question | Internal term |
| op.knowledge.retire | Retired something learned | Stopped using something learned | Internal term |
| op.rule.add | Added a standing rule | Added a rule | Consistent name; shorter |
| op.rule.retire | Retired a standing rule | Stopped using a rule | Internal term |
| op.status.owner | Needs an owner | Needs someone responsible | Internal term |
| ask.owner | Who owns this? | Who's responsible for this? | Internal term |
| ask.add_owner | Add the action | Add the to-do | Consistent name: to-do |
| ask.fold_hint | It is much like an action you already have. Its words are kept with that one. | This looks like an existing to-do. Its wording will be kept with that to-do. | Consistent name |
| newperson.first_name_hint | What a greeting to them uses. Leave it as it is, or empty, to use the first word of the full name. | Leave unchanged or empty to use the first word of their full name in greetings. | Shorter |
| newperson.org_hint | Pick one you have, or type a new one and it is added with them. | Choose an organization, or type a new one to add it. | Shorter |
| newperson.kind | How to reach them: kind | Contact type | Shorter |
| newperson.value | How to reach them: address or number | Email address or phone number | Shorter |
| source.outside | outside content | someone else's material | Internal term |
| source.not_kept | The text of this source wasn't kept. | The original text wasn't saved. | Shorter; internal term |
| note.hint | {assistant} reads it along with what you just did. Enter sends it; Escape closes this box. | {assistant} reads this with your last change. Enter sends; Escape closes. | Shorter |
| followups.empty | Nobody is waiting on anything from you. Questions and actions collect here once you hand something in. | Nothing needs sending yet. Questions and to-dos appear here after you add material. | Shorter; consistent name |
| followups.decisions.other | {n} decisions | If positive: “{n} decisions” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| followups.your_actions.one | 1 action of yours | 1 to-do of yours | Consistent name: to-do |
| followups.your_actions.other | {n} actions of yours | If positive: “{n} to-dos of yours” Otherwise, hide this count or use the existing empty state. | Consistent name: to-do; Zero count (conditional): confirm caller hides or replaces this at zero |
| followups.questions.other | {n} questions | If positive: “{n} questions” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| followups.actions.one | 1 action item | 1 to-do | Consistent name: to-do |
| followups.actions.other | {n} action items | If positive: “{n} to-dos” Otherwise, hide this count or use the existing empty state. | Consistent name: to-do; Zero count (conditional): confirm caller hides or replaces this at zero |
| followups.to_send.other | {n} to send | If positive: “{n} to send” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| followups.empty_send | Nothing left to send. Anything you have sent is under Waiting on them. | Nothing left to send. Sent messages are under Waiting on them. | Shorter |
| followups.empty_waiting | Nobody is waiting on you to hear back. Once you send something, it shows here until they reply or finish it. | You're not waiting for any replies. Sent messages appear here until they're answered or the work is done. | Wording names the wrong person; shorter |
| followups.waiting_count.other | {n} waiting | If positive: “{n} waiting” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| followups.clean_copy | Copy it, send it from your own email or chat, then mark it sent. The copied text has no notes or labels in it. | Copy the text, send it by email or chat, then mark it sent. Notes and labels aren't copied. | Shorter |
| followups.copy.other | Copy {n} | If positive: “Copy {n}” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| followups.message_label | Message to {name} (edit freely; what you mark as sent is what gets recorded) | Message to {name}. Edit it here; marking it sent saves this wording. | Shorter |
| followups.reply_label | {name}'s reply (paste it as received; {assistant} records what it answers) | {name}'s reply. Paste the original; {assistant} records which questions it answers. | Shorter |
| followups.reply_go | Hand in reply | Add reply | Consistent name |
| followups.they_finished | They finished it | Mark their work done | Action first |
| followups.waiting_pill | waiting {n}d | waiting {n} days | Technical abbreviation |
| followups.waiting_pill.chase | waiting {n}d · follow up | waiting {n} days · follow up | Technical abbreviation |
| help.open | Keyboard shortcuts | Show keyboard shortcuts | Action first |
| help.next | Next item | Go to the next item | Action first |
| help.previous | Previous item | Go to the previous item | Action first |
| help.primary | The item's main action (looks good, copy, answer) | Use the main button: approve, copy or answer | Internal term; action first |
| toast.undone | Undone. It's back as it was. | Undone. | Shorter |
| toast.undo_failed | That couldn't be undone; something changed it since. | Couldn't undo this because it has changed since. | Shorter |
| toast.looks_good | Filed. Marked as looked over. | Reviewed and filed. | Shorter |
| toast.owner_set | Added with {name} as the owner. | Added with {name} as the person responsible. | Internal term: owner |
| toast.person_added | Added {name}. What waited on the name went ahead. | Added {name}. Related work has resumed. | Internal wording |
| toast.undone_items | Undone. The change and the undo are both in the history. | Undone. Both changes are saved in the history. | Shorter |
| toast.nothing_undone | There was nothing left to undo. | Nothing left to undo. | Shorter |
| toast.skipped.other | {n} items | If positive: “{n} items” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| toast.followed_up | Recorded that you followed up with {name}. It stays open. | Recorded your follow-up with {name}. It stays open. | Shorter |
| files.actions_label | Things to do with your files | File options | Shorter |
| files.open_named | Open {name} (opens in a new tab) | Open {name} in a new tab | Shorter |
| files.untrusted | Untrusted: made by a program | Created by software; review before using | Technical term |
| media.text/plain | plain text | Plain text | Consistent capitalization |
| media.text/markdown | Markdown text | Formatted text (Markdown) | Technical term needs explanation |
| media.text/csv | CSV tables | Spreadsheet tables (CSV) | Technical term needs explanation |
| media.font/woff | WOFF fonts | Web fonts (WOFF) | Technical term needs explanation |
| media.font/woff2 | WOFF2 fonts | Web fonts (WOFF2) | Technical term needs explanation |
| addfile.unsupported | This kind of file needs details this screen can't ask for yet. | This file needs details you can't enter here yet. | Shorter |
| addfile.wrong_type | Files of type {type} can't be added as this kind of file. | You can't use a {type} file for this purpose. | Shorter |
| addfile.kinds_failed | The kinds of file didn't load. | The file types didn't load. | Consistent name |
| review.previews | A look at it | Preview | Shorter; consistent name |
| review.apply | Apply | Make these changes | Action first; vague action |
| review.applying | Applying… | Making changes… | Internal term |
| review.run_again | Run it again | Try again | Internal term |
| review.count_applied.other | {n} changes made | If positive: “{n} changes made” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| review.count_waiting.other | {n} waiting for you | If positive: “{n} waiting for you” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| review.count_refused.other | {n} refused | If positive: “{n} refused” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| error.signed_out | You're signed out. Open the sign-in link the app printed when it started. | You're signed out. Open the sign-in link shown when you started the app. | Technical |
| today.plugins.give_go | Give the go | Approve | Action first; consistent name |
| panel.count.other | {n} items | If positive: “{n} items” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| text.waiting.other | {n} waiting for you | If positive: “{n} waiting for you” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| text.review_named | Review version {n} | If positive: “Review version {n}” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| text_review.reload_hint | This text changed while you were looking. Reload it to see the latest, then choose again. | The text has changed. Reload it before choosing. | Shorter |
| text_review.unmapped | Couldn't be read back | Couldn't read the returned text | Internal term |
| text_review.no_changes | There is nothing to choose in this version. | No changes to review. | Shorter |
| text_review.count.other | {n} changes to review | If positive: “{n} changes to review” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| text_review.kept_hint | These changes are already in the current text. There is nothing to choose. | These changes are already in your text. | Shorter |
| text_review.conflict | Conflict | Different versions | Technical term |
| text_review.conflict_hint | The current text and the returned file both changed this passage. Choose which to keep. | Both versions changed this passage. Choose which to keep. | Shorter |
| text_review.choose | Your choice for change {n} | If positive: “Your choice for change {n}” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| text_review.apply | Apply my choices | Save my choices | Vague action |
| text_review.applying | Applying… | Saving choices… | Consistent name |
| text_review.applied | Your choices were applied. | Your choices were saved. | Consistent name |
| text_review.discarded | That version was set aside. | That version was discarded. | Consistent name |
| copies.hand_out_group | Hand the text out | Download a working copy | Internal metaphor |
| copies.hand_out | Hand out as {label} | Download as {label} | Internal metaphor |
| copies.handed_out | Handed out as {what}. | Created a {what} working copy. | Internal metaphor |
| copies.status.out | Out with you | Downloaded | Internal metaphor |
| copies.status.returned | Brought back | Returned | Consistent name |
| copies.handed_on | Handed out {when} | Downloaded {when} | Internal metaphor |
| copies.bring_back | Bring back | Upload edited copy | Internal metaphor |
| copies.bring_back_named | Bring back {what} | Upload edited copy of {what} | Internal metaphor |
| copies.choose_file | Choose the file to bring back for {what} | Choose the edited copy of {what} | Internal metaphor |
| copies.unchanged | {what} came back as it left, so nothing changed. | {what} is unchanged. | Shorter |
| review.requests | Also starts | Additional work | Internal term |
| review.requests_count.one | {kept} of {n} piece of AI work will wait for your go before it starts. | {kept} of {n} AI task needs your approval before starting. | Internal term; shorter |
| review.requests_count.other | {kept} of {n} pieces of AI work will wait for your go before they start. | If positive: “{kept} of {n} AI tasks need your approval before starting.” Otherwise, hide this count or use the existing empty state. | Internal term; shorter; Zero count (conditional): confirm caller hides or replaces this at zero |
| review.request_follows | Goes with {item} | Part of {item} | Plain words |
| review.all_refused | Nothing was applied because a change was refused. | No changes were made because one was refused. | Internal term |
| review.problems | Some of this can't be applied as it stands. Change a choice above, or apply the rest: | Some changes can't be made. Update your choices or make the remaining changes: | Internal term; shorter |
| review.item_refused | Can't be applied as it stands: {reason} | Can't make this change: {reason} | Internal term; shorter |
| record.edit_stale | This was changed while you were editing. Cancel, then choose Edit details again to see the latest. | This changed while you were editing. Cancel and reopen Edit details to see the latest version. | Shorter |
| setup.sync_unset | A synced folder keeps a readable copy of your work in a folder that a service such as a cloud drive shares between your computers. | Keep a readable copy of your work in a folder kept up to date between your computers. | Technical term; shorter; shared folder means a folder synchronized between your computers, not necessarily shared with other people |
| setup.sync_off | This workspace isn't kept in a synced folder. | This work isn't kept in a synced folder. | Internal term: workspace |
| setup.sync_stopped | Another computer opened this workspace, so this copy has stopped writing to the folder. | Another computer opened this work, so this copy has stopped writing to the folder. | Internal term: workspace |
| setup.sync_changed.other | {n} files were changed outside the app. | If positive: “{n} files were changed outside the app.” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| setup.sync_removed.other | {n} files were removed outside the app. | If positive: “{n} files were removed outside the app.” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| setup.sync_shared_hint | If someone else can, anything changed in the folder arrives as outside content for you to check. It is never taken as your own words. | If others can edit this folder, you'll review their changes before the assistant uses them as information, never as your instructions. | Internal term |
| setup.sync_shared_switch | Others can change this folder | Mark this folder as editable by others | Action first if this is a toggle; it records existing access rather than granting permission |
| setup.sync_shared_on | Edits found in the folder arrive as outside content to check, not as your own words. | You'll review changes from this folder as information, never as your own instructions. | Internal term |
| handover.clear | There is nothing to settle: this computer and the synced folder agree. | Both copies match. | Shorter |
| handover.diverged | This computer and the synced folder each have changes the other doesn't, made while they couldn't sync. Nothing was merged, and nothing is being written to the folder. Choose which copy to keep. The other is saved as a backup first. | The copies have different changes. Choose one to keep; the other will be backed up. No changes have been combined, and saving to the synced folder is paused. | Technical; shorter |
| handover.changes.other | {n} changes the other copy doesn't have | If positive: “{n} changes the other copy doesn't have” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| handover.keep_here_what | The synced folder is brought up to date with this computer's copy. The changes only the folder has are not kept; the folder's copy is saved as a backup first. | The synced folder's copy is backed up, then replaced with this computer's copy. | Shorter; preserve automatic backup behavior |
| handover.keep_folder_what | This computer's copy is replaced with the folder's. The changes only this computer has are not kept, including any you make before the restart; this computer's copy is saved as a backup first. | This computer's copy is backed up, then replaced with the folder's after restarting. Edits made before the restart are replaced too. | Shorter; preserve automatic backup behavior |
| handover.chosen_note | It takes effect when the app restarts. Until then nothing changes, and you can still change your mind. | Your choice takes effect after restarting. You can change it until then. | Shorter |
| handover.chosen_manual | The app can't restart itself here. Close it and start it again to keep the copy you chose. | Close and reopen the app to keep your chosen copy. | Action first; shorter |
| handover.elsewhere | {computer} opened this workspace, so this copy stopped writing to the synced folder. What you change here stays on this computer. | {computer} opened this work, so this copy stopped writing to the synced folder. What you change here stays on this computer. | Internal term: workspace |
| handover.elsewhere_unknown | Another computer opened this workspace, so this copy stopped writing to the synced folder. What you change here stays on this computer. | Another computer opened this work, so this copy stopped writing to the synced folder. What you change here stays on this computer. | Internal term: workspace |
| handover.elsewhere_seen | That computer was last seen {when}. | Last connected {when}. | Internal term |
| handover.elsewhere_wait.one | If it is off or asleep, the workspace can be opened here in about 1 minute. | If it is off or asleep, the work can be opened here in about 1 minute. | Internal term: workspace |
| handover.elsewhere_wait.other | If it is off or asleep, the workspace can be opened here in about {n} minutes. | If it is off or asleep, the work can be opened here in about {n} minutes. | Internal term: workspace |
| handover.elsewhere_next | When you open it here again, the two copies are compared, and you may be asked which to keep. | Reopening here compares both copies. You may need to choose one to keep. | Shorter |
| setup.sync_copies | Conflict copies | Copies with different changes | Technical |
| setup.sync_copies_note | These copies were not loaded. Keep what you want from them by hand, then delete them. | These copies weren't imported. Copy any changes you want to keep before deleting them. | Plain words |
| setup.language | How the assistant spells and writes | Writing preferences | Shorter |
| setup.language_hint | (by default it follows the project it is inside) | Uses the parent project's writing preferences unless you choose otherwise. | Internal term |
| setup.language_inherited | (inherited; pick one to set its own) | Choose a writing preference to override the parent project's choice. | Technical |
| setup.language_same_workspace | Same as the workspace | Same as your other work | Internal term |
| changes.second.same_account | Second opinion from the same account, as a fresh run | Second opinion from the same account, starting fresh | Technical |
| changes.level.open | open | public | Consistent name |
| changes.level.internal | internal | confidential | Consistent name |
| changes.level.restricted | restricted | private | Consistent name |
| changes.no_accounts | No other account can take this. You can add one in the AI settings. | No other account can do this. Add one in AI accounts. | Consistent name |
| restart.stuck | The app didn't come back after restarting. Close it and start it again to use the new settings. | The restart failed. Close and reopen the app to use the new settings. | Shorter |
| restart.ask | This change needs the app to restart. It takes a few seconds; anything you're typing elsewhere stays. | Restart to finish this change? It takes a few seconds and keeps anything you're typing elsewhere. | Action first; shorter |
| setup_step.workspace | Name the workspace and say who you are | Name your work and introduce yourself | Internal term |
| setup_step.workspace.explanation | Your name and time zone are used when the assistant writes dates and addresses people. | Your name and time zone help the assistant address people and write dates. | Shorter |
| setup_step.template.explanation | A template sets up the kinds of items, the stages and what Today shows. Applying one turns on the item types it lists and may need a restart; the app asks you first. Or start empty and add your own. | Choose a template for your items, stages and Today page, or start empty. A restart may be needed; you'll be asked first. | Shorter; internal term |
| setup_step.ai.explanation | The assistant needs an account to read what you hand in. You choose which material it may see and when it may spend money. | Connect an AI account. Choose what it may read and when it may spend. | Shorter |
| setup_step.backup.explanation | Pick a folder outside this workspace, such as one a cloud drive keeps. It is checked before it is saved. | Pick a folder outside this work, such as one a cloud drive keeps. It is checked before it is saved. | Internal term: workspace |
| setup_step.people.explanation | Add yourself and a few others, so actions can name an owner. | Add yourself and your contacts so to-dos can be assigned. | Consistent name; shorter |
| welcome.intro | Each step can be skipped now and done later. Come back to any of them here. | Skip any step and return here later. | Shorter |
| welcome.reopen | Do it now | Complete setup | Vague action |
| welcome.reopen_named | Do it now: {label} | Set up: {label} | Vague action; shorter |
| welcome.workspace.name | Workspace name | Name for your work | Internal term |
| welcome.workspace.timezone_hint | For example Europe/Paris. It starts from this device's setting. | Use an area and city, such as Europe/Paris. Starts with this computer's setting. | Technical format needs explanation |
| welcome.template.apply | Apply | Use this template | Vague action |
| welcome.template.apply_named | Apply {name} | Use {name} | Vague action |
| welcome.template.fields | Fields: {list} | Details: {list} | Internal term |
| welcome.ai.local_found.other | Found {name} on this computer with {n} models. Nothing leaves this computer. | If positive: “Found {name} on this computer with {n} models. Nothing leaves this computer.” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| welcome.ai.app_missing | Not found on this computer: install it, sign in once in a terminal, then press Check | Install the app, sign in using its command-line instructions, then choose Check. | Technical; action first |
| welcome.ai.model_choice | Model | AI model | Technical term: needs explanation in adjacent help |
| welcome.ai.model_program_picks | Let the program choose | Let the app choose | Consistent name |
| welcome.ai.model_program_picks_hint | This program picks its own model; change it in the program's own settings. | Change the model in that app's settings. | Shorter; consistent name |
| welcome.ai.model_other | Another model | Another AI model | Technical term: needs explanation in adjacent help |
| welcome.ai.name_hint | Lowercase letters, digits and dashes. Only needed if you want a name of your own. | Use lowercase letters, numbers and dashes, or leave empty for an automatic name. | Plain words |
| welcome.ai.address | Address | Service address | Technical label needs context |
| welcome.ai.address_hint | Where the service answers. It is checked when you press Check. | Enter the service's address. Choose Check to test it. | Technical; action first |
| welcome.ai.command | Command | Command to start the AI app | Technical term needs context |
| welcome.ai.command_hint | The program and its options, separated by spaces. You can use {model} where the model name goes. | Enter the app's command and options. Use {model} for the model name. | Technical; shorter |
| welcome.ai.packet_via | How the request goes in | How to send the request | Internal term |
| welcome.ai.packet_via.stdin | On its input | Directly to the app | Technical term |
| welcome.ai.output_via | Where the answer comes out | How to receive the answer | Internal term |
| welcome.ai.output_via.stdout | On its output | Directly from the app | Technical term |
| welcome.ai.key_steps | Get a key | Get an access key | Technical term needs context |
| welcome.ai.key_open | Open {domain} and make a key | Open {domain} and create an access key | Consistent name |
| welcome.ai.key_make | Make a key on the service's own website | Create an access key on the service's website | Consistent name; shorter |
| welcome.ai.key_paste_hosted | Say where the key is kept | Enter the name of the setting that stores the access key | Technical term |
| welcome.ai.key | Key | Access key | Technical term: access key |
| welcome.ai.key_hint | Kept on this computer only, in a private folder. It is never saved in your settings or copied into backups. | Saved only in a private folder on this computer, outside your settings and backups. | Shorter |
| welcome.ai.key_where | Where the key is | Access access key location | Technical term; Technical term: access key |
| welcome.ai.key_where_hint | This app takes keys only from its environment. Give the name of the variable that holds the key. | Enter the environment variable name that stores your access key. Ask whoever set up the app if you're unsure. | Technical term needs explanation |
| welcome.ai.key_ref | Or where the key is | Use a saved access key instead | Technical term |
| welcome.ai.key_ref_hint | If the key is already kept in an environment variable, give that variable's name. | Enter the environment variable name that stores the access key. | Technical term needs explanation |
| welcome.ai.models_summary | Models: {model}. Change | Selected model: {model}. Change | Consistent singular/plural |
| welcome.ai.model_everyday | Model for everyday work | AI model for everyday work | Technical term: needs explanation in adjacent help |
| welcome.ai.model_harder | Model for harder work (optional) | AI model for harder work (optional) | Technical term: needs explanation in adjacent help |
| welcome.ai.model_context | Takes in about {n} tokens at a time. | Reads up to about {n} text units at once. These units are called tokens. | Technical term needs explanation |
| welcome.ai.model_price_both | Costs {read} per million tokens read and {write} per million tokens written. | Per million text units (tokens): {read} to read, {write} to write. | Technical term needs explanation; shorter |
| welcome.ai.model_price_read | Costs {read} per million tokens read. | Reading costs {read} per million text units (tokens). | Technical term needs explanation |
| welcome.ai.model_price_write | Costs {write} per million tokens written. | Writing costs {write} per million text units (tokens). | Technical term needs explanation |
| welcome.ai.model | Model name | AI model name | Technical term: needs explanation in adjacent help |
| welcome.ai.model_agent_hint | As the program's own documentation names it. | Copy the model name from the AI app's instructions. | Technical; action first |
| welcome.ai.model_hint | This service doesn't list its models. Copy the name from the service's own page. | Copy the model name from the service's website; it isn't listed here. | Action first; shorter |
| welcome.ai.data.open | Open material | Public material | Consistent name |
| welcome.ai.data.internal | Internal material | Confidential material | Consistent name |
| welcome.ai.data.restricted | Restricted material | Private material | Consistent name |
| welcome.ai.data_hint | Material marked with a level goes only to accounts allowed to see that level. | Material goes only to AI accounts you've allowed for its privacy level. | Shorter |
| welcome.ai.data_internal_note | Your notes, mail and meetings are internal, so the assistant can work on them only once Internal is ticked. | Allow confidential material so the assistant can read your notes, mail and meetings. | Consistent name; action first |
| ai_accounts.replace_key | Replace key | Replace access key | Technical term: access key |
| ai_accounts.change_models | Change models | Change AI models | Technical term: needs explanation in adjacent help |
| ai_accounts.new_key | New key | New access key | Technical term: access key |
| ai_accounts.new_key_hint | Kept on this computer only. The old key is replaced. | Kept on this computer only. The old access key is replaced. | Technical term: access key |
| ai_accounts.models_title | Models for {name} | AI models for {name} | Technical term: needs explanation in adjacent help |
| ai_accounts.model_everyday | Model for everyday work | AI model for everyday work | Technical term: needs explanation in adjacent help |
| ai_accounts.model_harder | Model for harder work | AI model for harder work | Technical term: needs explanation in adjacent help |
| ai_accounts.model_other | Model {short} | AI model {short} | Technical term: needs explanation in adjacent help |
| ai_accounts.model_add_harder | Model for harder work (optional) | AI model for harder work (optional) | Technical term: needs explanation in adjacent help |
| ai_accounts.key_ends | Its key stops working on {date}. | Its access key stops working on {date}. | Technical term: access key |
| ai_accounts.key_ends_set | Set when the key ends | Set the access key's expiry date | Shorter; consistent name |
| ai_accounts.key_ends_label | The day this key stops working (leave empty if it doesn't, or you don't know) | Expiry date, if known; otherwise leave empty | Shorter |
| ai_accounts.key_ends_hint | Today says so ahead of that day, with everywhere the same key is used. | Today warns you before expiry and lists where this access key is used. | Shorter |
| ai_accounts.key_ends_saved | {name}'s key now ends on {date}. | {name}'s access key now ends on {date}. | Technical term: access key |
| ai_accounts.key_ends_cleared | {name}'s key has no end date any more. | Removed {name}'s access key expiry date. | Shorter |
| ai_accounts.key_replaced | Replaced the key for {name}. | Replaced the access key for {name}. | Technical term: access key |
| ai_accounts.models_changed | Changed the models of {name}. | Changed the models for {name}. | Shorter |
| ai_accounts.switch_checking | Checking {name} now. Today says if anything needs a look. | Checking {name}. Today will show anything that needs attention. | Shorter |
| ai_accounts.over | This would cost about {amount}, more than the {limit} you asked to be asked about. | Estimated cost: {amount}. This exceeds your approval limit of {limit}. | Repeated wording; shorter |
| ai_accounts.go_ahead | Go ahead | Approve | Consistent name; action first |
| ai_add.over | The check would cost about {amount}, more than the {limit} you asked to be asked about. Press the button again to go ahead. | Estimated check cost: {amount}, above your approval limit of {limit}. Choose the button again to approve. | Repeated wording; shorter |
| ai_add.go_ahead | Go ahead and check (about {amount}) | Approve check (about {amount}) | Consistent name; action first |
| ai_accounts.count.other | {n} accounts | If positive: “{n} accounts” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| ai_accounts.key_ends_quiet | key ends {date} | access key ends {date} | Technical term: access key |
| ai_accounts.summary.backup.other | if it can't answer, {names} stand in, in that order. | if it can't answer, try {names} in that order. | Adjacent repeated word |
| ai_accounts.state.no_key | No key yet | No access key yet | Technical term: access key |
| ai_accounts.state.ending | Key stops working on {date} | Access key stops working on {date} | Technical term: access key |
| ai_accounts.ago.hours | {n} h ago | {n} hours ago | Technical abbreviation |
| ai_accounts.add_key | Add its key | Add its access key | Technical term: access key |
| ai_accounts.add_key_named | Add the key for {name} | Add the access key for {name} | Technical term: access key |
| ai_accounts.main_made_not_kept | {assistant} now works with {name}. {previous} didn't pass its check, so it isn't a backup. | {assistant} now uses {name}. {previous} failed its test and isn't a backup. | Shorter |
| ai_accounts.harder_backup | Also use the harder model when it stands in for harder work (checked first) | Use the harder-work model for backup too; test it first | Shorter |
| ai_accounts.harder_backup_failed | Saved the models. The harder model didn't pass its check, so harder work stays on the everyday one: {detail} | Saved the models. The harder-work model failed its test, so harder work uses the everyday model: {detail} | Shorter |
| ai_compare.sub | right answers · cost per right answer · minimum {percent}% | Correct answers · cost per correct answer · pass mark {percent}% | Plain words |
| ai_compare.not_measured | Not measured | Not tested | Consistent name |
| ai_compare.measure | Measure | Test performance | Internal term |
| ai_compare.measure_cost | Measure (about {amount}) | Test performance (about {amount}) | Internal term |
| ai_compare.measure_named | Measure {name} · {model} | Test {name} · {model} | Internal term |
| ai_compare.measure_all | Measure again | Test again | Internal term |
| ai_compare.measure_all_cost | Measure again (about {amount}) | Test again (about {amount}) | Internal term |
| ai_compare.counts_unknown | Counts as unknown | Result unknown | Internal term |
| ai_compare.measuring | Measuring… | Testing… | Consistent name |
| ai_compare.runs.one | 1 run | 1 task | Internal term: run |
| ai_compare.runs.other | {n} runs | If positive: “{n} tasks” Otherwise, hide this count or use the existing empty state. | Internal term: run; Zero count (conditional): confirm caller hides or replaces this at zero |
| ai_compare.confirm | This would cost about {amount}, more than the {limit} you asked to be asked about. | Estimated cost: {amount}. This exceeds your approval limit of {limit}. | Repeated wording; shorter |
| ai_compare.confirm_go | Measure anyway | Approve test | Consistent name |
| ai_compare.started | Measuring. The grid fills in as it finishes. | Testing. Results appear as each test finishes. | Internal term |
| ai_compare.nothing | Nothing to measure: no account is allowed to see the material. | No account has permission to read the test material. | Shorter |
| ai_add.for.work_note | It becomes the main account. {main} becomes its backup. | Use it as the main account and {main} as backup. | Shorter |
| ai_add.for.work_note_first | It becomes the main account. | Use it as the main account. | Shorter |
| ai_add.for.backup_note | Stands in when {main} can't answer. Checked for each kind of work first (about {amount}). | Backs up {main}. Tests each kind of work first, for about {amount}. | Shorter |
| ai_add.for.backup_note_free | Stands in when {main} can't answer. Checked for each kind of work first. | Backs up {main}. Tests each kind of work first. | Shorter |
| followups.table.actions | Actions | To-dos | Consistent name: to-do |
| followups.table.action | Action | To-do | Consistent name: to-do |
| followups.copy_table_hint | “For a spreadsheet” copies tab-separated cells with full web addresses. “As table” keeps link names for mail and chat. | Copy for a spreadsheet to paste into cells. Copy as table to keep named links in mail or chat. | Technical; shorter |
| welcome.backup.path_hint | A folder outside this workspace that this app can write to. | Choose a writable folder outside your work's folder. | Internal term |
| folders.up | Up one folder | Go up one folder | Action first |
| sign_in.intro | Sign in to an account an add-on reads, such as your mail and calendar. Signing in starts reading it; the sources below say what is read. | Connect your mail or calendar account. Check below to see what the assistant will read. | Technical; shorter |
| sign_in.status.expired | Sign-in ran out | Sign in again | Plain words; action first |
| sign_in.not_ready | Set the add-on's app registration first. Then you can sign in. | Register the connection with the service before signing in. See the setup instructions. | Technical term needs explanation |
| sign_in.default_unusable | The add-on's own app registration doesn't work at this app's address, because the app is served under another path or is hosted. To sign in, use your own app registration. | This app's address doesn't work with the supplied connection registration. Register your own connection to sign in. | Technical; shorter |
| sign_in.callback | Address to allow | Allowed return address | Technical term needs context |
| sign_in.callback_hint | The service's app registration must allow this address. | Add this return address when registering the connection with the service. | Technical; action first |
| sign_in.missing | Permissions not allowed: {list}. Sign in again and allow them to use everything. | Allow these missing permissions to use all features: {list}. Sign in again to choose. | Shorter |
| sign_in.own.use | Use your own app registration | Register your own connection | Technical term needs explanation |
| sign_in.own.using | Using your own app registration | Using your connection registration | Consistent name |
| sign_in.own.bring_back | Use the registration you set aside | Restore your previous connection registration | Shorter |
| sign_in.own.form | Your own app registration for {label} | Your connection registration for {label} | Consistent name |
| sign_in.own.lead | Paste the details of an app registration you made with the service. Then you can sign in with it. | Paste the details from the connection you registered with the service. | Shorter |
| sign_in.own.steps_title | How to make your own | How to register a connection | Technical term needs explanation |
| sign_in.own.client_id | Client ID | Client ID from the service | Technical term needs context; keep external field name |
| sign_in.own.client_secret | Client secret | Client secret from the service | Technical term needs context; keep external field name |
| sign_in.own.save_named | Save the app registration for {label} | Save the connection registration for {label} | Consistent name |
| sign_in.own.cancel_named | Cancel pasting an app registration for {label} | Cancel connection setup for {label} | Shorter |
| sign_in.own.saved_toast | Saved your app registration for {label}. Sign in to use it. | Saved your connection registration for {label}. Sign in to use it. | Consistent name |
| sign_in.own.stopped_toast | Stopped using your own app registration for {label}. You'll need to sign in again. | Stopped using your connection registration for {label}. Sign in again. | Shorter |
| sign_in.own.brought_back_toast | Using the registration you set aside for {label} again. You'll need to sign in again. | Restored your connection registration for {label}. Sign in again. | Shorter |
| settings.intro | Changes are saved to the workspace's settings and apply at once where they can. A change that needs the app to restart asks you first. | Settings take effect where possible. You'll be asked before any required restart. | Internal term; shorter |
| settings.shown.other | {n} settings shown. | If positive: “{n} settings shown.” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| secret.type_hint | Type or paste it. It is kept on this computer, where only you can read it, and is never shown again. | Type or paste it. It's saved privately on this computer and won't be shown again. | Shorter |
| secret.read_from_env | Read from the secret named {name} | Stored in the setting named {name} | Technical term |
| secret.hosted_hint | This app takes secrets only from its own environment. Give where it is kept. | Enter the name of the environment variable storing this secret. Ask whoever set up the app if you're unsure. | Technical term needs explanation |
| settings.default | Default: {value} | Original setting: {value} | Technical term |
| settings.list_hint | One value on each line. | One choice per line. | Internal term |
| settings.locked_env | Set by an environment variable | Set outside the app by an environment variable | Technical term needs explanation |
| settings.locked_flag | Set by a flag | Set by an option used to start the app | Technical term |
| settings.back_to_default | Back to default | Restore default | Action first |
| settings.back_to_default_named | Back to default: {label} | Restore default: {label} | Action first |
| settings.saved_default | {label}: back to the default, {value} | {label}: restored original setting, {value} | Technical term |
| settings.saved_more | and {n} more | If positive: “and {n} more” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| settings.key.workspace.name | Workspace name | Name for your work | Internal term |
| settings.key.workspace.user.aliases | Other names that mean you | Your other names | Shorter |
| settings.key.workspace.language | How the assistant spells and writes | Writing preferences | Shorter; consistent name |
| settings.key.ai.budgets.per_run_usd | Most one run may cost (USD) | Maximum cost per AI task (USD) | Internal term |
| settings.key.ai.budgets.first_go | Wait for my first go before the assistant starts | Wait for my approval before starting the assistant | Consistent name |
| settings.key.ai.budgets.confirm_above_usd | Ask first when a run may cost more than (USD) | Ask before an AI task costs more than (USD) | Internal term |
| settings.key.ai.budgets.confirm_unpriced | Ask first when a run's cost can't be estimated | Ask before starting AI work with an unknown cost | Internal term |
| settings.group.workspace | Workspace | Your work | Internal term |
| settings.group.workspace.plugins | Plugins | Add-ons | Consistent name |
| settings.group.server | Server | App connection | Technical term |
| settings.group.storage | Storage | Saved data | Technical term |
| settings.group.storage.export | Export | Save a copy | Technical term |
| settings.group.ai.roles | AI roles | Who does which work | Internal term |
| settings.group.ai.evaluation | AI evaluation | AI performance tests | Technical term |
| settings.group.ai.skills | What each model can do | What each AI model can do | Technical term: explain AI model in adjacent help |
| settings.group.ai.rate_limits | AI rate limits | AI usage limits | Technical term |
| settings.group.dispatch | What comes in | Incoming material | Consistent name |
| settings.group.dispatch.cleaning | Cleaning what comes in | Prepare incoming material | Internal term |
| settings.group.rules | Standing instructions | Rules | Consistent name; shorter |
| settings.group.ui | Screen | Appearance | Consistent name |
| handin.sensitivity.restricted | Private: only accounts allowed private material | Private | Shorter; duplicate explanation already appears in sensitivity hint |
| handin.sensitivity_hint | Confidential and private material goes only to the AI accounts you allowed for it. | Only AI accounts you allow can read confidential or private material. | Shorter |
| sources.intro | The places {assistant} keeps reading for you. Anything new, changed or gone is handed in for {assistant} to look at. | The places {assistant} checks for changes. New, changed or removed material goes to {assistant}. | Shorter |
| sources.empty | No sources are set up yet. A source says what {assistant} keeps reading for you, such as a calendar, a mailbox, a folder or a feed. Use Add a source to start. | No sources yet. Add a mailbox, calendar, folder or feed for {assistant} to check. | Shorter |
| sources.items.other | {n} items | If positive: “{n} items” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| sources.last.counts | {new} new, {changed} changed, {gone} gone | {new} new, {changed} changed, {gone} gone | Zero count (conditional): omit zero-valued segments when composing this line |
| sources.last.baseline | First read: noted what is there | First check complete; existing items noted | Internal term |
| sources.last.offline | Not read: no network | Not checked: no internet connection | Technical |
| sources.failures | Failed {n} times in a row | If positive: “Failed {n} times in a row” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| sources.read_offline | {label} wasn't read: there is no network connection. It is tried again by itself. | {label} couldn't be checked without an internet connection. It will retry automatically. | Technical; shorter |
| sources.first_read_noted | Items already there are noted, not handed in. New ones go to the assistant. To hand in what arrived or changed in the last day, choose Look at the last day in its menu. | Existing items aren't sent to the assistant. New items are. Choose Look at the last day to include recent arrivals and changes. | Internal term; shorter |
| sources.kinds_none | No kind of source is available yet. Turn on an add-on that reads a calendar, mail or another place, then sign in to it. | Turn on a mail or calendar add-on, then sign in to add a source. | Shorter; action first |
| sources.field.label_hint | What to call it in lists. Leave it empty to use the name of the kind. | Leave empty to use the source type's name. | Shorter |
| sources.field.author_hint | Leave it empty when the changes come from different people. Choose yourself for a place you write in, so your own edits are never treated as news from someone else. | Choose yourself for your own writing. Leave empty if several people make changes. | Shorter |
| sources.closed.title | Auto-closed | Set aside by rules | Internal term; consistent name |
| sources.closed.intro | Changes a rule set aside without {assistant} reading them. Take a closer look hands one in after all. | Rules set these changes aside before {assistant} read them. Choose Take a closer look to have one read. | Internal term; shorter |
| sources.closed.change.removed | Gone | Removed | Consistent name |
| setaside.intro | Mail that is not work, kept away from {assistant}. This is work hands a message in after all. Confirm teaches the sorting and deletes the copy here; your mailbox keeps the message. | Mail kept away from {assistant}. Choose This is work to have it read. Confirm the sorting to teach the app and remove its copy here; the original stays in your mailbox. | Shorter |
| setaside.work | This is work | Treat as work | Action first |
| setaside.work_named | This is work: {title} | Treat as work: {title} | Action first |
| setaside.deleted.other | {n} set-aside messages were deleted from here after you confirmed them. | If positive: “{n} set-aside messages were deleted from here after you confirmed them.” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| setaside.always_sender | Always for this sender | Apply to this sender | Action first |
| setaside.always_domain | Always for this domain | Apply to this email domain | Action first; technical term needs context |
| setaside.always_domain_named | Always for {domain} | Apply to {domain} | Action first |
| setaside.confirmed_senders.other | From now on, mail from {n} senders is set aside as {what}. | If positive: “From now on, mail from {n} senders is set aside as {what}.” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| setaside.confirmed_none.one | 1 message confirmed. It is deleted from here shortly. | Confirmed 1 message. Its copy here will be deleted shortly. | Shorter |
| setaside.confirmed_none.other | {n} messages confirmed. They are deleted from here shortly. | If positive: “Confirmed {n} messages. Their copies here will be deleted shortly.” Otherwise, hide this count or use the existing empty state. | Shorter; Zero count (conditional): confirm caller hides or replaces this at zero |
| ask.hint | {assistant} answers from your records and the user guide. Anything it suggests changing waits for you. | {assistant} uses your saved information and the guide. Suggested changes need your approval. | Internal term; shorter |
| ask.state.review | Ready for your look | Ready to review | Shorter |
| ask.apply | Apply | Make this change | Vague action |
| ask.apply_named | Apply: {label} | Make this change: {label} | Vague action |
| ask.proposal.applied | Applied | Changed | Internal term |
| app.name | PM Cockpit | Thimbleby | Internal name; inconsistent product name |
| demo.region | Demo workspace | Demo work | Internal term: workspace |
| feedback.open | Send feedback | Write feedback | Action describes what the person does |
| feedback.title | Send feedback | Write feedback | Action describes what the person does |
| feedback.message_hint | This app sends nothing. You send the message yourself. | Copy your message or open it in your email app, then send it yourself. | Shorter; concrete action |
| feedback.preview | What will go | Message preview | Internal wording |
| feedback.mail | Open in your mail | Open in your email app | Consistent name |
| feedback.screen.record | A record page | An item page | Internal term |
| ask.mail | Open in your mail | Open in your email app | Consistent name |
| ask.mail_named | Open in your mail: {title} | Open in your email app: {title} | Consistent name |
| settings.open_addons | Add-ons | Open Add-ons | Action first |
| dataform.intro | Some add-ons keep files you can change, such as templates or lists. Open one to change it as a form. Your changes go in your own copy; the one that comes with the add-on is never touched. | Edit an add-on's templates or lists here. Changes are saved in your copy; the supplied files stay unchanged. | Shorter |
| dataform.new | New file | Create a file | Action first |
| dataform.new_named | New file for {label} | Create a file for {label} | Action first |
| dataform.new_form | New file | Create a file | Action first |
| dataform.name_hint | Lowercase letters, digits, - or _. The file ending is added for you. | Use lowercase letters, numbers, dashes or underscores. The file ending is added automatically. | Technical symbols |
| dataform.name_bad | Use lowercase letters, digits, - or _, and start with a letter or digit. | Start with a letter or number. Use lowercase letters, numbers, dashes or underscores. | Technical symbols |
| dataform.start | Start from the defaults | Start with the supplied settings | Internal term |
| dataform.new_title | New file {file} | Create file {file} | Action first |
| dataform.saves_workspace | Saving writes your own copy. The one that comes with the add-on stays as it is. | Saves your own copy without changing the supplied file. | Shorter |
| dataform.saves_project | Saving writes a copy for this project only. | Saves a copy for this project only. | Shorter |
| dataform.problem | Doesn't fit the form: {problem} | Can't use these details: {problem} | Internal term |
| dataform.problem_form | The copy in use doesn't fit the form, so the defaults are shown. Saving replaces it. ({problem}) | Your copy couldn't be shown. The supplied settings are shown instead; saving will replace your copy. ({problem}) | Internal term; shorter |
| addons.intro | Packs add a whole kind of work to the app. Look at what one adds, reaches and keeps first. Installing one from the list happens here, after you have looked. The app never takes payment. | Add-ons let the assistant do more. Review what each one adds, accesses and stores before installing it. Payment is handled outside the app. | Consistent name; shorter |
| addons.off | The catalog is off in this workspace's settings. | The add-on catalog is turned off in Settings. | Internal term; shorter |
| addons.no_catalog | This copy of the app doesn't list a catalog. Packs you install still show under Installed. | No add-on catalog is connected. Installed add-ons still appear under Installed. | Consistent name; shorter |
| addons.no_packs | No packs are listed yet. | No add-ons are listed yet. | Consistent name |
| addons.no_packs_failed | The catalog couldn't be read, so no packs are listed. The reason is below; refresh it once that is fixed. | The catalog couldn't be read: no add-ons are listed. Check the reason below, then refresh. | Consistent name; shorter |
| addons.by_maintainers | Made by the app's maintainers | Made by the app's developers | Internal term |
| addons.third_party | Third party | Made by someone else | Technical term |
| addons.adds.item_types | Item types: {types} | Kinds of items: {types} | Internal term |
| addons.adds.screens.other | {n} screens | If positive: “{n} screens” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| addons.adds.today.one | {n} kind of line on Today | {n} kind of item on Today | Internal term |
| addons.adds.today.other | {n} kinds of lines on Today | If positive: “{n} kinds of items on Today” Otherwise, hide this count or use the existing empty state. | Internal term; Zero count (conditional): confirm caller hides or replaces this at zero |
| addons.adds.ai_work.other | {n} kinds of AI work | If positive: “{n} kinds of AI work” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| addons.adds.actions.other | {n} actions | If positive: “{n} actions” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| addons.adds.setup_steps.other | {n} setup steps | If positive: “{n} setup steps” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| addons.adds.sources.other | {n} places it keeps reading | If positive: “{n} places it keeps reading” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| addons.reaches | Reaches | What it can access | Internal metaphor |
| addons.reaches.hosts | Internet: {hosts} | Websites: {hosts} | Technical term |
| addons.reaches.keys | Keys you provide: {n} | If positive: “Access keys you provide: {n}” Otherwise, hide this count or use the existing empty state. | Technical term; Zero count (conditional): confirm caller hides or replaces this at zero |
| addons.keeps | Keeps | What it stores | Plain words |
| addons.keeps.restricted | May hold private material. It goes only to AI accounts you allow for private material. | May store private material; only approved AI accounts can read it. | Shorter |
| addons.cost.size | {label}: about {size} words of AI work (an estimate) | {label}: about {size} words to process | Shorter |
| addons.installed_note | {name} is installed. It is ready after a restart. Then turn it on. | {name} is installed. Restart, then turn it on. | Action first in instruction; shorter |
| addons.removed_note | {name} is removed. The app lets go of it after a restart. | {name} is removed. Restart to finish. | Internal metaphor; shorter |
| addons.install_check | This text comes from the publisher, not from the app. Read it before you run anything. | Read these publisher instructions before running anything. | Shorter; preserve attribution |
| addons.demo_intro | To try it on made-up data first: | Try it with sample data first: | Action first; shorter |
| addons.demo_command | cockpit demo --plugin {id} | cockpit demo --plugin {id} | Technical; keep exact command until implementation is checked; offer a Try sample data action |
| addons.catalog_address_hint | The address of a catalog file, starting with https://. Whoever gave you the add-on can tell you. | Ask the add-on's publisher for the catalog's secure web address. | Technical term |
| addons.token.add | Add a read token | Add a download access key | Technical term |
| addons.token.add_named | Add a read token for {name} | Add a download access key for {name} | Technical term |
| addons.token.title | A read token for {host} | Download access key for {host} | Technical term |
| addons.token.intro | This add-on's files are kept privately at {host}. Give a token that can read them. It needs read access only to where the add-on's files are kept, and it is sent only to {host}. | Enter a read-only access key for the add-on's private files at {host}. It is sent only to {host}. | Technical; shorter |
| addons.token.label | Read token | Download access key | Technical term |
| addons.token.save | Save token | Save access key | Consistent name |
| addons.token.saved | Saved the read token for {host}. | Saved the download access key for {host}. | Consistent name |
| addons.token.saved_note | The read token is saved. Press Install to try again. | Access key saved. Choose Install to retry. | Consistent name; shorter |
| addons.feed.notes.other | {n} notes | If positive: “{n} notes” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| today.agenda.count.other | {n} events today | If positive: “{n} events today” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| today.todo.count.other | {n} things to do | If positive: “{n} things to do” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| today.needs.count.other | {n} things need you | If positive: “{n} things need you” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| today.arrived.count.other | {n} messages | If positive: “{n} messages” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| today.arrived.closed | {n} closed by your rules | If positive: “{n} closed by your rules” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| today.arrived.set_aside | {n} set aside | If positive: “{n} set aside” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| today.arrived.check_new.other | {n} new items | If positive: “{n} new items” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| today.arrived.check_failed.other | {n} sources couldn't be read: see Sources | If positive: “{n} sources couldn't be read: see Sources” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| today.arrived.check_busy.other | {n} sources were already being read | If positive: “{n} sources were already being read” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| lists.add_to | Add a value to {list} | Add a choice to {list} | Internal term |
| lists.add_placeholder | New value | New choice | Internal term |
| lists.intro | A list holds the choices a dropdown offers, such as a project's status. Changes take effect at once and can be undone. | Lists provide choices such as project status. Changes apply immediately and can be undone. | Technical; shorter |
| lists.values_of | Values in {list} | Choices in {list} | Internal term |
| lists.retired | No longer offered ({n}) | If positive: “No longer offered ({n})” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| lists.retired_hint | Records that already hold one of these keep it. | Existing items keep their current choices. | Internal term |
| setup.no_organizations | No organizations yet. Add the ones your people work for. | No organizations yet. Add the ones your contacts work for. | Plain words |
| setup.org_people.other | {n} people | If positive: “{n} people” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| setup.org_remove_blocked | People still work for it. Change their organization first. | Change the organization for its remaining contacts before removing it. | Action first; shorter |
| settings.changed_in_addon | This add-on's setting is changed outside this screen. | Change this setting outside this screen. | Action first; shorter |
| restart.for_more | {list} and {n} more | If positive: “{list} and {n} more” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| setup_step.addons.explanation | Add-ons connect the assistant to your mail, calendar and other tools. Turn on the ones you installed, then sign in to them. | Turn on installed add-ons, then sign in to connect your mail, calendar and other tools. | Shorter; action first |
| sign_in.none | Sign-ins appear here once an add-on that signs in (mail, calendar) is turned on. | Turn on a mail or calendar add-on to see its sign-in options. | Shorter; action first |
| ai_accounts.key_missing | Key not found: {where} | Access key not found: {where} | Technical term: access key |
| ai_accounts.key_missing_plain | Key not found on this computer | Access key not found on this computer | Technical term: access key |
| nav.records | Records | Saved items | Internal term |
| nav.outgoing | Waiting to go out | Drafts to approve | Shorter; consistent name |
| nav.styleguide | Style guide | Style examples | Technical term |
| nav.collapse | Collapse the sidebar | Hide the side menu | Technical term |
| nav.expand | Pin the sidebar open | Keep the side menu open | Technical term |
| outgoing.empty | Nothing waiting to go out. Drafts appear here for your approval. | No drafts waiting for approval. | Shorter; consistent name |
| user.open | Appearance, {name} | Change appearance, {name} | Action first |
| user.theme.system | System | Match this computer | Technical term |
| user.density | Density | Spacing | Technical term |
| status.chip_named | Status: {state} | App status: {state} | Internal label needs context |
| status.chip_live | Live | Connected | Technical term |
| status.chip_network | Waiting for the network | Waiting for an internet connection | Technical term |
| status.chip_spend | Spend near limit | Spending near limit | Plain words |
| status.network | Network | Internet connection | Technical term |
| status.network_waiting.other | {n} requests have been waiting for the network since {time}. | If positive: “{n} requests have been waiting for the network since {time}.” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| status.network_todo | They run again by themselves as soon as the network is back. Nothing is lost and no try is used up. | Work resumes when your internet connection returns. Nothing is lost, and retry attempts aren't used up. | Technical; shorter |
| status.assistant_open | Open the AI step | Open AI account setup | Internal navigation term |
| status.spend | AI spend | AI spending | Consistent name |
| alive.last_run | last run {time} | last task {time} | Internal term |
| alive.no_runs | no runs yet | no tasks yet | Internal term |
| alive.say.run_failed | last run failed {time} | last task failed {time} | Internal term |
| alive.say.network | waiting for the network | waiting for an internet connection | Technical term |
| alive.runs | Runs today | AI tasks today | Internal term |
| alive.runs_none | No runs yet today. | No AI tasks today. | Internal term |
| alive.runs_row.one | {account}: 1 run{failed} | {account}: 1 task{failed} | Internal term |
| alive.runs_row.other | {account}: {n} runs{failed} | If positive: “{account}: {n} tasks{failed}” Otherwise, hide this count or use the existing empty state. | Internal term; Zero count (conditional): confirm caller hides or replaces this at zero |
| alive.runs_failed | , {failed} failed | , {failed} failed | Zero count (conditional): omit zero-valued segments when composing this line |
| alive.queue_some.other | {n} requests, the oldest waiting since {time} | If positive: “{n} requests, the oldest waiting since {time}” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| alive.chains | If an account can't serve, the assistant tries | If an account can't respond, try | Internal term |
| alive.open | Open the AI step | Open AI account setup | Internal navigation term |
| styleguide.title | Style guide | Style examples | Technical term |
| styleguide.type | Type scale | Text sizes | Technical term |
| styleguide.type_note | One family, six sizes and three weights. | One font, six sizes and three weights. | Technical term |
| styleguide.sample_text | Needs you: answer one decision | Needs you: make one decision | Wrong action verb |
| styleguide.colors | Color roles | Color uses | Technical term |
| styleguide.colors_note | Every role has a name; status always comes with a word. | Name each color's purpose and pair every status with a word. | Technical term; shorter |
| styleguide.role.canvas | The page behind the panes | Page background | Technical term; shorter |
| styleguide.role.surface | Panes, the header, the sidebar and inputs | Panels, header, side menu and form fields | Technical term |
| styleguide.role.sunk | Quoted sources, code and expanded detail | Quotes, code and expanded details | Technical term |
| styleguide.role.accent | The one primary action | Main action | Technical term; shorter |
| styleguide.role.accent_soft | Selected rows and the current view | Selected items and current page | Technical term |
| styleguide.role.ok | Done, healthy, setup progress | Done, working, setup progress | Internal metaphor |
| styleguide.role.mark | The evidence highlight in a source | Highlighted evidence in the original text | Technical term |
| styleguide.buttons_note | One primary per row or region. A disabled button says why. | Use one main button per section. Explain why any button is unavailable. | Technical term |
| styleguide.primary | Primary | Main button | Technical term |
| styleguide.secondary | Secondary | Other button | Technical term |
| styleguide.ghost | Ghost | Button without a border | Technical term |
| styleguide.pills | Pills and the status chip | Status labels | Technical term |
| styleguide.pills_note | Pills show exceptions, never defaults, and always a word. | Use status labels for exceptions, with words as well as color. | Technical term |
| styleguide.chip_live | Live | Connected | Technical term |
| styleguide.row_title | Look over 3 actions the assistant added | Review 3 to-dos the assistant added | Consistent name |
| styleguide.row_meta | Check-in notes · 3 actions, 1 waits for you | Check-in notes · 3 to-dos, 1 needs your approval | Consistent name |
| styleguide.row_primary | All looks good | Approve | Action first; Action first; consistent name: approval |
| styleguide.row_long | A row title that is long enough to run past one line, so it shows how a title wraps and then stops at two lines with the rest on expand, never pushing the actions off the row | Show a long title on two lines, with the rest available when opened. Keep its buttons visible. | Technical; shorter |
| styleguide.row_expanded | Expanded content indents to the title column. | Align expanded details with the title. | Technical; shorter |
| styleguide.segmented | Segmented control | View choices | Technical term |
| styleguide.states_note | One sentence and one button; rows in the row's shape while loading; the raw detail behind Details. | Use one sentence and one button. While loading, show placeholder rows. Put error details under Details. | Technical; shorter |
| styleguide.empty_text | Nothing waiting to go out. Drafts appear here for your approval. | No drafts waiting for approval. | Shorter; consistent name |
| styleguide.empty_inline | Empty, in a rail pane | Empty side panel | Technical term |
| styleguide.failed_detail | The server answered with an error. | The app received an error. | Technical term |
| styleguide.floating | Drawer, dialog, menu and toast | Panels, pop-ups, menus and notifications | Technical term |
| styleguide.floating_note | Only floating things have shadows. Escape closes each, and focus returns to what opened it. | Use shadows only on these panels. Escape closes them and returns the selection to the opening button. | Technical term |
| styleguide.open_drawer | Open a drawer | Open a side panel | Technical term |
| styleguide.open_dialog | Open a dialog | Open a pop-up | Technical term |
| styleguide.show_toast | Show a toast | Show a notification | Technical term |
| styleguide.drawer_hint | Type something, then press Escape: the drawer asks before it discards. | Type something, then press Escape. The panel asks before discarding your text. | Technical term |
| styleguide.dialog_text | A dialog is only for a confirm that can't be undone. | Ask for confirmation before an action that can't be undone. | Technical; shorter |
| styleguide.forms | Form controls | Forms | Technical term |
| styleguide.forms_note | Control borders are at least 3:1 against their surface. | Keep form borders visible with a contrast ratio of at least 3:1. | Technical term needs context |
| styleguide.field_disabled | Workspace | Your work | Internal term |
| styleguide.evidence_note | The assistant's work looks like evidence: a quote, a source, a highlight that is marked and underlined. | Show the assistant's evidence as a quote with its source and an underlined highlight. | Shorter |
| styleguide.outside | From outside · not instructions | Someone else's material · not instructions | Internal term; consistent name |
| styleguide.icons_note | One line-icon set, drawn in the text color. Icons never carry status alone. | Use one set of outlined icons in the text color. Always pair status icons with words. | Technical term; shorter |
| setup_step.mail.explanation | The assistant reads your mail and calendar so you don't have to hand things in. It only reads; it never sends, moves or deletes anything. | Connect your mail and calendar for reading only. The assistant never sends, moves or deletes anything. | Shorter; this read-only claim needs a product behavior check |
| walkthrough.title | Set up your workspace | Set up your assistant | Internal term |
| walkthrough.intro | About 10 minutes. Nothing is spent until you press Go at the end. | Allow about 10 minutes. Nothing is spent until you approve the assistant's work. | Consistent name |
| walkthrough.why.you | Your name and time zone are used when the assistant writes dates and addresses people. Saving your name makes your own record in People, so nothing waits to know who you are. | Your name and time zone help the assistant address people and write dates. Saving adds you to People. | Shorter; internal term |
| walkthrough.why.ai | The assistant needs an AI account to read what you hand in. You choose which material it may see and how much it may spend. | Connect an AI account. Choose what it may read and how much it may spend. | Shorter |
| walkthrough.why.mail | Connect your mail and calendar and the assistant reads them for you. It only reads. The last day of your mail waits for your first Go, so nothing is spent yet. | Connect your mail and calendar for reading only. Reading the last day's mail starts after your approval. | Shorter; consistent name |
| walkthrough.why.backup | A backup is a copy of your work in a folder outside this workspace, such as one a cloud drive keeps. The folder is checked before it is saved. | Choose a backup folder outside your work's folder, such as a cloud drive. The app checks it before saving. | Internal term; shorter |
| walkthrough.why.people | Add the people you work with, so actions can name an owner. You can skip this: names the assistant can't place become questions for you to answer. | Add contacts so to-dos can be assigned. You can skip this and identify unfamiliar names later. | Shorter; consistent name |
| walkthrough.why.done | Here is what is set up and what you skipped. When you press the button, Today shows one line to start the assistant. Nothing is spent until you press Go on it. | Review your setup. On Today, approve the first work before anything is spent. | Shorter; consistent name |
| walkthrough.done.next | On Today, one line starts the assistant on your first items and says about what they cost. Hand something in is there too. | On Today, review the estimated cost and approve the first items. You can also add material there. | Shorter; internal term |
| walkthrough.extras.why | None of these is needed to start. Do them now, or any time later from Settings. | Set these up now or later in Settings. | Shorter |
| walkthrough.mail.none | No mail or calendar service is listed yet. You can still connect a mail folder or a calendar address below. | No services listed. Connect a mail folder or private calendar address below. | Shorter |
| walkthrough.mail.load_failed | The list of services didn't load. You can still connect a mail folder or a calendar address below. | Services couldn't be listed. Connect a mail folder or private calendar address below. | Shorter |
| walkthrough.mail.reaches | What it reaches | What it can access | Consistent name |
| walkthrough.mail.reaches.hosts | Talks over the internet to: {hosts} | Connects to: {hosts} | Technical term |
| walkthrough.mail.reaches.keys.other | Needs {n} keys from you | If positive: “Needs {n} keys from you” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| walkthrough.mail.restart_why | The app restarts once to bring the new add-on in. It takes a few seconds, and this step is waiting when it is back. | Restart to finish adding the add-on. Setup resumes here in a few seconds. | Action first; shorter |
| walkthrough.mail.restart_manual | The app can't restart itself here. Close it and start it again to bring the new add-on in; this step is waiting when it is back. | Close and reopen the app to finish adding the add-on. Setup resumes here. | Action first; shorter |
| walkthrough.mail.other_hint | Another mail service: a mail folder on any mail server. Another calendar: its private address. | Connect another service using a mail server folder or a private calendar address. | Technical; shorter |
| walkthrough.mail.first_go | The last day of your mail waits for your first Go. Nothing is spent until you press it. | Approve reading the last day's mail before anything is spent. | Consistent name; shorter |
| walkthrough.mail.sorting_hint | A small run reads only each message's sender, subject and category, never the message itself, and sets aside what is personal or a promotion. When it isn't sure, the mail stays with your work. | The assistant checks each sender, subject and category, not the message body, to set aside personal mail and promotions. Uncertain messages stay with your work. | Internal term; shorter |
| welcome.spend.intro | These start low. The assistant asks you first above one amount and stops for the day at the other. You can change them any time in Settings. | Choose when the assistant must ask before spending and its daily spending limit. Change either later in Settings. | Shorter |
| welcome.spend.confirm | Ask me first when a run may cost more than (USD) | Ask before an AI task costs more than (USD) | Internal term |
| welcome.spend.confirm_hint | Starts at {amount}. Cheaper runs start on their own once you have pressed Go the first time. | Starts at {amount}. After your first approval, cheaper tasks start automatically. | Internal term; shorter |
| welcome.spend.day_hint | Starts at {amount}. New runs stop for the day above it. | Starts at {amount}. New AI tasks stop when the daily limit is reached. | Internal term |
| knowledge.intro | What {assistant} has learned and the standing rules it follows. Nothing guides its work until you keep it. | What {assistant} has learned and the rules it follows. Review and keep each before it is used. | Shorter |
| knowledge.filter.retired | Retired | No longer used | Consistent name: Stop using |
| knowledge.filter.count | {label} ({n}) | If positive: “{label} ({n})” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| knowledge.kind.routing_entry | Routing | Who answers what | Internal term; consistent name |
| knowledge.empty.proposed | Nothing is waiting for you. What {assistant} learns shows here first. | Nothing to review. New learning from {assistant} appears here first. | Shorter |
| knowledge.empty.active | Nothing is active yet. Keep what {assistant} learns and it shows here. | Nothing kept yet. Keep what {assistant} learns to use it. | Shorter |
| knowledge.empty.retired | Nothing has been retired. | No saved learning has been stopped. | Internal term; align with Stop using |
| knowledge.from.input | Learned from something that came in | Learned from incoming material | Shorter |
| knowledge.from.seed | A starting entry | Included at setup | Internal term |
| knowledge.status.retired | Retired | No longer used | Consistent name: Stop using |
| knowledge.status.expired | Expired unreviewed | Expired before review | Internal term |
| knowledge.outside | From outside | From someone else's material | Internal term; consistent name |
| knowledge.enforced | A check enforces it | Checked automatically | Technical term |
| knowledge.used.other | Used {n} times · last {when} | If positive: “Used {n} times · last {when}” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| knowledge.ago.unknown | a while ago | date unknown | Internal fallback: do not imply a known age |
| knowledge.reach.records | for some kinds of items only | for selected kinds of items | Internal term; shorter |
| knowledge.narrow | Narrow | Limit where this applies | Internal term |
| knowledge.narrow_named | Narrow: {text} | Limit where this applies: {text} | Internal term |
| knowledge.retire | Retire | Stop using | Internal term |
| knowledge.toast.retired | Retired. It no longer guides {assistant}'s work. | No longer used by {assistant}. | Internal term; shorter |
| knowledge.toast.narrowed | Narrowed. | Updated where this applies. | Internal term |
| knowledge.narrow.title | Narrow what this applies to | Choose where this applies | Internal term |
| knowledge.narrow.save | Narrow | Save limits | Internal term |
| knowledge.review.one | 1 rule was given to {assistant} and never applied. Look it over. | Review 1 rule {assistant} hasn't used. | Action first; shorter |
| knowledge.review.other | {n} rules were given to {assistant} and never applied. Look them over. | If positive: “Review {n} rules {assistant} hasn't used.” Otherwise, hide this count or use the existing empty state. | Action first; shorter; Zero count (conditional): confirm caller hides or replaces this at zero |
| knowledge.review.moved | Some rules moved out of the part sent every time. Look them over. | Review rules now sent only when relevant. | Internal term; action first |
| rules_review.intro | {assistant} was given these rules and none of them showed in its work in the last {days} days. Keep one to look at it again later, narrow it to where it applies, or retire it. | {assistant} received these rules but hasn't used them in {days} days. Keep them for later review, limit where they apply, or stop using them. | Internal term; shorter |
| rules_review.size | Sent with every run: {size} of {budget} characters of rules, lessons and terms. | Instructions sent with every task: {size} of {budget} characters. | Internal term; shorter |
| rules_review.moved.one | 1 rule moved out of the part sent every time. It goes only with the runs it covers. | 1 rule is now sent only for relevant tasks. | Internal term; shorter |
| rules_review.moved.other | {n} rules moved out of the part sent every time. They go only with the runs they cover. | If positive: “{n} rules are now sent only for relevant tasks.” Otherwise, hide this count or use the existing empty state. | Internal term; shorter; Zero count (conditional): confirm caller hides or replaces this at zero |
| rules_review.counts.one | Given to 1 run, never applied | Sent for 1 task, never used | Internal term |
| rules_review.counts.other | Given to {n} runs, never applied | If positive: “Sent for {n} tasks, never used” Otherwise, hide this count or use the existing empty state. | Internal term; Zero count (conditional): confirm caller hides or replaces this at zero |
| rules_review.kept | Kept. Its next review starts now. | Kept for later review. | Shorter |
| settings.rules_link | The rules {assistant} learns, and what you've kept, are on the Knowledge screen. | Review what {assistant} has learned and your saved rules in Knowledge. | Shorter |
| queue.extractor.sub | Files of this kind that come in aren't being read, so nothing in them reaches the assistant. This line goes once a file of this kind reads well. | The assistant can't read these files. This notice clears after one is read successfully. | Internal term; shorter |
| queue.account_check.sub | It is a backup for that work and hasn't passed the connection check for it yet. A backup nobody checked could fail just when it is needed. | Test this backup account before it handles the work. | Shorter; action first |
| queue.account_check.sub_failed | Its last check didn't pass. Check it again once it is fixed, or take it out of the backups in Settings. | Fix the account and test again, or remove it as a backup in Settings. | Shorter; action first |
| queue.switch_failed.label | Switch check | Review account change | Internal term; action first |
| queue.switch_failed.sub.one | The check after the switch found 1 case that didn't come out right: | The account-change test found 1 failed case: | Internal term; shorter; do not infer that every failure was an incorrect answer |
| queue.switch_failed.sub.other | The check after the switch found {n} cases that didn't come out right. The first: | If positive: “The account-change test found {n} failed cases. First:” Otherwise, hide this count or use the existing empty state. | Internal term; shorter; do not infer that every failure was an incorrect answer; Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.switch_failed.sub_unfinished | The check after the switch couldn't finish, so nothing shows the new choice works well. | The test couldn't finish. The new account's performance is unknown. | Shorter |
| queue.catch_up_go.label | Go needed | Needs your approval | Consistent name |
| queue.catch_up_go.priced.other | Learn from {n} kinds of earlier correction: {cost} | If positive: “Learn from {n} kinds of earlier correction: {cost}” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.catch_up_go.mixed.one | Learn from 1 kind of earlier correction: {cost}, and some on your plan's allowance | Learn from 1 kind of earlier correction: {cost} plus some of your plan's allowance | Shorter |
| queue.catch_up_go.mixed.other | Learn from {n} kinds of earlier correction: {cost} for those with a price, and some on your plan's allowance | If positive: “Learn from {n} kinds of earlier correction: {cost} plus some of your plan's allowance” Otherwise, hide this count or use the existing empty state. | Shorter; Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.catch_up_go.unpriced.other | Learn from {n} kinds of earlier correction. They use your plan's allowance. | If positive: “Learn from {n} kinds of earlier correction. They use your plan's allowance.” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.catch_up_go.sub | These are corrections you made before the assistant could learn from them. Nothing is spent until you press Go. | Approve spending to learn from corrections made before learning was available. | Shorter; consistent name |
| queue.catch_up_go.run | Go | Approve | Action first; consistent name |
| queue.rule_review.one | Look over 1 rule that never applied in the last {days} days | Review 1 rule unused in the last {days} days | Shorter |
| queue.rule_review.other | Look over {n} rules that never applied in the last {days} days | If positive: “Review {n} rules unused in the last {days} days” Otherwise, hide this count or use the existing empty state. | Shorter; Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.rule_review.moved | Look over the rules: some moved out of the part sent every time | Review rules now sent only when relevant | Internal term |
| queue.rule_review.sub | They were given to {assistant} and never showed in its work. | {assistant} received these rules but hasn't used them. | Shorter |
| learned.from_outside | From outside | From someone else's material | Internal term; consistent name |
| learned.said_just_this_time.one | You said “just this time” to this once before. | You previously chose “Just this time” once. | Shorter |
| learned.said_just_this_time.other | You said “just this time” to this {n} times before. | If positive: “You previously chose “Just this time” {n} times.” Otherwise, hide this count or use the existing empty state. | Shorter; Zero count (conditional): confirm caller hides or replaces this at zero |
| learned.from.input | From what came in | From incoming material | Internal term |
| toast.learned_kept_all.other | Kept {n} terms. {assistant} will use them from now on. | If positive: “Kept {n} terms. {assistant} will use them from now on.” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| learned.today.review.other | Review {n} things {assistant} learned | If positive: “Review {n} things {assistant} learned” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| learned.today.catch_up.other | Look over {n} things {assistant} learned from your earlier corrections | If positive: “Look over {n} things {assistant} learned from your earlier corrections” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| learned.today.from_inputs.other | {n} from what came in | If positive: “{n} from what came in” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| learned.today.from_corrections.other | {n} from your corrections | If positive: “{n} from your corrections” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| learned.today.expired.other | {n} from what came in expired before you looked | If positive: “{n} from what came in expired before you looked” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| learned.today.left_out.one | {n} more kind of correction didn't fit and has expired | {n} additional correction type exceeded the review limit and expired | Internal term; awkward phrasing; explain expiration in adjacent help |
| learned.today.left_out.other | {n} more kinds of correction didn't fit and have expired | If positive: “{n} additional correction types exceeded the review limit and expired” Otherwise, hide this count or use the existing empty state. | Internal term; awkward phrasing; explain expiration in adjacent help; Zero count (conditional): confirm caller hides or replaces this at zero |
| learned.review.empty | Nothing is waiting for you to look at. | Nothing to review. | Shorter |
| learned.keep_all.other | Keep all {n} terms | If positive: “Keep all {n} terms” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| learned.keep_all_hint | Only terms that come with the words they were taken from are kept together. | Keep terms together only when each includes its original wording. | Shorter |
| learned.catch_up.waiting.one | {n} kind of correction is still being looked at | Reviewing {n} kind of correction | Shorter |
| learned.catch_up.waiting.other | {n} kinds of correction are still being looked at | If positive: “Reviewing {n} kinds of correction” Otherwise, hide this count or use the existing empty state. | Shorter; Zero count (conditional): confirm caller hides or replaces this at zero |
| learned.catch_up.left_out.one | {n} more kind of correction didn't fit the list of {most} | {n} additional correction type is outside the {most}-item review limit | Internal term; shorter |
| learned.catch_up.left_out.other | {n} more kinds of correction didn't fit the list of {most} | If positive: “{n} additional correction types are outside the {most}-item review limit” Otherwise, hide this count or use the existing empty state. | Internal term; shorter; Zero count (conditional): confirm caller hides or replaces this at zero |
| question.sent | Already sent | Mark as already sent | Action first |
| because.first_run | First run on {account} | First task using {account} | Internal term |
| because.leave_out | Stop it applying to | Stop using this for | Internal term |
| because.only_retire | It applies to one project only, so the way to stop it is to retire it. | This applies to just one project. Stop using it to remove it there. | Internal term; shorter |
| because.retire | Retire it | Stop using it | Internal term |
| because.narrow | Narrow it | Limit where it applies | Internal term |
| toast.narrowed | Narrowed. It no longer applies there. | Updated. It no longer applies there. | Internal term |
| toast.retired | Retired. It won't guide the assistant any more. | No longer used by the assistant. | Internal term; shorter |
| queue.empty | Nothing needs you right now. New things appear here as they come in. | Nothing needs you right now. | Shorter |
| queue.new_show.one | 1 new · Show | Show 1 new item | Action first |
| queue.new_show.other | {n} new · Show | If positive: “Show {n} new items” Otherwise, hide this count or use the existing empty state. | Action first; Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.untrusted | From outside | From someone else's material | Internal term; consistent name |
| queue.detail.gone | This has been dealt with already. | Already dealt with. | Shorter |
| queue.inspector.empty | Pick a line to see its items here. | Choose an item to see its details. | Internal term |
| queue.title.calendar | Calendar entry from {who} | Calendar event from {who} | Consistent name: calendar event |
| queue.title.pasted | Text pasted in | Pasted text | Shorter |
| queue.pill.go | Needs your go | Needs your approval | Consistent name |
| queue.act.pick_owner | Pick an owner | Choose who's responsible | Internal term |
| queue.act.all_good | All looks good | Approve | Action first |
| queue.decision | Answer 1 decision | Make 1 decision | Wrong action verb |
| queue.who_is | Pick who “{name}” is | Identify “{name}” | Shorter |
| queue.owner | Pick an owner for “{text}” | Choose who's responsible for “{text}” | Internal term |
| queue.held | Decide on a change that is waiting for you | Review a waiting change | Shorter |
| queue.go | Give the go to {what} | Approve {what} | Shorter; consistent name |
| queue.overdue.other | Finish {n} overdue to-dos | If positive: “Finish {n} overdue to-dos” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.review.things.other | Look over {n} things {assistant} did | If positive: “Look over {n} things {assistant} did” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.review.actions_added.one | Look over 1 action {assistant} added | Look over 1 to-do {assistant} added | Consistent name: to-do |
| queue.review.actions_added.other | Look over {n} actions {assistant} added | If positive: “Look over {n} to-dos {assistant} added” Otherwise, hide this count or use the existing empty state. | Consistent name: to-do; Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.review.actions_closed.one | Look over 1 action {assistant} closed | Look over 1 to-do {assistant} closed | Consistent name: to-do |
| queue.review.actions_closed.other | Look over {n} actions {assistant} closed | If positive: “Look over {n} to-dos {assistant} closed” Otherwise, hide this count or use the existing empty state. | Consistent name: to-do; Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.review.questions.other | Look over {n} questions {assistant} wrote | If positive: “Look over {n} questions {assistant} wrote” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.review.notes.other | Look over {n} notes {assistant} filed | If positive: “Look over {n} notes {assistant} filed” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.review.recorded.other | Check {n} things {assistant} recorded | If positive: “Check {n} things {assistant} recorded” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.review.people.other | Look over {n} people {assistant} added | If positive: “Look over {n} people {assistant} added” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.review.projects.other | Look over {n} projects {assistant} added | If positive: “Look over {n} projects {assistant} added” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.review.drafts.other | Look over {n} drafts {assistant} wrote | If positive: “Look over {n} drafts {assistant} wrote” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.review.waits.other | {n} wait for you | If positive: “{n} wait for you” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.send.questions.other | Send {n} questions to {name} | If positive: “Send {n} questions to {name}” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.send.actions.one | Send 1 action item to {name} | Send 1 to-do to {name} | Consistent name: to-do |
| queue.send.actions.other | Send {n} action items to {name} | If positive: “Send {n} to-dos to {name}” Otherwise, hide this count or use the existing empty state. | Consistent name: to-do; Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.send.items.other | Send {n} items to {name} | If positive: “Send {n} items to {name}” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.send.n_questions.other | {n} questions | If positive: “{n} questions” Otherwise, hide this count or use the existing empty state. | Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.send.n_actions.one | 1 action item | 1 to-do | Consistent name: to-do |
| queue.send.n_actions.other | {n} action items | If positive: “{n} to-dos” Otherwise, hide this count or use the existing empty state. | Consistent name: to-do; Zero count (conditional): confirm caller hides or replaces this at zero |
| queue.nudge.meta.one | 1 thing sent, no reply yet · the longest {days} days | 1 item awaiting a reply · waiting up to {days} days | Shorter; keep item type unspecified |
| queue.nudge.meta.other | {n} things sent, no reply yet · the longest {days} days | If positive: “{n} items awaiting a reply · waiting up to {days} days” Otherwise, hide this count or use the existing empty state. | Shorter; keep item type unspecified; Zero count (conditional): confirm caller hides or replaces this at zero |
