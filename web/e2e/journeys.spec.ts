// Journey tests: a real person's path through the screens, from a workspace made by the init command with no template,
// started by the serve command, with fakes only at the outside services (tests/fake_services.py). The point is the joins
// between steps that a test of one step misses. Each journey is a numbered test saying what the person does.
// Names come from the fictional workspace the fake services serve, never written out here.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const FAKE = "http://127.0.0.1:8790";

interface Info {
  token: string;
  ai_base_url: string;
  people: string[];
  backup_folder: string;
  source_folder: string;
}
interface Requests {
  total: number;
  smoke: number;
  work: number;
}

let info: Info;
const problems: string[] = [];

const requests = async (): Promise<Requests> => (await fetch(`${FAKE}/__e2e/ai-requests`)).json();

async function checkAccessibility(page: Page) {
  // The header sticks to the top, so what it covers depends on the scroll position; check from the top.
  await page.evaluate(() => window.scrollTo(0, 0));
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  const found = results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  expect(found).toEqual([]);
}

/** What the person reads on the page: its text plus the words in its fields' placeholders, titles and labels. */
async function readScreen(page: Page): Promise<string> {
  return page.evaluate(() => {
    const words = [document.body.innerText];
    for (const el of Array.from(document.querySelectorAll("[placeholder],[title],[aria-label]"))) {
      for (const name of ["placeholder", "title", "aria-label"]) {
        const value = el.getAttribute(name);
        if (value) words.push(value);
      }
    }
    return words.join("\n");
  });
}

