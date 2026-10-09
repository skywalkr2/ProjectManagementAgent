// The milestone 2 acceptance scenario (docs/project/schedule.md) in a real browser, with accessibility checks.
// Names come from the fixture's cases and people, never written out here.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

interface Case {
  id: string;
  pasted?: string;
  note?: string;
  expect?: Array<Record<string, unknown>>;
}
interface Person {
  id: string;
  name: string;
  role: string | null;
}

let cases: Case[] = [];
let people: Person[] = [];
const problems: string[] = [];

const byId = (id: string) => cases.find((c) => c.id === id)!;
const firstLine = (text: string) => text.split("\n").find((l) => l.trim())!.trim();

async function signIn(page: Page) {
  page.on("console", (msg) => {
    if (msg.type() === "error") problems.push(msg.text());
  });
  page.on("pageerror", (err) => problems.push(String(err)));
  await page.goto("?token=e2e-token");
  await expect(page.getByRole("heading", { name: "What changed" })).toBeVisible();
}

async function handIn(page: Page, c: Case) {
  await page.getByRole("button", { name: "Hand something in" }).click();
  if (c.note) await page.getByLabel(/Your note/).fill(c.note);
  if (c.pasted) await page.getByLabel(/Pasted content/).fill(c.pasted);
  await page.getByRole("button", { name: "Hand in", exact: true }).click();
  const row = page.locator("li.line", { hasText: firstLine(c.pasted ?? c.note ?? "") });
  await expect(row.locator(".kind").first()).toHaveText(/Review/i, { timeout: 20_000 });
  const expander = row.locator(".expander").first();
  if ((await expander.getAttribute("aria-expanded")) !== "true") await expander.click();
  return row;
}

async function checkAccessibility(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  const found = results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  expect(found).toEqual([]);
}

test.describe.serial("acceptance scenario", () => {
  test.beforeAll(async ({ request, baseURL }) => {
    const origin = new URL(baseURL!).origin;
    cases = await (await request.get(`${origin}/__e2e/cases`)).json();
  });

  test("signing in, the backup nag, and a clean first screen", async ({ page }) => {
    await signIn(page);
    people = await (await page.request.get("api/people")).json();
    await expect(page.locator(".backup")).toContainText("No backup has succeeded yet");
    await checkAccessibility(page);
  });

  test("1. meeting notes become actions with owners, and a shared first name becomes a question", async ({ page }) => {
    await signIn(page);
    const notes = byId("production-checkin");
    const row = await handIn(page, notes);
    const actions = row.locator("li.child", { hasText: "Added an action" });
    await expect(actions).toHaveCount(notes.expect!.length);
    for (const e of notes.expect!) {
      const owners = (e.owners as string[]).map((id) => people.find((p) => p.id === id)!.name);
      const item = actions.filter({ hasText: (e.text_has as string[])[0] });
      for (const name of owners) await expect(item.locator(".meta")).toContainText(name);
      await expect(item.locator(".because q")).toBeVisible();
    }
    await row.getByRole("button", { name: "Show source" }).first().click();
    await expect(row.locator("mark").first()).toBeVisible();
    await checkAccessibility(page);
    await row.getByRole("button", { name: "Looks good" }).click();
    await expect(page.getByText("Filed. Marked as looked over.")).toBeVisible();

    const shared = await handIn(page, byId("shared-first-name"));
    const picker = shared.getByRole("combobox", { name: /Who is/ });
    await expect(picker.locator("optgroup").first().locator("option")).toHaveCount(2);
    const choice = await picker.locator("optgroup").first().locator("option").first().getAttribute("value");
    await picker.selectOption(choice!);
    await shared.getByRole("button", { name: "Use this person" }).click();
    await expect(shared.locator("li.child .pill")).toHaveCount(0);
  });

  test("2. a vendor's date becomes a fact, not a question", async ({ page }) => {
    await signIn(page);
    const row = await handIn(page, byId("printer-proof-date"));
    await expect(row.locator("li.child", { hasText: "Recorded a fact" })).toHaveCount(1);
    await expect(row.locator("li.child", { hasText: "Asked a question" })).toHaveCount(0);
  });

  test("3. an instruction inside pasted content is treated as content", async ({ page }) => {
    await signIn(page);
    const before = (await (await page.request.get("api/people")).json()).length;
    const row = await handIn(page, byId("hostile-standing-rule"));
    await expect(row.locator("li.child", { hasText: "Filed a note" })).toHaveCount(1);
    await expect(row.locator("li.child", { hasText: "Added a person" })).toHaveCount(0);
    expect((await (await page.request.get("api/people")).json()).length).toBe(before);
  });

  test("4. Follow-ups: one clean message per person, copied and marked sent", async ({ page }) => {
    await signIn(page);
    const ownerId = (byId("production-checkin").expect![0].owners as string[])[0];
    const owner = people.find((p) => p.id === ownerId)!;
    const section = page.locator("li.line", { has: page.locator("strong", { hasText: new RegExp(`^${owner.name}$`) }) });
    await section.getByRole("button", { name: /^Copy \d+$/ }).click();
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    expect(copied.startsWith(copied.split("\n")[0])).toBe(true);
    expect(copied).toContain(owner.name.split(" ")[0]);
    expect(copied).not.toMatch(/ACT-|Q-\d|PER-/);
    await page.getByRole("button", { name: "Mark sent" }).click();
    await expect(section).toContainText("nothing new to send");
    await page.getByRole("button", { name: "Undo" }).last().click();
    await expect(section.getByRole("button", { name: /^Copy \d+$/ })).toBeVisible();
  });

  test("5. undoing the vendor's date removes the fact", async ({ page }) => {
    await signIn(page);
    const row = page.locator("li.line", { hasText: firstLine(byId("printer-proof-date").pasted!) });
    await row.getByRole("button", { name: /More actions for/ }).first().click();
    await page.getByRole("menuitem", { name: "Undo everything it did" }).click();
    await expect(row.locator("li.child .pill")).toHaveText(/Undone/i);
  });

  test("7. after a backup succeeds the header shows its age", async ({ page }) => {
    await signIn(page);
    await page.getByRole("button", { name: "Back up now" }).click();
    await expect(page.locator(".backup")).toContainText("Backed up less than an hour ago");
  });

  test("the keyboard drives the review loop", async ({ page }) => {
    await signIn(page);
    const first = page.locator("[data-row]").first();
    await expect(first).toBeVisible();
    await page.keyboard.press("j");
    await expect(first).toBeFocused();
    await page.keyboard.press("?");
    await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
    await checkAccessibility(page);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.keyboard.press("n");
    await expect(page.getByLabel(/Your note/)).toBeFocused();
  });

  test("a phone-sized screen has one column and no sideways scrolling", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page);
    expect(await page.evaluate(() => document.documentElement.hasAttribute("data-narrow"))).toBe(true);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await checkAccessibility(page);
  });

  test("nothing broke the content security policy or threw", async () => {
    expect(problems.filter((p) => !p.includes("Failed to load resource"))).toEqual([]);
  });
});
