// Journey 6, the exit test of the first phase in automated form: a person on a fresh install does everything through
// the walkthrough only, and the walkthrough's first result (the look back over the last two weeks of their mail, with its
// estimate, then the promises it found) comes before backups, people or anything else that asks about more. A workspace made by the init command with no template and started by the serve command, with
// nothing installed or set: no mail add-on, no account, no backup. The catalog (named through the app's environment,
// so no settings file is touched) offers the mail add-on as a wheel, and fakes play the outside services
// (tests/fake_services.py): the AI service over plain HTTP, and the sign-in, mail, calendar and catalog services over
// HTTPS with a throwaway authority the app trusts through its environment.
// The journey never touches the workspace: it reads the page, the fake services, the throwaway place add-ons are
// installed into, and the file the app's output is kept in to count restarts.
// Names come from the fictional workspace the fake services serve, never written out here.
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import {
  collectProblems,
  fakeAddress,
  visit,
  type Info,
  type Requests,
  type SignInSeen,
} from "./journey-helpers";

const FAKE = fakeAddress("JOURNEY_NEW_START_FAKE_PORT", 8794);

let info: Info;
const problems: string[] = [];

const requests = async (): Promise<Requests> => (await fetch(`${FAKE}/__e2e/ai-requests`)).json();
const service = async (): Promise<SignInSeen> => (await fetch(`${FAKE}/__e2e/sign-in`)).json();

/** How many times the app restarted since it was started, from what it printed. */
const restarts = (): number => (readFileSync(String(info.log), "utf8").match(/Restarting, as asked/g) ?? []).length;

