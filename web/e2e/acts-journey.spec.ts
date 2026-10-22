// Mail and calendar acts, end to end (design 6.12, 7.4): on the core's stand-in channel serving a plain mailbox with acting
// switched on, the person replies to a saved message and sends the reply, files a message away and takes that back, and
// answers an invitation. Each time the person sees the act's exact content in Waiting to go out, its state in words, and the
// confirm before it goes; what the channel was handed (`/__e2e/acts`) is what was shown. Its server is started with `--acts`,
// which seeds the messages and the invitation, and the reply's words are the only thing the test makes up.
import { expect, test, type Page } from "@playwright/test";
import { checkAccessibility, collectProblems } from "./journey-helpers";

interface Handed {
  kind: string;
  action: string;
  parts: Record<string, string>;
  to: string[];
  about: string[];
  label: string | null;
  folder: string | null;
  answer: string | null;
  proposed_start: string | null;
  proposed_end: string | null;
}

interface Acts {
  enabled: boolean;
  account: string;
  reply: { id: string; title: string; sender: string };
  tidy: { id: string; title: string };
  invitation: { id: string; title: string; organizer: string };
  delivered: Handed[];
  undone: Handed[];
}

const seeded = async (page: Page): Promise<Acts> => (await page.request.get("/__e2e/acts")).json();

async function signIn(page: Page) {
  await page.goto("?token=e2e-token");
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
}

/** Open a record's own page, as a link to it from anywhere in the app does. */
async function openRecord(page: Page, kind: string, id: string, heading: string) {
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, `records/${kind}/${id}`);
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
}

const waiting = (page: Page) => page.getByRole("list", { name: "Waiting to go out" }).getByRole("listitem");
const wentOut = (page: Page) => page.getByRole("list", { name: "Went out" }).getByRole("listitem");

test.describe.configure({ mode: "serial" });

