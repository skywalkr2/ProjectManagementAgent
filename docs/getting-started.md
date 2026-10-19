# Getting started

This page takes you from a computer with nothing on it to your first result: the assistant has read your mail and
turned it into actions and questions you can look over. It takes about 10 minutes of your time. The assistant spends nothing
on your own material until you press **Go** at the very end, and you see the estimate first. The one thing before that
which costs anything is the check of your AI account, which you start yourself and which shows its cost beforehand (in the walkthrough's AI account step).

You do three things in order: install the app, start your own workspace, and follow the setup walkthrough that opens by
itself.

## 1. Install

You need an AI account of your own with your AI service (a key for it, or a program on your computer that is already
signed in). The app does not come with one, and no AI service is chosen for you.

**From a package file** (no source code and no Node needed). Install **uv** first, the Python package tool; its own
documentation shows how, and it fetches the right Python for you. Then, in a terminal, in the folder where you saved the
package file and the install script for your computer:

```sh
sh install.sh pm_cockpit-<version>-py3-none-any.whl                                  # macOS, Linux
powershell -ExecutionPolicy Bypass -File install.ps1 pm_cockpit-<version>-py3-none-any.whl   # Windows
```

**From a checkout of the source.** You need Python 3.12 or newer with uv, and Node 22.12 or newer with npm:

```sh
uv sync
npm --prefix web ci && npm --prefix web run build
```

(`docs/install.md` has the details, updating, and restoring from a backup.) Installing costs nothing and changes nothing
outside the app's own folders.

## 2. Start your own workspace

A workspace is one folder that holds your work. Keep it in your home folder, not in a temporary folder: the system empties
temporary folders when the computer restarts, and your setup would go with them.

```sh
cockpit
```

That's the only command to remember. From a checkout, run `uv run cockpit` in its folder the first time; on macOS and
Linux that also makes `cockpit` work in any folder from then on. The first time, it makes your
workspace in a folder called `Cockpit` in your home folder and opens it in your browser, where the walkthrough starts.
Every time after, the same command reopens the workspace you used last. It runs on your own computer, reachable only
from it. If the browser doesn't open, copy the link it prints. Leave the terminal window open while you work: closing it
stops the app. To update later: `cockpit update`.

To keep a workspace somewhere else, or have more than one: `cockpit init <folder>`, then `cockpit serve -w <folder>`.
After that, `cockpit` alone reopens whichever you used last.

Nothing is spent so far, and nothing has left your computer.

## 3. The setup walkthrough

The first time you open a new workspace, the walkthrough opens by itself and says: *Set up your workspace. About 10
minutes. The assistant spends nothing on your own material until you press Go at the end.* It shows one screen at a time, in the order you need them.
Every screen says why it matters and can be skipped and done later. **Finish later** closes it; it then stays closed until
you open it again from the **Setup** line on Today, from **Help**, or from **Settings**. It remembers where you were, also
after a restart.

### You

Your name, the workspace's name and your time zone, in one form. Press **Save**. Your name makes your own record in
People, so the assistant knows who "me" is when it files an action.

*Cost: nothing.* *If it fails:* a message under the form says what was refused (for example a time zone it does not know);
fix that field and save again. What you typed stays in the form.

### Your AI account

Pick your AI service by name, make a key on that service's own page, paste it here, and press **Check**. The app asks the
service for the models it offers; pick one for everyday work and, if you like, a stronger one for harder work. Then choose
what the assistant may see. **Your notes, mail and meetings are internal material, so tick Internal**; a new account sees
only open material until you raise it. Press **Add account**, then **Test again**: the app sends one small test request
for each kind of work to check that the account answers.

**What it may spend** sits below the account: the amount above which the assistant asks you first (it starts at $0.10) and
the most it may spend in a day (it starts at $2.00). You can change both here or later in Settings.

Your key stays on this computer, in a private folder only you can read. The settings refer to it and never hold it.

*Cost: the test is the one thing in setup that spends money, and you start it.* It sends a few small requests to your AI
service, normally a fraction of a cent in all. The button shows the estimate when the app can work it out, and when you add an
account the app asks first if the estimate is above the amount you set under *What it may spend*. None of your own material is sent. Nothing
else is spent here.
*If it fails:* the test says in plain words what went wrong. The usual causes are a key copied only in part, a key that has
been switched off, an account with no credit, or a service that is busy; copy the key again, check the service's account
page, or try again in a minute. Press **Test again** after you change something.

### Mail and calendar

The assistant reads your mail and calendar so you do not have to hand things in one by one. It only reads: it never sends,
moves or deletes anything.

The screen lists the services you can connect.

- **A service that is not on this computer yet:** press **Install and connect**. The app installs it and turns it on.
- **A service that is installed but off:** press **Turn on**.
- **Then, once:** press **Restart to connect (a few seconds)**. The app restarts itself only when you press this button,
  and the walkthrough comes back at this screen. At most one restart is needed in the whole walkthrough, even if you
  connected more than one service first.
- **Then:** press **Sign in**. The service's own sign-in page opens in this tab; you sign in there and allow reading. You
  come back to this screen.

After you sign in, the screen lists what is now being read (your inbox and your main calendar). **What it holds waits for
your Start on the next screen**, so you see a result without a surprise on the bill. You can choose other folders or
calendars later from Sources.

If your mail service is not in the list, press **Another mail or calendar**. That opens Sources, where you can add a mail
folder from any mail server or a calendar's private address.

*Cost: nothing here.* Reading costs nothing; the AI only works on what was read after your Start.
*If it fails:*
- If the install is refused, the row shows the app's own words (a release that does not match its checksum, or one that
  cannot be reached). Try again, or press **How to get it** for the add-on's instructions.
