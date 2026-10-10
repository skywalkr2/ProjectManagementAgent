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
    await expect(section.getByRole("button", { name: "Mark sent" })).toBeVisible();
    await section.getByRole("button", { name: "Mark sent" }).click();
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
    // Let the stage rows arrive first, so no row appears above the one under test.
    await expect(page.locator(".kind", { hasText: "Ready to move on" }).first()).toBeVisible();
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

  test("people and projects are set up from the screen, with undo", async ({ page }) => {
    await signIn(page);
    await page.getByRole("button", { name: "People & projects" }).click();
    await expect(page.getByRole("heading", { name: "People" })).toBeVisible();
    await page.getByRole("button", { name: "Add a person" }).click();
    await page.getByLabel(/Full name/).fill("Test Person");
    await page.getByLabel(/^Role/).fill("Proofreader");
    await page.locator("form").getByRole("button", { name: "Add a person" }).click();
    const row = page.locator("li.line", { hasText: "Test Person" });
    await expect(row).toContainText("Proofreader");
    await row.getByRole("button", { name: "Edit" }).click();
    await row.getByLabel(/Full name/).fill("Renamed Person");
    await row.getByRole("button", { name: "Save" }).click();
    await expect(page.locator("li.line", { hasText: "Renamed Person" })).toBeVisible();
    await page.getByRole("button", { name: "Undo" }).last().click();
    await expect(page.locator("li.line", { hasText: "Test Person" })).toBeVisible();
    await checkAccessibility(page);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
    await page.getByRole("button", { name: "Today" }).click();
    await expect(page.getByRole("heading", { name: "What changed" })).toBeVisible();
  });

  test("items move through stages from Stages and Today, with undo", async ({ page }) => {
    await signIn(page);
    const before: Array<{ title: string; ready: boolean; current_label: string | null; next: { label: string } | null }> =
      await (await page.request.get("api/stages/records")).json();
    const item = before.find((v) => v.ready && v.next)!;
    await page.getByRole("button", { name: "Stages" }).click();
    await expect(page.locator("li.line", { hasText: item.title }).first()).toBeVisible();
    await checkAccessibility(page);
    const row = page.locator("li.line", { hasText: item.title }).first();
    await expect(row.locator(".kind")).toHaveText(item.current_label ?? "Not started");
    await row.getByRole("button", { name: `Move to ${item.next!.label}` }).click();
    await expect(page.getByText(`Moved ${item.title} to ${item.next!.label}.`)).toBeVisible();
    await expect(row.locator(".kind")).toHaveText(item.next!.label);
    await page.getByRole("button", { name: "Undo" }).last().click();
    await expect(row.locator(".kind")).toHaveText(item.current_label ?? "Not started");
    await row.getByRole("button", { name: /More actions for/ }).click();
    await page.getByRole("menuitem", { name: "History" }).click();
    await expect(row.getByRole("list", { name: "Where it has been" })).toContainText("by undo");
    await checkAccessibility(page);

    await page.getByRole("button", { name: "Today" }).click();
    const ready = page.locator("li.line", { hasText: `${item.title} is ready for ${item.next!.label}` });
    await expect(ready).toBeVisible();
    await ready.getByRole("button", { name: `Move to ${item.next!.label}` }).click();
    await expect(ready).toHaveCount(0);
    await checkAccessibility(page);
  });

  test("a stage task waits for the person's go on Stages and Today, and Go approves it", async ({ page }) => {
    await signIn(page);
    // Walk items forward through the API until a stage task is waiting for the go.
    const waitingTasks = async () =>
      ((await (await page.request.get("api/stages/requests")).json()) as Array<Record<string, any>>).filter(
        (r) => r.approval === "required" && r.state === "needs_you",
      );
    for (let pass = 0; pass < 6 && (await waitingTasks()).length === 0; pass++) {
      const views: Array<Record<string, any>> = await (await page.request.get("api/stages/records")).json();
      for (const v of views.filter((x) => x.ready && x.next)) {
        await page.request.post("api/stages/move", { data: { record: v.record, to: v.next.id, read_version: v.version } });
        if ((await waitingTasks()).length) break;
      }
    }
    const task = (await waitingTasks())[0];
    const item = (
      (await (await page.request.get("api/stages/records")).json()) as Array<{ record: { kind: string; id: string }; title: string }>
    ).find((v) => v.record.kind === task.stage_start.kind && v.record.id === task.stage_start.record)!;
    await page.reload();
    await expect(page.getByRole("heading", { name: "What changed" })).toBeVisible();
    const today = page.locator("li.line", { hasText: `${item.title}: ` }).filter({ hasText: "is waiting for your go" });
    await expect(today).toBeVisible();
    await expect(today).not.toContainText(task.id);
    await checkAccessibility(page);
    await page.getByRole("button", { name: "Stages" }).click();
    const here = page.locator("li.line", { hasText: item.title }).first();
    await expect(here.getByRole("list", { name: "Waiting for your go" })).toContainText("is waiting for your go");
    await checkAccessibility(page);
    await here.getByRole("button", { name: "Go", exact: true }).click();
    await expect(page.getByText(/Approved\./)).toBeVisible();
    await expect(here.getByRole("list", { name: "Waiting for your go" })).toHaveCount(0);
    await page.getByRole("button", { name: "Today" }).click();
    await expect(page.getByRole("heading", { name: "What changed" })).toBeVisible();
    await expect(page.locator("li.line", { hasText: `${item.title}: ` }).filter({ hasText: "is waiting for your go" })).toHaveCount(0);
  });

  test("a phone-sized screen shows stages in one column", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page);
    await page.getByRole("button", { name: "Stages" }).click();
    await expect(page.locator("li.line").first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    await checkAccessibility(page);
  });

  test("nothing broke the content security policy or threw", async () => {
    expect(problems.filter((p) => !p.includes("Failed to load resource"))).toEqual([]);
  });
});
