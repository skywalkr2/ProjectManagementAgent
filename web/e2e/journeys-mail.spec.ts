// Journey 2: a person signs in to their mail and calendar on the walkthrough's Mail and calendar screen, the walkthrough
// offers to look back over the last two weeks with its estimate, one Start reads everything, and what was found is one line
// for each source on Today to look over (a sign-in's sources are taken in quietly, design 6.32). A workspace made by the init command with no template, started
// by the serve command, with the mail add-on on (as one the person had already installed and turned on would be) and fakes only at the outside services
// (tests/fake_services.py): the AI service over plain HTTP, and the sign-in, mail and calendar services over HTTPS with
// a throwaway authority the app trusts through its environment.
// Names come from the fictional workspace the fake services serve, never written out here.
import { expect, test } from "@playwright/test";
import {
  collectProblems,
  fakeAddress,
  openView,
  visit,
  type Info,
  type Requests,
  type SignInSeen,
} from "./journey-helpers";

const FAKE = fakeAddress("JOURNEY_MAIL_FAKE_PORT", 8792);

let info: Info;
const problems: string[] = [];

const requests = async (): Promise<Requests> => (await fetch(`${FAKE}/__e2e/ai-requests`)).json();
const service = async (): Promise<SignInSeen> => (await fetch(`${FAKE}/__e2e/sign-in`)).json();