test.describe("mail and calendar acts", () => {
  test("a reply is drafted from the message, read in full in Waiting to go out, approved and sent as shown", async ({ page }) => {
    const problems: string[] = [];
    collectProblems(page, problems);
    const first = await seeded(page);
    expect(first.enabled).toBe(true);
    expect(first.delivered).toEqual([]);

    await signIn(page);
    await openRecord(page, "source", first.reply.id, first.reply.title);
    await page.getByRole("button", { name: "Reply", exact: true }).click();
    const words = page.getByRole("textbox", { name: "Your reply" });
    await expect(words).toBeFocused();
    await checkAccessibility(page);
    const reply = "The proofs ship on Monday.";
    await words.fill(reply);
    await page.getByRole("button", { name: "Draft the reply" }).click();

    // It opens in Waiting to go out, a draft to approve, with the exact words, who it goes to and the account's channel.
    await expect(page.getByRole("heading", { level: 1, name: "Waiting to go out" })).toBeVisible();
    await expect(waiting(page)).toHaveCount(1);
    await expect(waiting(page)).toContainText(`Reply to ${first.reply.sender}`);
    await expect(waiting(page)).toContainText("To approve");
    const pane = page.getByRole("complementary", { name: `Reply to ${first.reply.sender}` });
    await expect(pane).toContainText(reply);
    await expect(pane).toContainText(`Re: ${first.reply.title}`);
    await expect(pane).toContainText(first.reply.sender);
    expect((await seeded(page)).delivered).toEqual([]); // drafting sent nothing

    // The sender was never written to: the yes waits for the acknowledgement by name, then a confirm in words.
    const send = pane.getByRole("button", { name: "Approve and send" });
    await expect(send).toBeDisabled();
    await pane.getByRole("checkbox", { name: new RegExp(`I know about ${first.reply.sender}`) }).check();
    await checkAccessibility(page);
    await send.click();
    const dialog = page.getByRole("dialog", { name: `Go ahead with this now: Reply to ${first.reply.sender}?` });
    await expect(dialog).toBeVisible();
    expect((await seeded(page)).delivered).toEqual([]);
    await dialog.getByRole("button", { name: "Send" }).click();

    await expect(page.getByText(`Sent the reply to ${first.reply.sender}.`)).toBeVisible();
    await expect(page.getByText("Nothing is waiting to go out.")).toBeVisible();
    await expect(wentOut(page)).toHaveCount(1);
    await expect(wentOut(page)).toContainText("Sent");

    // The channel was handed exactly what was shown, once, as a reply to the saved message.
    const after = await seeded(page);
    expect(after.delivered).toHaveLength(1);
    expect(after.delivered[0]).toMatchObject({
      kind: "message",
      action: "reply",
      to: [first.reply.sender],
      about: [first.reply.id],
      parts: { subject: `Re: ${first.reply.title}`, body: reply },
    });
    expect(problems).toEqual([]);
  });

  test("a message is filed away from its page and taken back from the toast, the channel asked once each way", async ({ page }) => {
    const problems: string[] = [];
    collectProblems(page, problems);
    const first = await seeded(page);
    const before = first.delivered.length;

    await signIn(page);
    await openRecord(page, "source", first.tidy.id, first.tidy.title);
    await page.locator(".heading").getByRole("button", { name: /More actions for/ }).click();
    await page.getByRole("menuitem", { name: "Archive" }).click();

    // The act says what it does in words and lists the message it is about: its sender, subject and date.
    await expect(page.getByRole("heading", { level: 1, name: "Waiting to go out" })).toBeVisible();
    await expect(waiting(page)).toHaveCount(1);
    await expect(waiting(page)).toContainText("Archive 1 message");
    const pane = page.getByRole("complementary", { name: "Archive 1 message" });
    const messages = pane.getByRole("region", { name: "The messages" });
    await expect(messages).toContainText("This changes 1 message.");
    await expect(messages).toContainText(`${first.reply.sender}: ${first.tidy.title}`);
    await checkAccessibility(page);

    await pane.getByRole("button", { name: "Approve and send" }).click();
    const dialog = page.getByRole("dialog", { name: "Go ahead with this now: Archive 1 message?" });
    await expect(dialog.getByText(/You can take it back afterward/)).toBeVisible();
    expect((await seeded(page)).delivered).toHaveLength(before);
    await dialog.getByRole("button", { name: "Send" }).click();

    // Sent, with Undo while the service allows it; Undo takes it back and says so.
    await expect(page.getByText("Sent the change to your mail.")).toBeVisible();
    expect((await seeded(page)).delivered).toHaveLength(before + 1);
    await page.getByRole("button", { name: "Undo" }).click();
    await expect(page.getByText("Took back the change to your mail.")).toBeVisible();
    const after = await seeded(page);
    expect(after.delivered[before]).toMatchObject({ kind: "mailbox", action: "archive", about: [first.tidy.id], parts: {} });
    expect(after.undone).toHaveLength(1);
    expect(after.undone[0]).toMatchObject({ kind: "mailbox", action: "archive", about: [first.tidy.id] });
    await expect(wentOut(page).first()).toContainText("Undone");
    expect(problems).toEqual([]);
  });

  test("an invitation is answered from its entry: the answer is read in full, goes to the organizer after the yes and can't be taken back", async ({ page }) => {
    const problems: string[] = [];
    collectProblems(page, problems);
    const first = await seeded(page);
    const before = first.delivered.length;

    await signIn(page);
    await openRecord(page, "event", first.invitation.id, first.invitation.title);
    await expect(page.getByRole("button", { name: "Accept", exact: true })).toBeVisible();
    await checkAccessibility(page);
    await page.getByRole("button", { name: "Accept", exact: true }).click();

    await expect(page.getByRole("heading", { level: 1, name: "Waiting to go out" })).toBeVisible();
    const title = `Answer to ${first.invitation.title}: accept`;
    await expect(waiting(page)).toHaveCount(1);
    await expect(waiting(page)).toContainText(title);
    await expect(waiting(page)).toContainText("To approve");
    const pane = page.getByRole("complementary", { name: title });
    await expect(pane.getByRole("region", { name: "The event" })).toContainText("Your answer: accept");
    await expect(pane).toContainText(first.invitation.organizer);
    await checkAccessibility(page);

    await pane.getByRole("checkbox", { name: new RegExp(`I know about ${first.invitation.organizer}`) }).check();
    await pane.getByRole("button", { name: "Approve and send" }).click();
    const dialog = page.getByRole("dialog", { name: `Go ahead with this now: ${title}?` });
    await expect(dialog).toBeVisible();
    expect((await seeded(page)).delivered).toHaveLength(before);
    await dialog.getByRole("button", { name: "Send" }).click();

    await expect(page.getByText(`Sent the answer to ${first.invitation.title}.`)).toBeVisible();
    await expect(page.getByRole("button", { name: "Undo" })).toHaveCount(0); // others are told of an answer
    const after = await seeded(page);
    expect(after.delivered).toHaveLength(before + 1);
    expect(after.delivered[before]).toMatchObject({
      kind: "calendar",
      action: "answer",
      answer: "accepted",
      to: [first.invitation.organizer],
      about: [first.invitation.id],
    });
    expect(problems).toEqual([]);
  });

  test("a plain mailbox can't propose another time: the invitation offers Maybe and Decline, and says why", async ({ page }) => {
    const problems: string[] = [];
    collectProblems(page, problems);
    const first = await seeded(page);
    const before = first.delivered.length;

    await signIn(page);
    await openRecord(page, "event", first.invitation.id, first.invitation.title);
    await expect(page.getByText(/Proposing another time needs a calendar account/)).toBeVisible();
    await page.getByRole("button", { name: /More actions for the invitation's answers/ }).click();
    await expect(page.getByRole("menuitem")).toHaveText(["Maybe", "Decline"]);
    await expect(page.getByRole("menuitem", { name: "Propose a time…" })).toHaveCount(0);
    await checkAccessibility(page);

    // The choices it does offer draft the answer and send nothing: Maybe waits in Waiting to go out, read in full.
    await page.getByRole("menuitem", { name: "Maybe" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Waiting to go out" })).toBeVisible();
    const title = `Answer to ${first.invitation.title}: maybe`;
    const pane = page.getByRole("complementary", { name: title });
    await expect(pane.getByRole("region", { name: "The event" })).toContainText("Your answer: maybe");
    expect((await seeded(page)).delivered).toHaveLength(before);

    // Taking it back is in its row's menu, once the detail that opened over the list is closed: it will not go.
    await pane.getByRole("button", { name: "Close" }).click();
    await waiting(page).filter({ hasText: title }).getByRole("button", { name: /More actions for/ }).click();
    await page.getByRole("menuitem", { name: "Take it back" }).click();
    await expect(waiting(page).filter({ hasText: title })).toHaveCount(0);
    expect((await seeded(page)).delivered).toHaveLength(before);
    expect(problems).toEqual([]);
  });
});