- If the app says it cannot restart itself, close the terminal's program with Ctrl+C and run the same `cockpit serve`
  command again. The walkthrough opens at this screen.
- If the app does not come back within a minute, do the same.
- If signing in is refused, a message says so when you come back. Press **Sign in** again. If your service shows a warning
  page for this app, the screen says what that means for you.

### Your promises

This screen comes right after mail, before anything that asks about backups, people or projects. It offers **Look back over
the last 14 days of your own mail**, with the number of items and about what it would cost together, such as *12 items to
look over. About $0.30 in all.* Nothing is read by the assistant until you press **Start**.

After it has read them, the screen lists up to five open promises it found (who owes each to whom, the day, and the words
from your mail), and one follow-up message ready to copy: press **Copy message**, send it from your own mail, then press
**Mark sent**. If it found none, the screen says so, and **Missed one** lets you say in a sentence what it missed.

*Cost: the estimate on the screen, shown before you press Start.* On the built-in stand-in it is less than a cent.
*If it fails:* the screen says what to do first (choose an AI account, or connect mail) and takes you back to it.

### Backups

Choose a folder outside the workspace, such as one a cloud drive keeps, and press **Use this folder for backups**. The app
checks the folder first: it must be there, outside the workspace, and writable. Press **Check** to see it before you save.
The first backup is made on its own schedule, and the header shows its age once one has succeeded.

*Cost: nothing.* *If it fails:* the message says why the folder will not do (the drive is not connected, the folder is
inside the workspace, or the app cannot write in it). Choose another folder.

### People

Optional. Add the people you work with, so actions can name an owner. **Skipping is fine**: a name the assistant cannot
place becomes a question for you to answer, and you can add people at any time.

### Done

The last screen lists what was set up and what you skipped, each skipped item with a **Set up** button that takes you back
to it. Below that are optional extras for later: a starting template and other add-ons. None of them is needed to start.

Press **Go to Today**.

## Your first result

If you pressed **Start** on Your promises, your first result is already there. Otherwise Today shows one line: **Start the
assistant**, with how many items are waiting and about what they would cost together, such as *Start the assistant: 14
items, about $0.30*. Keyboard focus is on it when you arrive. Nothing has been sent to your AI service yet.

Press **Go** on that line. The assistant reads each item, one at a time, and files what it finds: actions with owners and
dates, questions, facts and notes, each with the words from your mail that justify it. Open **What changed** to look over
what it did. You can keep any change, change it, send it back with a note, or undo it. Nothing goes to another person
until you approve the exact words, and the app never sends anything by itself.

**What it costs:** the estimate on that line, shown before you press Go. After the first Go, the amount you set under
*What it may spend* applies: a run estimated above it asks you first, and a run below it starts on its own. The daily limit
stops new runs for the day.

You can also press **Hand something in** (or the `n` key) at any time to paste an email, minutes or a note.

## If you closed the walkthrough, or want to change something

- On Today, the **Setup** line shows how far you are and has **Continue setup**.
- **Help** has **Setup guide**, and **Settings** has **Open the setup guide**.
- Everything the walkthrough sets is also in **Settings**, **Sources**, **Add-ons** and **People & projects**.

## If something does not work

- **The page does not open:** copy the link `cockpit` printed into your browser. It only works on this computer.
- **The terminal says the workspace folder is not empty:** `cockpit init` makes a new folder; give it a path that does not
  exist yet.
- **Setup has a step that stays "Not done yet":** open that screen. It says what is missing, and the step is done once the
  workspace shows it.
- **You want to start over:** make a new workspace with `cockpit init` in another folder. The old one is untouched.
- **You want to try an add-on on made-up data first:** `cockpit demo` makes a sandbox of made-up people and projects. It is
  a place to try things, not a place to start your real work.
