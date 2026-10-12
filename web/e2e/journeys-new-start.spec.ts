// Journey 6, the exit test of the first phase in automated form: a person on a fresh install does everything through
// the walkthrough only. A workspace made by the init command with no template and started by the serve command, with
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

  test("J6. From a fresh install to the assistant's first results, through the walkthrough only", async ({ page }) => {
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
    await expect(page.getByText("About 10 minutes. Nothing is spent until you press Go at the end.")).toBeVisible();
    await visit(page);
    const main = page.locator("main#main");

    // 2. You.
    await expect(main.getByRole("heading", { level: 2, name: "You" })).toBeVisible();
    await main.getByLabel("Workspace name").fill("Offsite team");
    await main.getByLabel("Your full name").fill(info.people[0]);
    await main.getByRole("button", { name: "Save" }).click();
    await expect(page.locator('[data-screen="you"][data-state]')).toContainText("Done");
    // The save said so in a toast, which never covers the screen's own buttons: Back and Next can be pressed right away.
    const notices = page.getByRole("region", { name: "Notifications" });
    await expect(notices.getByText(/^Saved\./)).toBeVisible();
    await main.getByRole("button", { name: "Next" }).click({ trial: true });
    await visit(page);
    await main.getByRole("button", { name: "Next" }).click();
    // A toast from one screen is gone when the next one opens.
    await expect(main.getByRole("heading", { level: 2, name: "Your AI account" })).toBeVisible();
    await expect(notices.getByText(/^Saved\./)).toHaveCount(0);

    // 3. Your AI account: the fake service, with Internal ticked, since my mail is internal material.
    await expect(main.getByRole("heading", { level: 2, name: "Your AI account" })).toBeVisible();
    await main.getByText("More options").click();
    await main.getByLabel(/^Another service that speaks/).check();
    await main.getByRole("textbox", { name: "Address" }).fill(info.ai_base_url);
    await main.locator("#ai-key").fill("a-made-up-key");
    await main.getByRole("button", { name: "Check", exact: true }).click();
    const everyday = main.getByLabel("Model for everyday work");
    await expect(everyday.locator("option")).toHaveCount(2);
    await main.getByText(/^Models:/).click();
    await everyday.selectOption("fake-small");
    await main.getByLabel("Internal material").check();
    await visit(page);
    await main.getByRole("button", { name: "Add account" }).click();
    await expect(main.getByText("Everyday work: other — answered")).toBeVisible();
    await expect(page.locator('[data-screen="ai"][data-state]')).toContainText("Done");
    await visit(page);
    await main.getByRole("button", { name: "Next" }).click();

    // 4. Mail and calendar: the mail add-on is not on this computer, but the catalog lists it, with what it reads and
    // what it reaches. One button installs and turns it on; nothing restarts yet.
    await expect(main.getByRole("heading", { level: 2, name: "Mail and calendar" })).toBeVisible();
    const row = main.locator('[data-service="journey-mail"]');
    await expect(row).toHaveAttribute("data-state", "not_installed");
    await expect(row).toContainText("Reads your mail and calendar");
    await expect(row).toContainText("Not on this computer yet");
    // What it reaches is behind a disclosure, in plain words, and none of the settings jargon is on the row.
    await expect(row.getByText("What it reaches")).toBeVisible();
    expect(await row.innerText()).not.toMatch(/Signs in to|Internet:|Keys you provide/);
    await row.getByText("What it reaches").click();
    await expect(row).toContainText("You sign in on the service's own page");
    await expect(main.getByText(/Restart to connect/)).toHaveCount(0);
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
    const restart = main.getByRole("button", { name: "Restart to connect (a few seconds)" });
    await expect(restart).toBeVisible();
    await visit(page);
    await restart.click();
    await expect(row).toHaveAttribute("data-state", "ready", { timeout: 90_000 });
    expect(restarts()).toBe(1);
    await expect(main.getByRole("heading", { level: 2, name: "Mail and calendar" })).toBeVisible();
    await expect(main.getByText(/Restart to connect/)).toHaveCount(0);
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
    await main.getByRole("button", { name: "Next" }).click({ trial: true });
    let seen = await service();
    expect(seen).toMatchObject({ authorizations: 1, exchanges: 1, refused: 0 });
    expect(page.url()).not.toMatch(/code=|state=|sign_in=/);
    // The screen says what is read now, and that the last day's mail waits for the first Go.
    const reading = main.locator("[data-reading]");
    await expect(reading.getByText("Your inbox")).toBeVisible();
    await expect(reading.getByText("Your calendar")).toBeVisible();
    await expect(reading.getByText(/waits for your first Go/)).toBeVisible();
    await expect(page.locator('[data-screen="mail"][data-state]')).toContainText("Done");
    await visit(page);
    expect((await requests()).work).toBe(0);
    const { mail, events, noted } = seen.recent_items;
    const handedIn = mail.length + events.length;
    expect(handedIn).toBeGreaterThan(0);
    expect(noted.length).toBeGreaterThan(0);
    await main.getByRole("button", { name: "Next" }).click();

    // 5. Backups: a folder outside the workspace, checked before it is saved.
    await expect(main.getByRole("heading", { level: 2, name: "Backups" })).toBeVisible();
    await main.getByLabel("Folder", { exact: true }).fill(info.backup_folder);
    await main.getByRole("button", { name: "Use this folder for backups" }).click();
    await expect(page.locator('[data-screen="backup"][data-state]')).toContainText("Done");
    // Choosing the folder makes the first backup at once, and the screen says how it went.
    await expect(main.locator("[data-first-backup]")).toContainText("First backup made", { timeout: 30_000 });
    await visit(page);
    await main.getByRole("button", { name: "Next" }).click();

    // 6. People: skipping is fine.
    await expect(main.getByRole("heading", { level: 2, name: "People" })).toBeVisible();
    await visit(page);
    await main.getByRole("button", { name: "Skip for now" }).click();

    // 7. Done: what was set up and what was skipped, then the optional extras. The last button lands on Today with the
    // line that asks for my first go in focus.
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
    const go = page.locator("li.line", { hasText: "Start the assistant" });
    await expect(go).toHaveCount(1);
    await expect(go).toBeFocused();
    // Go is fully on the screen without scrolling, not clipped by the short card it sits in.
    await expect(go).toBeInViewport({ ratio: 1 });
    await expect(go.getByRole("button", { name: "Go", exact: true })).toBeInViewport({ ratio: 1 });
    // The first backup was made while setting up, so Today doesn't ask for one and the header chip doesn't say one is needed.
    await expect(page.getByRole("region", { name: "Backup", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Status: / })).not.toContainText("Backup needed");

    // 8. The recent mail is on Came in within seconds, and today's meetings are on the agenda; what is older isn't.
    const came = page.getByRole("region", { name: "Came in" });
    const agenda = page.getByRole("region", { name: "Agenda" });
    await expect(came.getByText(mail[0])).toBeVisible({ timeout: 10_000 });
    for (const title of mail) await expect(came.getByText(title, { exact: true })).toBeVisible();
    for (const title of events) await expect(agenda.getByText(title, { exact: true })).toBeVisible();
    for (const title of noted) await expect(page.getByRole("main").getByText(title, { exact: true })).toHaveCount(0);

    // 9. The first-go line shows the count and an estimate. Nothing has been asked of the assistant yet.
    await expect(go).toContainText(new RegExp(`Start the assistant: ${handedIn} items, (about \\$\\d+\\.\\d\\d|less than a cent)`));
    await expect(go).toContainText("Nothing is spent until you press Go.");
    await visit(page);
    expect((await requests()).work).toBe(0);
    seen = await service();
    expect(seen).toMatchObject({ mail_reads: 1, calendar_reads: 1, unauthorized: 0 });

    await expect(go.getByRole("button", { name: "Go", exact: true })).toBeInViewport({ ratio: 1 });
    // Go: one request for each item handed in, each item once, and the line goes.
    await go.getByRole("button", { name: "Go", exact: true }).click();
    await expect(page.locator("li.line", { hasText: "Start the assistant" })).toHaveCount(0);
    await expect.poll(async () => (await requests()).work, { timeout: 60_000 }).toBe(handedIn);
    const asked = await requests();
    for (const title of [...mail, ...events]) expect(asked.inputs.filter((input) => input.includes(title))).toHaveLength(1);
    for (const title of noted) expect(asked.inputs.filter((input) => input.includes(title))).toHaveLength(0);

    // The assistant's results are on Today for review, one for each item, under the group that says they arrived.
    const changes = page.getByRole("region", { name: "What changed" });
    const arrived = changes.getByRole("button", { name: /Show/ });
    const firstReview = changes.locator(".kind", { hasText: "Review" });
    await expect(arrived.or(firstReview).first()).toBeVisible({ timeout: 30_000 });
    if (await arrived.count()) await arrived.first().click();
    const reviews = changes.locator("li.line", { has: page.locator(".kind", { hasText: "Review" }) });
    await expect(reviews).toHaveCount(handedIn, { timeout: 30_000 });
    for (const title of [...mail, ...events]) await expect(reviews.filter({ hasText: title })).toHaveCount(1);
    await visit(page);
    await expect(page.getByText(/stopped, see why below/)).toHaveCount(0);

    // The whole path: one request per item and none before Go, one sign-in, and exactly one restart.
    expect((await requests()).work).toBe(handedIn);
    expect(await service()).toMatchObject({ authorizations: 1, exchanges: 1, unauthorized: 0, refused: 0 });
    expect(restarts()).toBe(1);
  });
});
