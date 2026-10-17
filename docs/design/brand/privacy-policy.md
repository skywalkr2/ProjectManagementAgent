# Thimbleby privacy policy (draft, 2026-10-17)

Drafted with an outside assistant at the owner's request and checked against the code. It is a draft for the homepage
Google's verification asks for; have it read by someone qualified before it is published. Review changes from the draft:
- **Where credentials live:** the app keeps passwords, keys and sign-in tokens as files in the workspace's private folder,
  readable only by the person's user account (`engine/setup.py` `keep_secret`; sign-ins in `.cockpit/keys/`), not in the
  system's keychain. The text says so. Moving them to the macOS Keychain and Windows Credential Manager is a better
  default to consider in phase I.
- **What the app contacts besides the person's accounts:** the add-on catalog and, from phase I, the update feed. Those
  hosts see the computer's internet address, nothing else; the draft said nothing about them.
- **Add-ons are not catalog-only:** a person can also install an add-on file themselves (`cockpit install`), or keep one in
  the workspace's add-ons folder. The text says the catalog is the usual way.
- **The feedback button** opens an email the person writes and sends themselves.
- **Data folders** filled in from phase I's plan.

Placeholders left for the owner: the effective date, the developer's legal name and the contact address.

---

**Thimbleby Privacy Policy**

Effective date: [DATE] · Developer: [DEVELOPER'S LEGAL NAME] · Website: thimbleby.app · Privacy contact: [CONTACT EMAIL]

Thimbleby is a desktop daily assistant for Mac and Windows. Its helper, Reginald, helps you remember commitments, prepare
replies and follow-ups, and manage your calendar. This policy explains what information the app uses and where it goes.

**Your information stays under your control.** Thimbleby stores its data on your computer. We do not receive your mail,
calendar, notes, prompts, drafts or activity history. There are no analytics, advertising trackers or automatic usage
reports. Your mail and calendar providers keep holding the information in your accounts, and if you choose a hosted AI
service, that service processes the text sent to it, as explained below. "Stored on your computer" does not mean
information never leaves it.

**What Thimbleby accesses and stores.** You choose which accounts and sources to connect; Thimbleby reaches mail and
calendar through the provider's sign-in (OAuth) or, for a plain mailbox, IMAP. Depending on the features you use, it keeps:
account identifiers and connection settings; sign-in tokens, AI account keys and any mailbox password you provide;
messages and calendar details it read, and notes or files you add; commitments, dates, people details, summaries and links
to their sources; drafts, proposed calendar changes, your approvals and the history of what was done; your preferences,
corrections, add-ons and local diagnostic records.

The data is kept in your Application Support folder on macOS (`~/Library/Application Support/Thimbleby`) and in your
AppData folder on Windows (`%APPDATA%\Thimbleby`). Passwords, keys and sign-in tokens are kept as files in that folder's
private part, readable only by your user account. Backups and exports exist wherever you choose to save them; backups can
be encrypted.

**Your chosen AI service.** When Reginald works on something, Thimbleby sends the text needed for that task to the AI
service you selected, using your own account. This may include message text, calendar details, notes or related context.
That provider's terms, retention settings and processing locations apply; using your own account does not stop the
provider from receiving what is sent. If you choose a model that runs entirely on your computer, the text stays on your
computer. Thimbleby does not use your information to train AI models.

**Google information and Limited Use.** Thimbleby's use and transfer of information received from Google APIs adheres to
the Google API Services User Data Policy, including the Limited Use requirements. Google information, and anything derived
from it such as summaries, is used only to provide the features you choose: finding commitments, preparing drafts and
carrying out the actions you approve. We do not sell it, use it for advertising, or use it for credit or lending decisions.
Transfers to your chosen AI service happen only to provide those features, with your consent. We do not receive or review
your Google information.

**Actions require your approval.** Connecting an account gives Thimbleby technical permission to act on it; it does not
let Reginald act on his own. You review and approve the exact message or calendar change before Thimbleby sends it or
creates, changes or cancels an event. An approved action sends what it needs to your mail or calendar provider and, where
it applies, to recipients or attendees.

**What else the app contacts.** To list add-ons, Thimbleby reads the add-on catalog; to tell you about a new version, it
reads the release feed. Those requests contain no personal information, though the servers answering them see your
computer's internet address, as any website would.

**Add-ons.** Add-ons are usually installed from Thimbleby's catalog, where each download is checked against the catalog's
checksum; you can also install an add-on file yourself. A checksum shows the file is the one the catalog lists; it is not
a guarantee an add-on is risk-free. Each add-on says what it can reach before you turn it on; review that, and any service
or privacy terms of its own.

**Keeping and deleting.** Your data stays until you delete it; disconnecting an account or uninstalling the app does not
remove what is already stored. To remove everything: disconnect your accounts and revoke Thimbleby's access in each
provider's account settings; quit Thimbleby and delete its data folder named above (which holds the passwords, keys and
tokens too); delete any backups and exports you kept; then uninstall the app. This does not delete your original mail or
calendar information, undo approved actions, or erase what an AI provider already processed; use those providers'
controls for that.

**Contact and changes.** The feedback button opens an email you write and send yourself; if you contact us, we receive
only what you include, so please leave out private messages, credentials and other people's information. Write to
[CONTACT EMAIL] with privacy questions. We will update this policy when our practices change, and ask for your consent
before any new use of connected-account information that requires it.
