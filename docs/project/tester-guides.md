# Tester setup guide and company IT guide (drafts, 2026-10-17)

Drafted with an outside assistant at the owner's request and checked against the design. Review changes: testers may use
Gmail, Outlook or a plain mailbox, not only Gmail; the first launch's setup guide does the connecting (AI account, then
mail), so the steps point there; a backup folder is part of setup; and the IT guide no longer says the app makes drafts
in the mailbox (drafts stay in Thimbleby until approved). Menu paths in Apple's and Microsoft's screens are checked again
when the installers ship. Placeholders: support email, application ID, publisher, privacy policy address.

---

# Thimbleby: tester setup guide

Thanks for helping test Thimbleby. This early build is unsigned, so your computer asks for one extra confirmation before
opening it. You'll need your own AI account, the mail account you'll use for the test (Gmail, Outlook or another mailbox),
and the download link we sent you.

## 1. Install and open Thimbleby

**On macOS**
1. Open the downloaded disk image and drag Thimbleby into Applications.
2. Open Thimbleby. If macOS blocks it, close the message.
3. Open **System Settings › Privacy & Security**, find the message about Thimbleby and click **Open Anyway**.
4. Confirm **Open** and sign in with your Mac password if asked.

Only make this exception for the download we sent you. If macOS says the app is damaged or reports malware, stop and
contact us.

**On Windows**
1. Open the downloaded installer.
2. If SmartScreen says **Windows protected your PC**, choose **More info › Run anyway**.
3. Follow the installation steps.

If **Run anyway** isn't offered, your organization's policy may be blocking it: contact your IT team or us, and don't
turn off your security protections. A later test build may ask again.

## 2. Follow the setup guide

The first time Thimbleby opens, its setup guide walks you through:
- **your AI account:** choose your AI service and sign in or paste its key there (never in a feedback form or email). That
  service processes the text Reginald works on, using your account, and its charges and terms apply; a model running on
  your computer keeps it there;
- **your mail and calendar:** sign in on your provider's own page in your browser. During the test, Google may show an
  "unverified app" warning: continue only if it names Thimbleby. **With Gmail, expect to reconnect about once a week**;
  that's Google's rule for test apps, not your password expiring. Outlook and other mailboxes don't have this limit;
- **a backup folder:** pick one, so nothing is lost if something goes wrong.

## 3. If something breaks

Quit and reopen Thimbleby once. For a disconnected account, reconnect it from the line Thimbleby shows on Today. If a sent
message or calendar change shows an unclear result, check your mail or calendar before trying again, so nothing goes out
twice. Then write to **[SUPPORT EMAIL]** with your computer (Mac or Windows) and Thimbleby's version, what you did, what
you expected and what happened, and any error text with private details removed. Never send passwords, keys or private
mail, and keep your data in place unless we agree on a recovery step. Reginald always waits for your yes on the exact
message or calendar change; if he ever doesn't, tell us at once.

---

# Thimbleby: company IT administrator guide

Thimbleby is a Mac and Windows desktop assistant that helps people keep track of commitments, prepare replies and manage
their calendar. Its helper, Reginald, sends messages and changes calendars only after the user approves the exact action.

**Application (client) ID:** [APPLICATION ID] · **Publisher:** [PUBLISHER NAME AND VERIFICATION STATUS] ·
**Support:** [SUPPORT EMAIL] · **Privacy policy:** [PRIVACY POLICY ADDRESS]

## Where information goes

Thimbleby runs on the user's computer and keeps its data there; it connects directly to Microsoft's services. Nothing is
sent to the developer, and there are no analytics. When the user picks a hosted AI service, the text Reginald works on is
sent to that service with the user's own account; a local model keeps it on the computer. Please approve the AI provider
and its settings under your organization's policies before work mail is connected.

## Requested permissions (delegated, acting for the signed-in user only)

| Permission | Why |
|---|---|
| `Mail.ReadWrite` | Read mail, archive or move messages and set categories, after the user's approval. Not sending. |
| `Mail.Send` | Send replies and follow-ups the user approved. |
| `Calendars.ReadWrite` | Read events and make the changes the user approved. |
| `offline_access` | Stay connected without signing in every session. |
| `openid` | Sign the user in. |

These permissions technically allow more than the approval step does; the approval is enforced by Thimbleby itself.

## Granting administrator consent

With an account allowed to grant consent (such as Cloud Application Administrator), subject to your tenant's policies:
1. Check the consent link's application ID against the one above.
2. In the Microsoft Entra admin center, open **Enterprise apps › All applications** and select Thimbleby, checking its
   application ID and publisher, not just its name.
3. Under **Permissions**, choose **Grant admin consent**, review the list and accept if appropriate.
4. Ask a pilot user to reconnect their work account and test.

Consent applies to the whole tenant. For a limited pilot, set **Assignment required** and assign only the approved users
or groups; don't loosen tenant-wide consent settings for the test. Publisher verification confirms who the publisher is;
it doesn't replace your own security review.

## Ending the pilot

Revoke the app's consent and block sign-ins in its Enterprise application settings, and have users disconnect their
accounts and delete Thimbleby's data. Revoking doesn't erase what was already downloaded or processed by an approved AI
service; follow your retention and deletion procedures.