test.describe.serial("journey: mail", () => {
  test.beforeAll(async () => {
    info = await (await fetch(`${FAKE}/__e2e/info`)).json();
  });

  test.afterAll(() => {
    expect(problems.filter((p) => !p.includes("Failed to load resource"))).toEqual([]);
  });

  test("J2. Sign in to my mail and calendar: the look back is offered with its estimate, one Start reads it, and what was found is one line for each source on Today", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    collectProblems(page, problems);

    // A new workspace with the mail add-on on: the walkthrough opens by itself.
    await page.goto(`?token=${info.token}`);
    await expect(page.getByRole("heading", { level: 1, name: "Set up your workspace" })).toBeVisible();
    await visit(page);

    // You, then an AI account, as in the first journey.
    const main = page.locator("main#main");
    await expect(main.getByRole("heading", { level: 2, name: "You" })).toBeVisible();
    await main.getByLabel("Workspace name").fill("Offsite team");
    await main.getByLabel("Your full name").fill(info.people[0]);
    await main.getByRole("button", { name: "Save" }).click();
    await expect(page.locator('[data-screen="you"][data-state]')).toContainText("Done");
    await expect(main.getByRole("heading", { level: 2, name: "Your AI account" })).toBeVisible();
    await main.getByText("More options").click();
    await main.getByLabel(/^Another service that speaks/).check();
    await main.getByRole("textbox", { name: "Service address" }).fill(info.ai_base_url);
    await main.locator("#ai-key").fill("a-made-up-key");
    await main.getByRole("button", { name: "Check", exact: true }).click();
    const everyday = main.getByLabel("AI model for everyday work");
    await expect(everyday.locator("option")).toHaveCount(2);
    await main.getByText(/^Selected model:/).click();
    await everyday.selectOption("fake-small");
    await main.getByLabel("Internal material").check();
    await main.getByRole("button", { name: "Add account" }).click();
    await expect(main.getByText("Everyday work: other — answered")).toBeVisible();
    await visit(page);
    await main.getByRole("button", { name: "Next" }).click();

    // Mail and calendar: the add-on I had installed is listed as a service, on, with what it reads and what it needs
    // to reach. Nothing has been read, and nothing has asked the assistant anything. No restart is waiting.
    await expect(main.getByRole("heading", { level: 2, name: "Mail and calendar" })).toBeVisible();
    const row = main.locator('[data-service="journey-mail"]');
    await expect(row).toHaveAttribute("data-state", "ready");
    await expect(row).toContainText("Reads your mail and calendar");
    await expect(main.getByText(/Restart to connect/)).toHaveCount(0);
    await expect(main.locator("[data-reading]")).toHaveCount(0);
    // The step says, in one line, that social updates, promotions and mailing lists are set aside by themselves.
    await expect(
      main.getByText("Social updates, promotions and mailing lists are set aside; you can turn this off."),
    ).toBeVisible();
    await visit(page);
    const before = await requests();
    expect(before.work).toBe(0);
    await row.getByRole("button", { name: "Sign in to Example mail", exact: true }).click();

    // Signing in happens on the service's own page, which sends me back to the same screen. The service is asked once,
    // and the app proves the sign-in is its own. The answer's code and state are not left in the address.
    await expect(main.getByRole("heading", { level: 2, name: "Mail and calendar" })).toBeVisible();
    await expect(main.getByText(/Signed in as .+@example\.com/)).toBeVisible();
    // The row no longer says to sign in: it says who is signed in and what is read, and offers no Sign in.
    await expect(row).toHaveAttribute("data-signed-in", "");
    await expect(row).toContainText("Reading your mail and calendar.");
    await expect(row).not.toContainText("Sign in to start reading");
    await expect(row.getByRole("button", { name: /^Sign in/ })).toHaveCount(0);
    let seen = await service();
    expect(seen).toMatchObject({ authorizations: 1, exchanges: 1, refused: 0 });
    expect(page.url()).not.toMatch(/code=|state=|sign_in=/);
    // The screen says what is read now, and that what it reads waits for you to start the assistant.
    const reading = main.locator("[data-reading]");
    await expect(reading.getByText("Your inbox")).toBeVisible();
    await expect(reading.getByText("Your calendar")).toBeVisible();
    await expect(reading.getByText(/waits for you to start the assistant/)).toBeVisible();
    await expect(page.locator('[data-screen="mail"][data-state]')).toContainText("Done");
    await visit(page);
    // The mailbox also holds a social update (the service's own category) and a sales mail (a bulk flag), both from the
    // last day: neither is work, so neither is taken in. The look back takes in the last 14 days of work mail (a message
    // from last week too) and every event, whatever its day, so each is counted once below.
    const { mail: recentMail, events: recentEvents, noted: recentNoted, set_aside: aside } = seen.recent_items;
    expect(recentMail.length).toBeGreaterThan(0);
    expect(recentNoted.length).toBeGreaterThan(0);
    expect(aside).toHaveLength(2);
    const { mail, events, noted } = seen.intake_items;
    const handedIn = mail.length + events.length;
    expect(handedIn).toBeGreaterThan(recentMail.length + recentEvents.length);
    expect(noted).toHaveLength(0);

    // The next screen, Your promises, comes right after Mail and calendar, before anything about backups or people. Once
    // the first read has happened it offers the look back over the last 14 days of my own mail, with what it would cost,
    // and the assistant has been asked nothing.
    await main.getByRole("button", { name: "Next" }).click();
    await expect(main.getByRole("heading", { level: 2, name: "Your promises" })).toBeVisible();
    const offer = main.locator('[data-first-promises="offer"]');
    await expect(offer.getByRole("heading", { level: 3, name: "Look back over the last 14 days of your own mail" })).toBeVisible({
      timeout: 30_000,
    });
    await expect(offer).toContainText(
      new RegExp(`${handedIn} items to look over\\. (About \\$\\d+\\.\\d\\d|Less than a cent) in all\\. Nothing is read by the assistant until you press Start\\.`),
    );
    await visit(page);
    expect((await requests()).work).toBe(0);

    // Start: one request for each item taken in, each item once, and the offer gives way to what was found. The stand-in
    // rules find no promise in these messages, so the screen says so plainly and offers "Missed one".
    await offer.getByRole("button", { name: "Start", exact: true }).click();
    await expect.poll(async () => (await requests()).work, { timeout: 60_000 }).toBe(handedIn);
    const asked = await requests();
    // The work mail the rules could not place was sorted in one run for the whole batch; it is not counted as work.
    expect(asked.sorting).toBe(1);
    for (const title of [...mail, ...events]) {
      expect(asked.inputs.filter((input) => input.includes(title))).toHaveLength(1);
    }
    for (const title of aside) expect(asked.inputs.filter((input) => input.includes(title))).toHaveLength(0);
    const none = main.locator('[data-first-promises="none"]');
    await expect(none).toContainText("No open promises found in the mail it looked over.", { timeout: 60_000 });
    await expect(none.getByRole("button", { name: "Missed one" })).toBeVisible();
    await visit(page);

    // Backups and People are left for later, and Done names what was skipped.
    await main.getByRole("button", { name: "Next" }).click();
    await expect(main.getByRole("heading", { level: 2, name: "Backups" })).toBeVisible();
    await main.getByRole("button", { name: "Skip for now" }).click();
    await expect(main.getByRole("heading", { level: 2, name: "People" })).toBeVisible();
    await main.getByRole("button", { name: "Skip for now" }).click();
    await expect(main.getByRole("heading", { level: 2, name: "Done" })).toBeVisible();
    const recap = main.getByRole("list", { name: "What was set up" });
    await expect(recap.locator('[data-step="mail"]')).toContainText("Done");
    await expect(recap.locator('[data-step="backup"]')).toContainText("Skipped");
    await visit(page);
    await main.getByRole("button", { name: "Go to Today" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();

    // The sign-in's sources were read at once and taken in when I pressed Start, so Today has nothing to start: no first-go
    // line, no line waiting for a go.
    const agenda = page.getByRole("region", { name: "Agenda" });
    const came = page.getByRole("region", { name: "Came in" });
    await expect(came.getByText(recentMail[0])).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[data-queue-line="first_go"]')).toHaveCount(0);
    await expect(page.locator('[data-queue-line="intake_go"]')).toHaveCount(0);

    // Today lists the recent mail on Came in and today's meetings on the agenda; what is older or further off is not.
    for (const title of recentMail) await expect(came.getByText(title, { exact: true })).toBeVisible();
    // A meeting that runs past midnight is listed under both days, so the first is enough.
    for (const title of recentEvents) await expect(agenda.getByText(title, { exact: true }).first()).toBeVisible();
    // Came in shows only the work mail, and says how many were set aside.
    for (const title of aside) await expect(came.getByText(title, { exact: true })).toHaveCount(0);
    await expect(came.getByRole("button", { name: "2 set aside" })).toBeVisible();
    for (const title of recentNoted) await expect(came.getByText(title, { exact: true })).toHaveCount(0);
    seen = await service();
    expect(seen).toMatchObject({ mail_reads: 1, calendar_reads: 1, unauthorized: 0 });

    // Sources says what is read without my having chosen it, and who is signed in.
    await openView(page, "Sources");
    await expect(page.getByRole("heading", { level: 1, name: "Sources" })).toBeVisible();
    await expect(page.getByText(/Signed in as .+@example\.com/)).toBeVisible();
    await expect(page.getByText("Your inbox").first()).toBeVisible();
    await expect(page.getByText("Your calendar").first()).toBeVisible();
    await visit(page);

    // What was found is one line for each source, not a line for each item: none of the items' own review lines is on
    // Today until I open the list.
    await openView(page, "Today");
    const found = page.locator('[data-queue-line="intake_review"]');
    const inbox = found.filter({ hasText: "Your inbox" });
    const calendar = found.filter({ hasText: "Your calendar" });
    await expect(inbox).toContainText(`Look over what was found in Your inbox: ${mail.length} items`, { timeout: 60_000 });
    await expect(calendar).toContainText(`Look over what was found in Your calendar: ${events.length} items`, { timeout: 60_000 });
    await expect(found).toHaveCount(2);
    await expect(page.locator('[data-queue-line="review"]')).toHaveCount(0);
    await visit(page);
    expect((await requests()).work).toBe(handedIn);

    // Opening a list shows the changes narrowed to that source and marks it seen; after both, what still needs a look is on
    // Today line by line, one for each item.
    await inbox.getByRole("button", { name: "Look over", exact: true }).click();
    await openView(page, "Today");
    await page.locator('[data-queue-line="intake_review"]').filter({ hasText: "Your calendar" }).getByRole("button", { name: "Look over", exact: true }).click();
    await openView(page, "Today");
    await expect(found).toHaveCount(0);
    // The assistant's results are on Today for review, one line for each item. They wait behind "N new · Show" while the
    // cursor is in the queue, so the list doesn't move under it.
    const reviews = page.locator('[data-queue-line="review"]');
    const showNew = page.getByRole("button", { name: /^Show \d+ new items?$/ });
    await expect(reviews.first().or(showNew).first()).toBeVisible({ timeout: 30_000 });
    if (await showNew.count()) await showNew.click();
    await expect(reviews).toHaveCount(handedIn, { timeout: 30_000 });
    for (const title of [...mail, ...events]) await expect(reviews.filter({ hasText: title })).toHaveCount(1);
    // My own words filed my action; what has no owner asks who it belongs to.
    await expect(page.getByRole("region", { name: "Your to-dos" })).toContainText("Send the venue list by 2026-11-02.");
    const catering = reviews.filter({ hasText: mail.find((title) => /quote/i.test(title)) ?? "" });
    await catering.getByRole("button", { name: /More actions for/ }).click();
    await page.getByRole("menuitem", { name: "Look closer" }).click();
    await expect(catering.getByText("Who owns this?").first()).toBeVisible();
    await visit(page);
    await expect(page.getByText(/stopped, see why below/)).toHaveCount(0);
    expect((await requests()).work).toBe(handedIn);

    // The Set aside folder lists both messages, each with why it was set aside.
    const social = aside.find((t) => /neighbors/i.test(t)) ?? "";
    const sales = aside.find((t) => /sale/i.test(t)) ?? "";
    await came.getByRole("button", { name: "2 set aside" }).click();
    const folder = page.locator("#set-aside");
    await expect(folder.getByRole("heading", { level: 3, name: "Set aside" })).toBeVisible();
    const socialRow = folder.locator("li.line", { hasText: social });
    const salesRow = folder.locator("li.line", { hasText: sales });
    await expect(socialRow).toContainText("Set aside because: your mail service files it under social");
    await expect(salesRow).toContainText("Set aside because: it was sent to many people");
    await visit(page);

    // This is work on the sales mail hands it in: it gets its own request, and nothing else is asked.
    await salesRow.getByRole("button", { name: `Treat as work: ${sales}` }).click();
    await expect(page.getByText(`Handed in ${sales}.`)).toBeVisible();
    await expect(folder.locator("li.line", { hasText: sales })).toHaveCount(0);
    await expect.poll(async () => (await requests()).work, { timeout: 60_000 }).toBe(handedIn + 1);
    const handed = await requests();
    expect(handed.inputs.filter((input) => input.includes(sales))).toHaveLength(1);
    expect(handed.inputs.filter((input) => input.includes(social))).toHaveLength(0);

    // Confirming the social update teaches the sorting about its sender and takes it out of the folder.
    await socialRow.getByRole("button", { name: `More actions for ${social}` }).click();
    await page.getByRole("menuitem", { name: "Confirm" }).click();
    await expect(
      page.getByText("From now on, mail from updates@network.example.com is set aside as sales mail."),
    ).toBeVisible();
    await expect(folder.locator("li.line", { hasText: social })).toHaveCount(0);
    await visit(page);

    // The next read brings a new message from that sender, saying nothing about itself: it is set aside by the new
    // sorting, with no request for the assistant.
    const later = await (await fetch(`${FAKE}/__e2e/mail-later`, { method: "POST" })).json();
    await openView(page, "Today");
    const cameIn = page.getByRole("region", { name: "Came in" });
    // The confirmed message has left the folder, so nothing is counted until the new one is read.
    await expect(cameIn.getByRole("button", { name: "Check now" })).toBeVisible();
    await expect(cameIn.getByRole("button", { name: /set aside$/ })).toHaveCount(0);
    await cameIn.getByRole("button", { name: "Check now" }).click();
    await expect(cameIn.getByRole("button", { name: "1 set aside" })).toBeVisible({ timeout: 30_000 });
    await expect(cameIn.getByText(later.subject)).toHaveCount(0);
    await openView(page, "Sources");
    await expect(page.locator("#set-aside").locator("li.line", { hasText: later.subject })).toContainText(
      `Set aside because: it is from ${later.sender}`,
    );
    expect((await requests()).work).toBe(handedIn + 1);
    expect(await service()).toMatchObject({ unauthorized: 0, refused: 0 });
  });
});