/** A screen the person sees: it names no settings file, secret reference or command, and passes the accessibility checks. */
async function visit(page: Page) {
  const text = await readScreen(page);
  expect(text).not.toMatch(/\.ya?ml\b/i);
  expect(text).not.toMatch(/\benv:/);
  expect(text).not.toMatch(/\bfile:\//);
  expect(text).not.toMatch(/\bcockpit /);
  await checkAccessibility(page);
}

const setupStep = (page: Page, name: string) => page.getByLabel(name, { exact: true });

test.describe.serial("journeys", () => {
  test.beforeAll(async () => {
    info = await (await fetch(`${FAKE}/__e2e/info`)).json();
  });

  test.afterAll(() => {
    expect(problems.filter((p) => !p.includes("Failed to load resource"))).toEqual([]);
  });

  test("J1. A new workspace: I name myself, add an AI account, hand in a note, press Go and see the result on Today", async ({
    page,
  }) => {
    page.on("console", (msg) => {
      if (msg.type() === "error") problems.push(msg.text());
    });
    page.on("pageerror", (err) => problems.push(String(err)));

    // I open the link the start command printed. Today is the home, and says setup has not begun.
    await page.goto(`?token=${info.token}`);
    await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
    await expect(page.getByText("Setup 0 of 7")).toBeVisible();
    await expect(page.getByRole("button", { name: /^Status: / })).toContainText("Backup needed");
    await visit(page);
    await page.getByRole("button", { name: "Continue setup" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Set up" })).toBeVisible();
    await visit(page);

    // The first step says who I am: the assistant needs a person to ask and to own my own actions.
    const me = setupStep(page, "Name the workspace and say who you are");
    await me.getByLabel("Workspace name").fill("Offsite team");
    await me.getByLabel("Your full name").fill(info.people[0]);
    await me.getByRole("button", { name: "Save" }).click();
    await expect(me.locator(".pill")).toContainText("Done");
    await visit(page);

    // The AI step: a service of my own that speaks the common chat format, at the address the fake service answers on.
    const ai = setupStep(page, "Add an AI account and test it");
    await ai.getByText("More options").click();
    await ai.getByLabel(/^Another service that speaks/).check();
    await ai.getByRole("textbox", { name: "Address" }).fill(info.ai_base_url);
    await ai.locator("#ai-key").fill("a-made-up-key");
    await ai.getByRole("button", { name: "Check", exact: true }).click();
    const everyday = ai.getByLabel("Model for everyday work");
    await expect(everyday.locator("option")).toHaveCount(2);
    await everyday.selectOption("fake-small");
    // The usual hand-in is internal material; an account only takes what it is allowed to see.
    await ai.getByLabel("Internal material").check();
    await visit(page);
    await ai.getByRole("button", { name: "Add account" }).click();
    await expect(ai.getByText("Everyday work: other — answered")).toBeVisible();
    await ai.getByRole("button", { name: "Test again" }).click();
    await expect(ai.getByText("Everyday work: other — answered")).toBeVisible();
    await expect(ai.getByText("Harder work: other — answered")).toBeVisible();
    await expect(ai.getByText(/not answer|failed/i)).toHaveCount(0);
    // Changing an account needs no restart, and the header says nothing is waiting for one.
    await expect(page.getByRole("button", { name: /^Status: / })).not.toContainText("Restart");
    await visit(page);
    const afterTest = await requests();
    expect(afterTest.work).toBe(0);
    expect(afterTest.smoke).toBeGreaterThan(0);

    // I hand in a short note of my own.
    await page.getByRole("button", { name: "Hand something in" }).first().click();
    await page.getByLabel("Paste or type it here").fill(
      "I will send the venue list by 2026-11-02.\nDecided: the offsite is on a Friday.\nWe need a catering quote.",
    );
    await visit(page);
    await page.getByRole("button", { name: "Hand in", exact: true }).click();

    // Today shows one line asking for my go, with a count and what it would cost. Nothing has been sent to the service.
    await page.getByRole("link", { name: /^Today/ }).first().click();
    const go = page.locator("li.line", { hasText: "Start the assistant" });
    await expect(go).toHaveCount(1);
    await expect(go).toContainText(/Start the assistant: 1 item, (about \$\d+\.\d\d|less than a cent)/);
    await expect(go).toContainText("Nothing is spent until you press Go.");
    await visit(page);
    expect(await requests()).toEqual(afterTest);

    // Go starts it, and the result is on Today: my action in To do, and the assistant's work to look over.
    await go.getByRole("button", { name: "Go", exact: true }).click();
    await expect(page.getByText("Send the venue list by 2026-11-02.").first()).toBeVisible({ timeout: 20_000 });
    await expect(page.locator("li.line", { hasText: "Start the assistant" })).toHaveCount(0);
    const review = page.locator("li.line", { hasText: "I will send the venue list" });
    await expect(review.getByText(/Assistant did 3 things/)).toBeVisible();
    expect((await requests()).work).toBe(1);
    await visit(page);

    // Opened, the review lists what the assistant did, with my name on the action it filed from my own words; the one
    // with no owner asks who it belongs to, and the hand-in did not stop anywhere.
    const expander = review.locator(".expander").first();
    if ((await expander.getAttribute("aria-expanded")) !== "true") await expander.click();
    await expect(review.getByText("Added an action").first()).toBeVisible();
    await expect(review.getByText(new RegExp(`${info.people[0]} · due`))).toBeVisible();
    await expect(review.getByText("Who owns this?")).toBeVisible();
    await visit(page);
    await expect(page.getByText(/stopped, see why below/)).toHaveCount(0);
  });

  test("J3. A folder I add on screen is read, a new file in it is handed in, and the assistant's result is on Today", async ({
    page,
  }) => {
    page.on("console", (msg) => {
      if (msg.type() === "error") problems.push(msg.text());
    });
    page.on("pageerror", (err) => problems.push(String(err)));
    await page.goto(`?token=${info.token}`);
    await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();

    // Sources: add a folder, pointing at the folder the test put the file in.
    await page.getByRole("navigation", { name: "Views" }).getByRole("link", { name: /^Sources/ }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Sources" })).toBeVisible();
    await page.getByRole("button", { name: /Add a source/ }).first().click();
    await page.getByLabel("A folder", { exact: true }).check();
    await page.getByLabel(/^The folder/).fill(info.source_folder);
    await visit(page);
    await page.getByRole("button", { name: "Add source", exact: true }).click();
    await expect(page.getByRole("listitem", { name: "A folder" })).toBeVisible();
    await visit(page);

    // Came in has Check now. The first read only notes what is there, so nothing is handed in yet.
    await page.getByRole("link", { name: /^Today/ }).first().click();
    const before = await requests();
    await page.getByRole("button", { name: "Check now" }).click();
    await expect(page.getByText(/^Checked /).last()).toBeVisible();
    await visit(page);
    expect(await requests()).toEqual(before);

    // A new file lands in the folder. Check now reads it, hands it in, and the assistant's result appears.
    const put = await fetch(`${FAKE}/__e2e/source-file`, {
      method: "POST",
      body: JSON.stringify({ text: "I will book the venue by 2026-11-05.\nWe need a printed agenda.\n" }),
    });
    expect(put.ok).toBe(true);
    await page.getByRole("button", { name: "Check now" }).click();
    await expect(page.getByText("Book the venue by 2026-11-05.").first()).toBeVisible({ timeout: 20_000 });
    expect((await requests()).work).toBe(before.work + 1);
    // The item that arrived is on What changed, named for the file.
    await page.getByRole("navigation", { name: "Views" }).getByRole("link", { name: /^What changed/ }).click();
    await expect(page.getByRole("heading", { level: 1, name: "What changed" })).toBeVisible();
    await expect(page.getByText(/folder-note\.txt/).first()).toBeVisible();
    await visit(page);
  });
});
