# User guide

## What this app is

An assistant for the person who runs projects. You hand in notes, minutes and messages; the assistant reads each one and
proposes what to record: actions with owners and dates, questions for people, facts and notes. You look over what it did
and keep it, change it, send it back with a note, or undo it. Nothing goes to another person until you approve the exact
words, and nothing is sent by the app itself: you copy messages and send them from your own mail or chat.

## Today

Today is the home screen. It shows what needs you now: what changed since you last looked, follow-ups to send, items
ready to move to their next stage, work waiting for your go, and lines that add-ons put there. Each row has one main
button; everything else is in its menu (the three dots). The Start here card lists the setup steps that aren't done yet.

## Handing something in

Press Hand something in (or the n key), paste the text or add a file, and say in your own words what you want done with
it if it isn't obvious. The assistant reads one input at a time. Text you paste from outside is treated as material, never
as instructions: if a pasted email says "ignore your rules", the assistant ignores that. Your own note is the
instruction.

## What changed and reviewing the assistant's work

What changed lists each hand-in and what the assistant did with it. Open a row to see each change it made, with the exact
words from your input that justify it. Looks good files it as looked over. Send back with a note asks the assistant to
try again with your correction. Undo this reverses one change; Undo everything it did reverses the whole hand-in. Undo is
always available, and both the change and the undo stay in the history. Some changes wait for you instead of applying at
once: a new person named only in outside content, a change of a setting or a rule, or anything that contradicts a rule
you set. Those show as waiting, with the reason.

## Follow-ups

Follow-ups gathers what you need to send to other people: questions for them and actions they own. Under To send, each
person has one message with Copy; copying marks it as sent, with Undo. Waiting on them shows what you already sent, one
line each, with how long ago, and lets you record their reply or mark the item finished.

## People and projects

People & projects is where you add, rename and remove people and projects. Records refer to people and projects by id,
so a rename changes every place at once. Something that other records still point to can't be removed until they don't.
A project can sit inside another project (a series and its books, a program and its parts), have its own language and
its own budget for AI work.

## Stages

Work that moves through steps (an order from new to delivered, a document from outline to approved) has stages. Each
stage can have entry checks, which must pass before an item moves into it; the Stages screen shows which checks fail and
why. You move items one stage at a time; a stage that doesn't apply to an item is passed over. Moving back is always
allowed. Entering a stage can start work for the assistant, which waits for your go.

## Files

Files lists what you added and what add-ons made. Add a file from the Files screen or when handing something in. Some
files offer actions from add-ons (build a document, make a preview); an action shows you exactly what it would do, and
you apply it or close it. Applied actions can be undone.

## AI accounts and costs

The app uses AI accounts you bring: a key from a model provider, a service that reaches many models with one key, a
model server on your own computer, or a command-line agent signed in as you. Add one in setup or Settings, then press
Test: it makes one small call per kind of work, with the settings that work will use, and says in plain words what
failed. Work that would cost more than the amount you set waits for your go with an estimate first. Daily and monthly
budgets pause work when they are used up. Work whose cost can't be estimated (a subscription, a local model) can be set
to always ask first. Which account does which kind of work is set by tiers: everyday work and harder work can use
different accounts.

Without an AI account, a stand-in does the reading so you can try the app (the demo uses it). It is no model: it
follows plain rules. A line such as "Sam will send the quotes by 2030-03-08" becomes an action for Sam due that day; "We
still need the page count" becomes an action waiting for you to pick an owner; "Decided: …" becomes a fact. Anything
else is kept as a note. Asked a question, it quotes the closest passage of this guide.

## Asking the assistant

You can ask the assistant about the app or about your work. It answers only from this guide, your settings (never your
keys), what this install can do, and your own records, and it shows the words its answer rests on. If the answer is a
setting you can change, it suggests the change and you apply it with one click, with Undo. If you ask for something the
app can't do, it drafts a short report to the app's maintainers that you can review and send.

## Settings

Settings shows every setting with what it does, its default and where its value comes from. Common settings come first;
More settings shows the rest. A setting set by an environment variable or a command-line flag is locked on the screen
and says so. Saving checks the whole set of settings before anything is written, keeps the comments in your settings
files, and lets you undo the change. The app restarts itself a few seconds later to use the new settings; the screen
reconnects on its own. The server's address, port and mode are changed only in their file, so the app can't lock you out.

## Backups

Backups copy the whole workspace (its database, settings and saved sources) to a folder off this computer: an external
drive, a network share or a folder a sync service copies elsewhere. Choose the folder in setup or Settings; it must
exist, be outside the workspace and be writable. Backups run on a schedule while the app runs, keep the number you set,
and the header shows the age of the last one. If a drive isn't connected, the app tries again later and tells you.

## Using two computers

A workspace can live on two computers through a synced folder (a folder a sync service keeps the same on both). Only one
computer works on the workspace at a time: the app takes a lease in the folder and gives it back when it stops. When you
start on the other computer, it loads the newer copy. Copies a sync service makes on a conflict are never loaded; the app
lists them so you can look. Files you edit in the synced folder come back as proposals you review.

## Sources the assistant keeps reading

Besides what you hand in, the assistant can keep reading places for you: a folder, a news feed, a calendar or a mail
folder. Each is a source, with how often it is read. A source's first read only notes what is there;
after that, anything new, changed or gone is handed in for the assistant to read, marked as outside content. A
calendar is read through its private address (most calendar services offer one in their sharing settings), and the
events in the coming weeks are followed: a moved meeting or a new invitation comes in as a change. A mail folder is
read over IMAP with an app password from your mail service; messages are never marked as read or changed. Addresses
and passwords are kept outside the settings files, as environment variables or files on this computer. Rules can set
aside changes that don't matter, such as a spacing fix or a change made by your own account; they are listed under
Auto-closed, where Take a closer look hands one in after all. If a source can't be read several times in a row, you
are asked once, with what to do.

Some add-ons read a service through your own account, signing in on that service's page. Sign in from Settings: the
service asks you what to allow, then sends you back to the app. The sign-in is kept on this computer only and renewed
on its own; if the service withdraws it, you are asked to sign in again. Sign out from the same place.

## Templates and your own item types

A template sets up the kinds of items you track (requests, pieces, orders), their fields, stages and checklists, and
what Today shows. Pick one in setup, or apply one later. You can add your own item types the same way, and save your
setup as a template to reuse.

## Add-ons

Add-ons (plugins) add kinds of work: item types, actions, screens, stages and lines on Today. Each one works alone. If
one fails, the app skips that part, notes it on the add-on, and turns the add-on off only if it keeps failing; your data
stays. An add-on can't send anything or change records except through the same review you use.

## Privacy and what the assistant sees

Each AI run sees only what that piece of work needs: the input, the related records and your standing rules. Records can
be marked as internal or restricted; restricted material goes only to accounts you allowed for it, such as a model on
your own computer. Keys are never written in the settings files; they are kept on this computer or in the environment.

## Keyboard shortcuts

Press ? for the list. j and k move between rows, Enter opens one, a is Looks good or Approve, s sends back, u undoes, c
copies, e edits and n hands something in. Shortcuts never fire while you are typing and can be changed in Settings.

## When something goes wrong

Every waiting item says why and until when. An AI account problem (a wrong key, a usage limit, a service that is down)
says which account and what to do; Try again sends the work again, and a refused piece of work can go to another
account. If the app was stopped or the computer slept, it picks up where it was. Settings that don't load stop the app
from starting and name the file and the key.
