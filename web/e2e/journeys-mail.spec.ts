// Journey 2: a person signs in to their mail and calendar, the assistant reads what came in, and the results are on
// Today for review. A workspace made by the init command with no template, started by the serve command, with the mail
// add-on on (as one the person had already installed and turned on would be) and fakes only at the outside services
// (tests/fake_services.py): the AI service over plain HTTP, and the sign-in, mail and calendar services over HTTPS with
// a throwaway authority the app trusts through its environment.
// Names come from the fictional workspace the fake services serve, never written out here.
import { expect, test } from "@playwright/test";
import {
  collectProblems,
  fakeAddress,
  openView,
  setupStep,
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

    // A new workspace with the mail add-on on: Today says setup has begun with one more step than a bare workspace.
    await page.goto(`?token=${info.token}`);
    await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
    await expect(page.getByText("Setup 0 of 8")).toBeVisible();
    await page.getByRole("button", { name: "Continue setup" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Set up" })).toBeVisible();
    await visit(page);

    // Who I am, then an AI account, as in the first journey.
    const me = setupStep(page, "Name the workspace and say who you are");
    await me.getByLabel("Workspace name").fill("Offsite team");
    await me.getByLabel("Your full name").fill(info.people[0]);
    await me.getByRole("button", { name: "Save" }).click();
    await expect(me.locator(".pill")).toContainText("Done");
    const ai = setupStep(page, "Add an AI account and test it");
    await ai.getByText("More options").click();
    await ai.getByLabel(/^Another service that speaks/).check();
    await ai.getByRole("textbox", { name: "Address" }).fill(info.ai_base_url);
    await ai.locator("#ai-key").fill("a-made-up-key");
    await ai.getByRole("button", { name: "Check", exact: true }).click();
    const everyday = ai.getByLabel("Model for everyday work");
    await expect(everyday.locator("option")).toHaveCount(2);
    await everyday.selectOption("fake-small");
    await ai.getByLabel("Internal material").check();
    await ai.getByRole("button", { name: "Add account" }).click();
    await expect(ai.getByText("Everyday work: other — answered")).toBeVisible();
    await visit(page);

    // The sign-in is a step of the guide too. Nothing has been read, and nothing has asked the assistant anything.
    const signIn = page.getByRole("listitem", { name: "Sign in to Example mail" });
    await expect(signIn).toBeVisible();
    await visit(page);
    const before = await requests();
    expect(before.work).toBe(0);
    await signIn.getByRole("button", { name: "Sign in to Example mail", exact: true }).click();
    await expect(page.getByText("Signed in to Example mail.")).toBeVisible();
    // The person signed in on the service's own page: it asked once, and the app proved the sign-in was its own. The
    // answer's code and state are not left in the address.
    let seen = await service();
    expect(seen).toMatchObject({ authorizations: 1, exchanges: 1, refused: 0 });
    expect(page.url()).not.toMatch(/code=|state=|sign_in=/);
    await visit(page);
    const { mail, events, noted } = seen.recent_items;
    const handedIn = mail.length + events.length;
    expect(handedIn).toBeGreaterThan(0);
    expect(noted.length).toBeGreaterThan(0);

    // Nothing was chosen: the inbox and the calendar are read by themselves, with the next round of reading (up to a
    // minute). Meanwhile Today says nothing was checked yet.
    const agenda = page.getByRole("region", { name: "Agenda" });
    const came = page.getByRole("region", { name: "Came in" });
    await expect(came).toContainText("Not checked yet");
    await expect(came.getByText(mail[0])).toBeVisible({ timeout: 120_000 });

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
