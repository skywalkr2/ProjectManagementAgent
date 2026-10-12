// Journey 2: a person signs in to their mail and calendar on the walkthrough's Mail and calendar screen, the assistant reads
// what came in, and the results are on Today for review. A workspace made by the init command with no template, started
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

  test("J2. Sign in to my mail and calendar: the inbox and calendar are read, the assistant waits for my go, and its results are on Today", async ({
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
    await main.getByRole("button", { name: "Next" }).click();
    await expect(main.getByRole("heading", { level: 2, name: "Your AI account" })).toBeVisible();
    await main.getByText("More options").click();
    await main.getByLabel(/^Another service that speaks/).check();
    await main.getByRole("textbox", { name: "Address" }).fill(info.ai_base_url);
    await main.locator("#ai-key").fill("a-made-up-key");
    await main.getByRole("button", { name: "Check", exact: true }).click();
    const everyday = main.getByLabel("Model for everyday work");
    await expect(everyday.locator("option")).toHaveCount(2);
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
    await visit(page);
    const before = await requests();
    expect(before.work).toBe(0);
    await row.getByRole("button", { name: "Sign in to Example mail", exact: true }).click();

    // Signing in happens on the service's own page, which sends me back to the same screen. The service is asked once,
    // and the app proves the sign-in is its own. The answer's code and state are not left in the address.
    await expect(main.getByRole("heading", { level: 2, name: "Mail and calendar" })).toBeVisible();
    await expect(main.getByText(/Signed in as .+@example\.com/)).toBeVisible();
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
    const { mail, events, noted } = seen.recent_items;
    const handedIn = mail.length + events.length;
    expect(handedIn).toBeGreaterThan(0);
    expect(noted.length).toBeGreaterThan(0);

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

    // Nothing was chosen: the inbox and the calendar are read by themselves, with the next round of reading (up to a
    // minute). Meanwhile Today says nothing was checked yet.
    const agenda = page.getByRole("region", { name: "Agenda" });
    const came = page.getByRole("region", { name: "Came in" });
    // A sign-in reads its sources at once: the mail is there within seconds, not at the next minute's check.
    await expect(came.getByText(mail[0])).toBeVisible({ timeout: 10_000 });

    // Today lists the recent mail on Came in and today's meetings on the agenda; what is older or further off is not.
    for (const title of mail) await expect(came.getByText(title, { exact: true })).toBeVisible();
    for (const title of events) await expect(agenda.getByText(title, { exact: true })).toBeVisible();
    for (const title of noted) await expect(page.getByRole("main").getByText(title, { exact: true })).toHaveCount(0);
    seen = await service();
    expect(seen).toMatchObject({ mail_reads: 1, calendar_reads: 1, unauthorized: 0 });

    // Sources says what is read without my having chosen it, and who is signed in.
    await openView(page, "Sources");
    await expect(page.getByRole("heading", { level: 1, name: "Sources" })).toBeVisible();
    await expect(page.getByText(/Signed in as .+@example\.com/)).toBeVisible();
    await expect(page.getByText("Your inbox").first()).toBeVisible();
    await expect(page.getByText("Your calendar").first()).toBeVisible();
    await visit(page);

    // The first go: one line with the count of what was handed in and what it would cost. Nothing has been asked.
    await openView(page, "Today");
    const go = page.locator("li.line", { hasText: "Start the assistant" });
    await expect(go).toHaveCount(1);
    await expect(go).toContainText(new RegExp(`Start the assistant: ${handedIn} items, (about \\$\\d+\\.\\d\\d|less than a cent)`));
    await expect(go).toContainText("Nothing is spent until you press Go.");
    await visit(page);
    expect((await requests()).work).toBe(0);

    // Go: one request for each item handed in, each item once, and the line goes.
    await go.getByRole("button", { name: "Go", exact: true }).click();
    await expect(page.locator("li.line", { hasText: "Start the assistant" })).toHaveCount(0);
    await expect.poll(async () => (await requests()).work, { timeout: 60_000 }).toBe(handedIn);
    const asked = await requests();
    for (const title of [...mail, ...events]) {
      expect(asked.inputs.filter((input) => input.includes(title))).toHaveLength(1);
    }
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
    // My own words filed my action; what has no owner asks who it belongs to.
    await expect(page.getByRole("region", { name: "To do" })).toContainText("Send the venue list by 2026-11-02.");
    const catering = reviews.filter({ hasText: mail.find((title) => /quote/i.test(title)) ?? "" });
    const expander = catering.locator(".expander").first();
    if ((await expander.getAttribute("aria-expanded")) !== "true") await expander.click();
    await expect(catering.getByText("Who owns this?").first()).toBeVisible();
    await visit(page);
    await expect(page.getByText(/stopped, see why below/)).toHaveCount(0);
    expect((await requests()).work).toBe(handedIn);
    expect(await service()).toMatchObject({ unauthorized: 0, refused: 0 });
  });
});