test.describe.serial("journey: new start", () => {
  test.beforeAll(async () => {
    info = await (await fetch(`${FAKE}/__e2e/info`)).json();
  });

  test.afterAll(() => {
    expect(problems.filter((p) => !p.includes("Failed to load resource"))).toEqual([]);
  });

  test("J6. From a fresh install to my first promises, through the walkthrough only", async ({ page }) => {
    test.setTimeout(300_000);
    collectProblems(page, problems);
    expect(info.log).toBeTruthy();
    expect(info.install_target).toBeTruthy();
    const installed = join(String(info.install_target), "journey_mail");
    expect(restarts()).toBe(0);
    expect(existsSync(installed)).toBe(false);

    // 1. I open the link the start command printed. The walkthrough opens by itself and says nothing is spent yet.
    await page.goto(`?token=${info.token}`);
    await expect(page.getByRole("heading", { level: 1, name: "Set up your workspace" })).toBeVisible();
    await expect(page.getByText("About 10–20 minutes. You can stop and come back.")).toBeVisible();
    await visit(page);
    const main = page.locator("main#main");

    // 2. You.
    await expect(main.getByRole("heading", { level: 2, name: "You" })).toBeVisible();
    await main.getByLabel("Workspace name").fill("Offsite team");
    await main.getByLabel("Your full name").fill(info.people[0]);
    await main.getByRole("button", { name: "Continue" }).click();
    await expect(page.locator('[data-screen="you"][data-state]')).toContainText("Done");
    // The save went on to the next screen, so its mark in the step list says it (a toast from one screen goes when the
    // next opens); that screen's own buttons can be pressed right away.
    await expect(main.getByRole("heading", { level: 2, name: "Your AI account" })).toBeVisible();
    await main.getByRole("button", { name: "Back" }).click({ trial: true });
    await visit(page);
    // A toast from one screen is gone when the next one opens.
    await expect(main.getByRole("heading", { level: 2, name: "Your AI account" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Notifications" }).getByText(/^Saved\./)).toHaveCount(0);

    // 3. Your AI account: the fake service, with Internal ticked, since my mail is internal material.
    await expect(main.getByRole("heading", { level: 2, name: "Your AI account" })).toBeVisible();
    await main.getByRole("radio", { name: /Something else/ }).check();
    await main.getByText("More options").click();
    await main.getByLabel(/^Another service that speaks/).check();
    await main.locator("#ai-key").fill("a-made-up-key");
    await main.getByRole("textbox", { name: "Service address" }).fill(info.ai_base_url);
    await main.getByRole("textbox", { name: "Service address" }).blur();
    // The check runs by itself, for every kind of work, before anything is saved.
    await expect(main.getByText("Works. Ready to use.")).toBeVisible();
    await main.getByText("Advanced", { exact: true }).click();
    await main.getByLabel("AI model for everyday work").selectOption("fake-small");
    await expect(main.getByText("Works. Ready to use.")).toBeVisible();
    // One explicit yes lets this account read my mail and notes (the usual hand-in is internal material).
    await main.getByRole("radio", { name: /^Allow/ }).check();
    await main.getByRole("button", { name: "Continue" }).click();
    await expect(main.getByRole("heading", { level: 2, name: "Mail and calendar" })).toBeVisible();
    await expect(page.locator('[data-screen="ai"][data-state]')).toContainText("Done");
    await visit(page);

    // 4. Mail and calendar: the mail add-on is not on this computer, but the catalog lists it, with what it reads and
    // what it reaches. One button installs and turns it on; nothing restarts yet.
    await expect(main.getByRole("heading", { level: 2, name: "Mail and calendar" })).toBeVisible();
    const row = main.locator('[data-service="journey-mail"]');
    await expect(row).toHaveAttribute("data-state", "not_installed");
    await expect(row).toContainText("Reads your mail and calendar");
    await expect(row).toContainText("Not on this computer yet");
    // What it reaches is behind a disclosure, in plain words, and none of the settings jargon is on the row.
    await expect(row.getByText("What it can access")).toBeVisible();
    expect(await row.innerText()).not.toMatch(/Signs in to|Websites:|Access keys you provide/);
    await row.getByText("What it can access").click();
    await expect(row).toContainText("You sign in on the service's own page");
    await expect(main.getByText(/Restart to finish connecting/)).toHaveCount(0);
    await visit(page);
    expect(existsSync(installed)).toBe(false);
    const before = await requests();
    expect(before.work).toBe(0);
    await row.getByRole("button", { name: "Install and connect Example mail" }).click();
    await expect(row).toHaveAttribute("data-state", "restart");
    // It went into the throwaway place the app installs into, and nothing has restarted.
    expect(existsSync(installed)).toBe(true);
    expect(restarts()).toBe(0);

    // The one restart, which I press. The walkthrough is still at this screen when the app is back, and a page opened
    // fresh after it resumes here too.
    const restart = main.getByRole("button", { name: "Restart to finish connecting" });
    await expect(restart).toBeVisible();
    await visit(page);
    await restart.click();
    await expect(row).toHaveAttribute("data-state", "ready", { timeout: 90_000 });
    expect(restarts()).toBe(1);
    await expect(main.getByRole("heading", { level: 2, name: "Mail and calendar" })).toBeVisible();
    await expect(main.getByText(/Restart to finish connecting/)).toHaveCount(0);
    await page.reload();
    await expect(page.getByRole("heading", { level: 1, name: "Set up your workspace" })).toBeVisible();
    await expect(main.getByRole("heading", { level: 2, name: "Mail and calendar" })).toBeVisible();
    await expect(row).toHaveAttribute("data-state", "ready");
    await visit(page);

    // Sign in on the service's own page, which sends me back to this screen. Nothing was asked of the assistant.
    expect((await service()).authorizations).toBe(0);
    await row.getByRole("button", { name: "Sign in to Example mail", exact: true }).click();
    await expect(main.getByRole("heading", { level: 2, name: "Mail and calendar" })).toBeVisible();
    await expect(main.getByText(/Signed in as .+@example\.com/)).toBeVisible();
    // The row no longer says to sign in: it says who is signed in and what is read, and offers no Sign in.
    await expect(row).toHaveAttribute("data-signed-in", "");
    await expect(row).toContainText("Reading your mail and calendar.");
    await expect(row).not.toContainText("Sign in to start reading");
    await expect(row.getByRole("button", { name: /^Sign in/ })).toHaveCount(0);
    // The sign-in toast doesn't cover Back or Next either.
    await main.getByRole("button", { name: "Back" }).click({ trial: true });
    await main.getByRole("button", { name: "Continue" }).click({ trial: true });
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
    expect((await requests()).work).toBe(0);
    const { mail: recentMail, events: recentEvents, noted: recentNoted } = seen.recent_items;
    expect(recentMail.length).toBeGreaterThan(0);
    expect(recentNoted.length).toBeGreaterThan(0);
    // The look back takes in the last 14 days of work mail and every event, so each is counted once below.
    const { mail, events, noted } = seen.intake_items;
    const handedIn = mail.length + events.length;
    expect(handedIn).toBeGreaterThan(recentMail.length + recentEvents.length);
    expect(noted).toHaveLength(0);
    // The assistant is asked, once, to read the message that holds a promise: the person's own, to send the venue list.
    const promiseLine = `${info.people[0]} will send the venue list by 2026-11-02.`;
    const scripted = await fetch(`${FAKE}/__e2e/script`, {
      method: "POST",
      body: JSON.stringify({
        when: "will send the venue list by 2026-11-02",
        answer: {
          summary: "Read by the journey's script.",
          ops: [
            {
              op: "action.add",
              text: "Send the venue list.",
              owners: ["me"],
              due: "2026-11-02",
              basis: "said",
              evidence: { quote: promiseLine },
            },
          ],
        },
      }),
    });
    expect(scripted.ok).toBe(true);
    await main.getByRole("button", { name: "Continue" }).click();

    // 5. Your promises, right after mail and before backups or people: the look back over the last 14 days of my own mail
    // is offered with what it would cost, and the assistant has been asked nothing.
    await expect(main.getByRole("heading", { level: 2, name: "Your promises" })).toBeVisible();
    const offer = main.locator('[data-first-promises="offer"]');
    await expect(offer.getByRole("heading", { level: 3, name: "Look back over the last 14 days of your own mail" })).toBeVisible({
      timeout: 30_000,
    });
    await expect(offer).toContainText(
      new RegExp(`${handedIn} items to look over\\. (About \\$\\d+\\.\\d\\d|Less than a cent) in all\\. Nothing is read by the assistant until you press Start\\.`),
    );
    // Nothing that asks about projects, areas, packs or more accounts is on this screen.
    await expect(main.getByText("Optional extras")).toHaveCount(0);
    await visit(page);
    expect((await requests()).work).toBe(0);
    seen = await service();
    expect(seen).toMatchObject({ mail_reads: 1, calendar_reads: 1, unauthorized: 0 });

    // Start: one request for each item taken in, each item once, and then the promise it found is on the screen.
    await offer.getByRole("button", { name: "Start", exact: true }).click();
    await expect.poll(async () => (await requests()).work, { timeout: 60_000 }).toBe(handedIn);
    const asked = await requests();
    // The work mail the rules could not place was sorted in one run for the whole batch; it is not counted as work.
    expect(asked.sorting).toBe(1);
    for (const title of [...mail, ...events]) expect(asked.inputs.filter((input) => input.includes(title))).toHaveLength(1);
    const promises = main.getByRole("list", { name: "Promises found" });
    await expect(promises).toBeVisible({ timeout: 60_000 });
    const mine = promises.locator("li", { hasText: "Send the venue list." });
    await expect(mine).toHaveCount(1);
    await expect(mine).toContainText("You owe this");
    await expect(mine).toContainText(`From: “${promiseLine}”`);
    // Nobody else owes anything yet, so there is no follow-up to copy.
    await expect(main.getByRole("region", { name: "One follow-up is ready" })).toHaveCount(0);
    await visit(page);
    await main.getByRole("button", { name: "Continue" }).click();

    // 6. Backups: a folder outside the workspace, checked before it is saved.
    await expect(main.getByRole("heading", { level: 2, name: "Backups" })).toBeVisible();
    await main.getByLabel("Folder", { exact: true }).fill(info.backup_folder);
    await main.getByRole("button", { name: "Back up now and continue" }).click();
    await expect(page.locator('[data-screen="backup"][data-state]')).toContainText("Done");
    // Choosing the folder makes the first backup at once, and Back up now and continue goes on to People.
    await expect(main.getByRole("heading", { level: 2, name: "People" })).toBeVisible();
    await visit(page);

    // 7. People: skipping is fine.
    await expect(main.getByRole("heading", { level: 2, name: "People" })).toBeVisible();
    await visit(page);
    await main.getByRole("button", { name: "I'll do this later" }).click();

    // 8. Done: what was set up and what was skipped, then the optional extras. The last button lands on Today.
    await expect(main.getByRole("heading", { level: 2, name: "Done" })).toBeVisible();
    const recap = main.getByRole("list", { name: "What was set up" });
    for (const step of ["workspace", "ai", "mail", "backup"]) await expect(recap.locator(`[data-step="${step}"]`)).toContainText("Done");
    await expect(recap.locator('[data-step="people"]')).toContainText("Skipped");
    const extras = main.getByRole("region", { name: "Optional extras" });
    await expect(extras).toBeVisible();
    expect(await extras.getByRole("listitem").count()).toBeGreaterThan(0);
    await visit(page);
    await main.getByRole("button", { name: "Go to Today" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
    // The look back was started on the walkthrough's own screen, so Today has nothing to start.
    await expect(page.locator('[data-queue-line="first_go"]')).toHaveCount(0);
    await expect(page.locator('[data-queue-line="intake_go"]')).toHaveCount(0);
    // The first backup was made while setting up, so Today doesn't ask for one and the header chip doesn't say one is needed.
    await expect(page.getByRole("region", { name: "Backup", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^App status: / })).not.toContainText("Backup needed");

    // 9. The recent mail is on Came in within seconds, and today's meetings are on the agenda; what is older isn't.
    const came = page.getByRole("region", { name: "Came in" });
    const agenda = page.getByRole("region", { name: "Agenda" });
    await expect(came.getByText(recentMail[0])).toBeVisible({ timeout: 10_000 });
    for (const title of recentMail) await expect(came.getByText(title, { exact: true })).toBeVisible();
    // A meeting that runs past midnight is listed under both days, so the first is enough.
    for (const title of recentEvents) await expect(agenda.getByText(title, { exact: true }).first()).toBeVisible();
    for (const title of recentNoted) await expect(came.getByText(title, { exact: true })).toHaveCount(0);
    await visit(page);

    // 10. What was found is one line for each source, not a line for each item: none of the items' own review lines is on
    // Today until I open the list.
    const found = page.locator('[data-queue-line="intake_review"]');
    await expect(found.filter({ hasText: "Your inbox" })).toContainText(`Look over what was found in Your inbox: ${mail.length} items`, {
      timeout: 60_000,
    });
    await expect(found.filter({ hasText: "Your calendar" })).toContainText(
      `Look over what was found in Your calendar: ${events.length} items`,
      { timeout: 60_000 },
    );
    await expect(found).toHaveCount(2);
    await expect(page.locator('[data-queue-line="review"]')).toHaveCount(0);
    await visit(page);

    // Opening each list marks it seen; after both, what still needs a look is on Today line by line, one for each item.
    for (const label of ["Your inbox", "Your calendar"]) {
      await page.getByRole("link", { name: /^Today/ }).first().click();
      await found.filter({ hasText: label }).getByRole("button", { name: "Look over", exact: true }).click();
    }
    await page.getByRole("link", { name: /^Today/ }).first().click();
    await expect(found).toHaveCount(0);
    // The results wait behind "N new · Show" while the cursor is in the queue, so the list doesn't move under it.
    const reviews = page.locator('[data-queue-line="review"]');
    const showNew = page.getByRole("button", { name: /^Show \d+ new items?$/ });
    await expect(reviews.first().or(showNew).first()).toBeVisible({ timeout: 30_000 });
    if (await showNew.count()) await showNew.click();
    await expect(reviews).toHaveCount(handedIn, { timeout: 30_000 });
    for (const title of [...mail, ...events]) await expect(reviews.filter({ hasText: title })).toHaveCount(1);
    await visit(page);
    await expect(page.getByText(/stopped, see why below/)).toHaveCount(0);

    // The whole path: one request per item and none before Start, one sign-in, and exactly one restart.
    expect((await requests()).work).toBe(handedIn);
    expect(await service()).toMatchObject({ authorizations: 1, exchanges: 1, unauthorized: 0, refused: 0 });
    expect(restarts()).toBe(1);
  });
});
