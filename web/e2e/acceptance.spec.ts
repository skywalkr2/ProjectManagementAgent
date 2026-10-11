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
  await page.getByRole("button", { name: "Hand something in" }).first().click();
  const box = page.getByLabel("Paste or type it here");
  if (c.pasted) {
    // Someone else's words are the default; what to do with them is the optional line.
    await box.fill(c.pasted);
    if (c.note) await page.getByLabel(/Anything to do with it/).fill(c.note);
  } else {
    await page.locator("label.radio", { hasText: "Mine" }).click();
    await box.fill(c.note ?? "");
  }
  await page.getByRole("button", { name: "Hand in", exact: true }).click();
  const row = page.locator("li.line", { hasText: firstLine(c.pasted ?? c.note ?? "") });
  await expect(row.locator(".kind").first()).toHaveText(/Review/i, { timeout: 20_000 });
  const expander = row.locator(".expander").first();
  if ((await expander.getAttribute("aria-expanded")) !== "true") await expander.click();
  return row;
}

async function checkAccessibility(page: Page) {
  // The header sticks to the top, so what it covers depends on the scroll position; check from the top.
  await page.evaluate(() => window.scrollTo(0, 0));
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

  test("a new workspace shows the first-run card and what the assistant needs", async ({ page }) => {
    await signIn(page);
    const card = page.getByRole("region", { name: "Start here" });
    await expect(card).toBeVisible();
    const steps = card.getByRole("listitem");
    await expect(steps).toHaveCount(3);
    await expect(steps.nth(0)).toContainText("Not done yet");
    await expect(page.getByText("The assistant is a stand-in for trying the app")).toBeVisible();
    await expect(page.getByText("Add an account in your AI settings, then run the connection test: cockpit ai test")).toBeVisible();
    await checkAccessibility(page);
    // Each step opens the setup guide at that step, with focus on its heading.
    await card.getByRole("button", { name: "Set up: Hand in a first note" }).click();
    await expect(page.getByRole("heading", { name: "Hand in a first note" })).toBeFocused();
    await checkAccessibility(page);
    await page.locator('[data-step="first_note"]').getByRole("button", { name: "Hand something in" }).click();
    await expect(page.getByLabel("Paste or type it here")).toBeFocused();
    await checkAccessibility(page);
    await page.getByRole("button", { name: "Cancel" }).click();
    await page.locator('[data-step="people"]').getByRole("button", { name: "Open People & projects" }).click();
    await expect(page.getByRole("heading", { name: "People", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Today" }).click();
    await card.getByRole("button", { name: "Hide this" }).click();
    await expect(card).toHaveCount(0);
    await page.reload();
    await expect(page.getByRole("heading", { name: "What changed" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Start here" })).toHaveCount(0);
  });

  test("the setup guide and Settings are screens of their own, and pass the accessibility checks", async ({ page }) => {
    await signIn(page);
    await page.getByRole("button", { name: "Settings" }).click();
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Workspace name" })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Seconds a message stays on screen" })).toBeVisible();
    await checkAccessibility(page);
    await page.getByRole("button", { name: "More settings" }).click();
    await expect(page.getByRole("button", { name: "Fewer settings" })).toHaveAttribute("aria-expanded", "true");
    await checkAccessibility(page);
    await page.getByRole("searchbox", { name: "Search settings" }).fill("backup");
    await expect(page.getByRole("textbox", { name: "Hours between backups" })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Workspace name" })).toHaveCount(0);
    await page.getByRole("button", { name: "Open the setup guide" }).click();
    await expect(page.getByRole("heading", { name: "Set up", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Add an AI account and test it" })).toBeVisible();
    await page.getByRole("radio").first().check();
    await expect(page.getByRole("heading", { name: "Get a key" })).toBeVisible();
    await expect(page.getByLabel("Key", { exact: true })).toBeVisible();
    await page.getByText("Advanced", { exact: true }).click();
    await expect(page.getByLabel("Account name")).toBeVisible();
    await checkAccessibility(page);
    await page.getByRole("button", { name: "Choose…" }).click();
    await expect(page.getByRole("dialog", { name: "Choose a folder" })).toBeVisible();
    await checkAccessibility(page);
    await page.getByRole("button", { name: "Cancel" }).click();
    await page.getByRole("button", { name: "Today" }).click();
  });

  test("a demo workspace says so on every screen, and feedback is a mail draft the person sends", async ({ page }) => {
    await signIn(page);
    const strip = page.getByRole("complementary", { name: "Demo workspace" });
    await expect(strip).toBeVisible();
    await expect(strip).toContainText("Everything here is made up. Nothing you do here reaches anyone.");
    await page.getByRole("button", { name: "Settings" }).click();
    await expect(strip).toBeVisible();
    // The strip never makes a phone-width page scroll sideways.
    await page.setViewportSize({ width: 360, height: 740 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await page.setViewportSize({ width: 1280, height: 800 });
    await checkAccessibility(page);

    const open = page.getByRole("button", { name: "Send feedback" });
    await expect(page.getByText(/^Version /)).toBeVisible();
    await open.click();
    const dialog = page.getByRole("dialog", { name: "Send feedback" });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("What happened, or what would help?").fill("The page was slow");
    await expect(dialog.getByLabel("Subject")).toHaveValue("Feedback on PM Cockpit");
    await expect(dialog.getByLabel("Message")).toHaveValue(/^The page was slow\n\nApp version: .+\nScreen: Settings$/);
    await expect(dialog.getByRole("link", { name: "Open in your mail" })).toHaveAttribute("href", /^mailto:/);
    await checkAccessibility(page);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(open).toBeFocused();
    await page.getByRole("button", { name: "Today" }).click();
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

  test("a note handed in as the person's own is filed under its project and found there", async ({ page }) => {
    await signIn(page);
    const projects: Array<{ id: string; name: string }> = await (await page.request.get("api/projects")).json();
    const loose = await handIn(page, { id: "loose-note", note: "Keep this one for later" });
    await expect(loose.locator("li.child", { hasText: "Filed a note (no project)" })).toHaveCount(1);
    const row = await handIn(page, { id: "own-note", note: "Keep this under the project, for later" });
    const first = projects[0];
    await expect(row.locator("li.child", { hasText: `Filed a note under ${first.name}` })).toHaveCount(1);
    await page.getByRole("button", { name: "People & projects" }).click();
    const project = page.locator("li.line", { hasText: first.name });
    await project.getByRole("button", { name: /More actions for/ }).click();
    await page.getByRole("menuitem", { name: /^Notes \(\d+\)$/ }).click();
    await expect(project.locator("ul.notes")).toContainText("Noted.");
    await expect(page.getByRole("heading", { name: "Notes not filed under a project" })).toBeVisible();
    await checkAccessibility(page);
  });

  test("4. Follow-ups: copy one clean message, then Mark sent, with Undo; sent items wait under their own filter", async ({ page }) => {
    await signIn(page);
    const ownerId = (byId("production-checkin").expect![0].owners as string[])[0];
    const owner = people.find((p) => p.id === ownerId)!;
    const section = page.locator("li.line", { has: page.locator("strong", { hasText: new RegExp(`^${owner.name}$`) }) });
    await section.getByRole("button", { name: /^Copy \d+$/ }).click();
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    expect(copied.startsWith(copied.split("\n")[0])).toBe(true);
    expect(copied).toContain(owner.name.split(" ")[0]);
    expect(copied).not.toMatch(/ACT-|Q-\d|PER-/);
    // Copying changes nothing on the server: the card stays under To send and now offers Mark sent.
    await expect(section.getByRole("button", { name: "Mark sent" }).first()).toBeVisible();
    await expect(page.getByText(`Marked as sent to ${owner.name}`)).toHaveCount(0);
    await section.getByRole("button", { name: "Mark sent" }).first().click();
    await expect(page.getByText(`Marked as sent to ${owner.name}`)).toBeVisible();
    // Sent items leave "To send" and wait under "Waiting on them", one line each.
    await expect(section).toHaveCount(0);
    await page.getByRole("button", { name: "Waiting on them" }).click();
    const waiting = page.locator("li.line", { has: page.getByRole("heading", { name: owner.name }) });
    await expect(waiting).toContainText(/sent (today|.* \(\d+ days?\))/);
    await expect(waiting.getByRole("button", { name: "They finished it" }).first()).toBeVisible();
    await checkAccessibility(page);
    await page.getByRole("button", { name: "To send" }).click();
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
    await expect(page.locator("[data-row]").first()).toBeVisible();
    await page.keyboard.press("j");
    // Lists load in their own time, so which row is first can change; what matters is that j put focus on a row.
    await expect(page.locator("[data-row]:focus")).toHaveCount(1);
    await page.keyboard.press("?");
    await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible();
    await checkAccessibility(page);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.keyboard.press("n");
    await expect(page.getByLabel("Paste or type it here")).toBeFocused();
  });

  test("Sources and the Ask box pass the accessibility checks, and the Ask box opens from the keyboard", async ({ page }) => {
    await signIn(page);
    await page.getByRole("button", { name: "Sources" }).click();
    await expect(page.getByRole("heading", { name: "Sources", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Auto-closed" })).toBeVisible();
    await checkAccessibility(page);
    // The Ask box: focus goes to the question, Escape closes it, and focus returns to the button that opens it.
    const opener = page.getByRole("button", { name: "Ask", exact: true });
    await opener.click();
    const dialog = page.getByRole("dialog", { name: /^Ask / });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel("Your question")).toBeFocused();
    await expect(dialog.getByRole("button", { name: "Ask", exact: true })).toBeDisabled();
    await checkAccessibility(page);
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(opener).toBeFocused();
    // The shortcut opens it too, but not while typing in a field.
    await page.keyboard.press("/");
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("Your question").fill("a/b");
    await expect(dialog.getByLabel("Your question")).toHaveValue("a/b");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: "Today" }).click();
    await expect(page.getByRole("heading", { name: "What changed" })).toBeVisible();
  });

  test("a phone-sized screen has one column and no sideways scrolling", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page);
    expect(await page.evaluate(() => document.documentElement.hasAttribute("data-narrow"))).toBe(true);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await checkAccessibility(page);
  });

  test("on a laptop-sized window Today shows its four columns at once, with no page scroll", async ({ page }) => {
    await page.setViewportSize({ width: 1512, height: 860 });
    await signIn(page);
    // The first-run card and the assistant's notice are on screen too: the board still fits beneath them.
    await expect(page.getByRole("region", { name: "Start here" })).toBeVisible();
    for (const name of ["Agenda", "To do", "Needs you", "Came in"]) {
      const heading = page.getByRole("heading", { level: 2, name, exact: true });
      await expect(heading).toBeVisible();
      await expect(heading).toBeInViewport({ ratio: 1 });
    }
    const boxes = await Promise.all(
      ["agenda", "todo", "needs", "arrived"].map((id) => page.locator(`[data-col="${id}"]`).boundingBox()),
    );
    // Side by side, in reading order, and inside the window.
    for (const [i, box] of boxes.entries()) {
      expect(box).not.toBeNull();
      expect(box!.y + box!.height).toBeLessThanOrEqual(860);
      if (i > 0) expect(box!.x).toBeGreaterThan(boxes[i - 1]!.x);
    }
    expect(await page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight)).toBeLessThanOrEqual(1);
    await checkAccessibility(page);
  });

  test("a mid-sized window pairs the columns, and a phone stacks them with the page scrolling", async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 800 });
    await signIn(page);
    const at = async (id: string) => (await page.locator(`[data-col="${id}"]`).boundingBox())!;
    const [agenda, todo, needs, arrived] = [await at("agenda"), await at("todo"), await at("needs"), await at("arrived")];
    expect(todo.x).toBe(agenda.x);
    expect(todo.y).toBeGreaterThan(agenda.y);
    expect(needs.x).toBeGreaterThan(agenda.x);
    expect(arrived.x).toBe(needs.x);
    expect(arrived.y).toBeGreaterThan(needs.y);
    await checkAccessibility(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.locator("html")).toHaveAttribute("data-narrow", "");
    const column = async (id: string) => (await page.locator(`[data-col="${id}"]`).boundingBox())!;
    const [a, b, c, d] = [await column("agenda"), await column("todo"), await column("needs"), await column("arrived")];
    expect(b.y).toBeGreaterThan(a.y + a.height - 1);
    expect(c.y).toBeGreaterThan(b.y + b.height - 1);
    expect(d.y).toBeGreaterThan(c.y + c.height - 1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
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
    // The rename's own toast, not whichever Undo happens to be last on screen.
    const renamed = page.getByRole("region", { name: "Notifications" }).locator("div", { hasText: /^Saved Renamed Person/ });
    await renamed.getByRole("button", { name: "Undo" }).click();
    await expect(page.locator("li.line", { hasText: "Test Person" })).toBeVisible();
    await checkAccessibility(page);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
    await page.getByRole("button", { name: "Today" }).click();
    await expect(page.getByRole("heading", { name: "What changed" })).toBeVisible();
  });

  test("a value added to the project status list from a project form is selected, and still there after a reload", async ({ page }) => {
    await signIn(page);
    await page.getByRole("button", { name: "People & projects" }).click();
    await page.getByRole("button", { name: "Add a project" }).click();
    const form = page.locator("form.setup-form");
    await form.getByRole("textbox", { name: "Name" }).fill("Listed project");
    const status = form.getByRole("combobox", { name: "Status" });
    await expect(status.locator("option")).toContainText(["Not set", "Add to the list…"]);
    await status.selectOption({ label: "Add to the list…" });
    const field = form.getByRole("textbox", { name: "Add a value to Project status" });
    await expect(field).toBeFocused();
    await field.fill("Parked for now");
    await checkAccessibility(page);
    // Enter adds the value; it does not send the project.
    await field.press("Enter");
    await expect(status).toHaveValue("Parked for now");
    await expect(page.getByRole("region", { name: "Notifications" })).toContainText("Added Parked for now to Project status.");
    await form.getByRole("button", { name: "Add a project" }).click();
    const row = page.locator("li.line", { hasText: "Listed project" });
    await expect(row).toContainText("Parked for now");
    await page.reload();
    await page.getByRole("button", { name: "People & projects" }).click();
    const again = page.locator("li.line", { hasText: "Listed project" });
    await expect(again).toContainText("Parked for now");
    await again.getByRole("button", { name: "Edit" }).click();
    await expect(again.getByRole("combobox", { name: "Status" })).toHaveValue("Parked for now");
    await checkAccessibility(page);
  });

  test("Settings lists the value lists, and a value can be renamed and stopped being offered", async ({ page }) => {
    await signIn(page);
    await page.getByRole("button", { name: "Settings" }).click();
    const lists = page.getByRole("region", { name: "Lists" });
    await expect(lists).toBeVisible();
    const status = lists.locator("li.line", { hasText: "Project status" });
    await expect(status).toContainText("Used for: project status");
    await expect(status.getByText("Parked for now", { exact: true })).toBeVisible();
    await checkAccessibility(page);
    await status.getByRole("button", { name: /More actions for Parked for now/ }).click();
    await page.getByRole("menuitem", { name: "Rename" }).click();
    const rename = status.getByRole("textbox", { name: "New name for Parked for now" });
    await rename.fill("On the shelf");
    await rename.press("Enter");
    await expect(status.getByText("On the shelf", { exact: true })).toBeVisible();
    await status.getByRole("button", { name: /More actions for On the shelf/ }).click();
    await page.getByRole("menuitem", { name: "Stop offering" }).click();
    await status.getByRole("button", { name: /No longer offered/ }).click();
    await expect(status.locator(".list-value", { hasText: "On the shelf" })).toBeVisible();
    await expect(status.getByRole("button", { name: "Offer again On the shelf" })).toBeVisible();
    await checkAccessibility(page);
  });

  test("items move through stages from Stages and Today, with undo", async ({ page }) => {
    await signIn(page);
    const before: Array<{
      title: string;
      ready: boolean;
      current_label: string | null;
      next: { id: string; label: string } | null;
      stages: Array<{ id: string; label: string }>;
    }> = await (await page.request.get("api/stages/records")).json();
    const item = before.find((v) => v.ready && v.next && !v.current_label)!;
    // Today only suggests moving on for an item already in a stage: the one after the first.
    const following = item.stages[item.stages.findIndex((s) => s.id === item.next!.id) + 1];
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

    // Not started yet: Stages offers the first stage, Today stays quiet about it.
    await page.getByRole("button", { name: "Today" }).click();
    await expect(page.getByRole("heading", { name: "What changed" })).toBeVisible();
    await expect(page.locator("li.line", { hasText: `${item.title} is ready for` })).toHaveCount(0);
    await page.getByRole("button", { name: "Stages" }).click();
    await row.getByRole("button", { name: `Move to ${item.next!.label}` }).click();
    await expect(row.locator(".kind")).toHaveText(item.next!.label);

    await page.getByRole("button", { name: "Today" }).click();
    const ready = page.locator("li.line", { hasText: `${item.title} is ready for ${following.label}` });
    await expect(ready).toBeVisible();
    await ready.getByRole("button", { name: `Move to ${following.label}` }).click();
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

  test("files are added from the screen, and an action on one is reviewed, applied and undone", async ({ page }) => {
    await signIn(page);
    await page.getByRole("button", { name: "Files" }).click();
    await expect(page.getByRole("heading", { name: "Files", exact: true })).toBeVisible();
    await checkAccessibility(page);
    const first = "A line to make a note from";
    const body = `\n${first}\nand a second line\n`;
    const words = body.split(/\s+/).filter(Boolean).length;
    const opener = page.getByRole("button", { name: "Add a file" });
    await opener.click();
    const dialog = page.getByRole("dialog", { name: "Add a file" });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel("File").setInputFiles({ name: "short-note.txt", mimeType: "text/plain", buffer: Buffer.from(body) });
    await dialog.getByLabel(/^Description/).fill("Written by the browser test");
    await checkAccessibility(page);
    await dialog.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByText("Added short-note.txt.")).toBeVisible();
    await expect(dialog).toHaveCount(0);
    await expect(opener).toBeFocused();
    const row = page.locator("li.line", { hasText: "short-note.txt" });
    await expect(row).toContainText("Attachment");
    await expect(row.getByRole("link", { name: /^Open short-note\.txt/ })).toHaveAttribute("target", "_blank");
    await checkAccessibility(page);

    await row.getByRole("button", { name: /More actions for/ }).click();
    await page.getByRole("menuitem", { name: "Make a note from this file" }).click();
    const review = page.getByRole("dialog", { name: "Make a note from short-note.txt" });
    await expect(review).toContainText(`${first} (${words} words)`);
    await review.getByRole("checkbox", { name: "Include the word count" }).uncheck();
    await expect(review.getByText(first, { exact: true })).toBeVisible();
    await expect(review.getByRole("checkbox", { name: "Include the word count" })).toBeFocused();
    await checkAccessibility(page);
    await review.getByRole("button", { name: "Apply" }).click();
    await expect(page.getByText("Make a note from short-note.txt: 1 change made.")).toBeVisible();
    await expect(review).toHaveCount(0);
    const notes: Array<{ text: string }> = await (await page.request.get("api/notes")).json();
    expect(notes.map((n) => n.text)).toContain(first);
    await page.getByRole("button", { name: "Undo" }).last().click();
    await expect(page.getByText("Undone. It's back as it was.")).toBeVisible();
    const after: Array<{ text: string }> = await (await page.request.get("api/notes")).json();
    expect(after.map((n) => n.text)).not.toContain(first);
  });

  test("a phone-sized screen shows files in one column", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page);
    await page.getByRole("button", { name: "Files" }).click();
    await expect(page.locator("li.line").first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    await checkAccessibility(page);
  });

  test("Add-ons opens from Settings, lists the bundled add-on under Installed, and passes the accessibility checks", async ({ page }) => {
    await signIn(page);
    await page.getByRole("button", { name: "Settings" }).click();
    await page.getByRole("button", { name: "Add-ons" }).click();
    await expect(page.getByRole("heading", { name: "Add-ons", exact: true })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Available" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText(/This copy of the app doesn't list a catalog/)).toBeVisible();
    await checkAccessibility(page);
    await page.getByRole("tab", { name: "Installed" }).click();
    await expect(page.getByRole("tab", { name: "Installed" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("listitem", { name: "example", exact: true })).toBeVisible();
    await checkAccessibility(page);
  });

  test("on a wide screen the Hand something in button stays on one line beside the views", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await signIn(page);
    const box = await page.getByRole("button", { name: "Hand something in" }).first().boundingBox();
    const tabs = await page.getByRole("navigation", { name: "Views" }).boundingBox();
    expect(box!.height).toBeLessThan(50);
    expect(Math.abs(box!.y - tabs!.y)).toBeLessThan(20);
  });

  test("nothing broke the content security policy or threw", async () => {
    expect(problems.filter((p) => !p.includes("Failed to load resource"))).toEqual([]);
  });
});
