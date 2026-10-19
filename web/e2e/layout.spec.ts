// No screen is ever wider than the window (the project's UI rules): every main screen at the widths people use, holding long
// unbroken text from outside (the layout stress strings) in a title, a Today row, a failed read in Today's right column and
// the details pane. The layout server (`--layout-stress`) holds the records and the failed reads; the hand-in is made here.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";

const strings: Record<string, string> = Object.fromEntries(
  (JSON.parse(readFileSync(fileURLToPath(new URL("./fixtures/layout-strings.json", import.meta.url)), "utf8")) as Array<{ id: string; text: string }>).map(
    (s) => [s.id, s.text],
  ),
);

/** 1512 x 982 is the owner's laptop; the others are a phone, a tablet and three desktops. */
const SIZES = [
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1280, height: 800 },
  { width: 1512, height: 982 },
  { width: 1920, height: 1080 },
];

/** What shows the screen has its long text and has loaded, so a width is never measured on a page still empty. */
const SCREENS: Array<{ name: string; hash: string; ready: (page: Page) => Promise<void> }> = [
  {
    name: "Today",
    hash: "today",
    ready: async (page) => {
      await expect(page.getByRole("heading", { level: 2, name: "Needs you", exact: true })).toBeVisible();
      await expect(page.locator('[data-queue-line="review"]').first()).toBeVisible();
      await expect(page.locator("[data-source-problems]").first()).toBeVisible();
      await expect(page.locator("[data-source-problems]").first()).toContainText(strings["mail-01"].slice(0, 12));
    },
  },
  { name: "Follow-ups", hash: "work/followups", ready: (page) => heading(page, "Follow-ups") },
  { name: "What changed", hash: "work/changed", ready: (page) => heading(page, "What changed") },
  { name: "Outgoing", hash: "work/outgoing", ready: (page) => heading(page, "Drafts to approve") },
  { name: "Stages", hash: "work/stages", ready: (page) => heading(page, "Stages") },
  { name: "Projects", hash: "records/projects", ready: (page) => text(page, strings["token-02"]) },
  { name: "People", hash: "records/people", ready: (page) => text(page, strings["email-03"]) },
  { name: "Files", hash: "records/files", ready: (page) => heading(page, "Files") },
  { name: "Knowledge", hash: "records/knowledge", ready: (page) => heading(page, "Knowledge") },
  {
    name: "Sources",
    hash: "sources",
    ready: async (page) => {
      await heading(page, "Sources");
      await text(page, strings["mail-01"].slice(0, 12));
    },
  },
  { name: "Add-ons", hash: "addons", ready: (page) => heading(page, "Add-ons") },
  { name: "Settings", hash: "settings", ready: (page) => heading(page, "Settings") },
  // Each section of Settings, with its help beside the settings or under them.
  { name: "Settings: AI accounts", hash: "settings/ai", ready: (page) => section(page, "AI accounts") },
  { name: "Settings: Backups and sync", hash: "settings/backups", ready: (page) => section(page, "Backups and sync") },
  { name: "Settings: Today", hash: "settings/today", ready: (page) => section(page, "Today") },
  { name: "Settings: Appearance", hash: "settings/appearance", ready: (page) => section(page, "Appearance") },
  { name: "Settings: Lists", hash: "settings/lists", ready: (page) => section(page, "Lists") },
  { name: "Settings: Advanced", hash: "settings/advanced", ready: (page) => section(page, "Advanced") },
];

const section = (page: Page, name: string) => expect(page.getByRole("heading", { level: 2, name: new RegExp(`^${name}`) })).toBeVisible();
const heading = (page: Page, name: string) => expect(page.getByRole("heading", { level: 1, name, exact: true })).toBeVisible();
const text = (page: Page, words: string) => expect(page.getByText(words.slice(0, 12)).first()).toBeAttached();

/** How wide the page and its body are against the window, and what sticks out past it without making the page scroll
 * (content a parent clips is as bad: it is cut off). Fixed layers and anything inside a box that scrolls itself are the
 * box's own business. */
const overflow = (page: Page) =>
  page.evaluate(() => {
    const limit = window.innerWidth;
    const scrolls = (el: Element | null): boolean => {
      for (; el; el = el.parentElement) if (/auto|scroll/.test(getComputedStyle(el).overflowX)) return true;
      return false;
    };
    const cut: string[] = [];
    for (const el of Array.from(document.querySelectorAll("body *"))) {
      const box = el.getBoundingClientRect();
      const parent = el.parentElement!.getBoundingClientRect();
      if (box.width > 0 && box.height > 0 && box.right > limit + 1 && parent.right <= limit + 1 && getComputedStyle(el).position !== "fixed" && !scrolls(el)) {
        cut.push(`${el.tagName.toLowerCase()}.${String(el.className).split(" ")[0]} reaches ${Math.round(box.right)}`);
      }
    }
    return { window: limit, page: document.documentElement.scrollWidth, body: document.body.scrollWidth, cut: cut.slice(0, 5) };
  });

const tooWide = (found: Awaited<ReturnType<typeof overflow>>) => found.page > found.window || found.body > found.window || found.cut.length > 0;

test.describe("no screen is wider than the window", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("?token=e2e-token");
    await expect(page.getByRole("heading", { level: 2, name: "Needs you", exact: true })).toBeVisible();
    // The assistant's work on a note: a Today line to review, whose items the details pane shows.
    const handed = await page.request.post("api/handin", { data: { note: strings["web-02"] } });
    expect(handed.ok()).toBe(true);
    // Today holds a new line back behind "new · Show" until a page load, so wait for it by what the server says.
    await expect
      .poll(async () => ((await (await page.request.get("api/today/queue")).json()) as Array<{ kind: string }>).some((line) => line.kind === "review"), {
        timeout: 30_000,
      })
      .toBe(true);
  });

  test("every main screen, and the details pane, at every width", async ({ page }) => {
    const wide: string[] = [];
    for (const size of SIZES) {
      await page.setViewportSize(size);
      // One page load per width: the screens change by the address's fragment, which is how the app moves between them.
      await page.goto("?token=e2e-token");
      for (const screen of SCREENS) {
        await page.evaluate((hash) => {
          window.location.hash = hash;
        }, screen.hash);
        await screen.ready(page);
        const found = await overflow(page);
        if (tooWide(found)) wide.push(`${screen.name} at ${size.width}: ${JSON.stringify(found)}`);
      }
      // The details pane: the review line opened to look closer, beside the queue or in place of its row.
      await page.evaluate(() => {
        window.location.hash = "today";
      });
      const review = page.locator('[data-queue-line="review"]').first();
      await expect(review).toBeVisible();
      await review.getByRole("button", { name: /^More actions for/ }).click();
      await page.getByRole("menuitem", { name: "Look closer" }).click();
      await expect(page.getByText(strings["web-02"].slice(0, 12)).first()).toBeVisible();
      const found = await overflow(page);
      if (tooWide(found)) wide.push(`Details at ${size.width}: ${JSON.stringify(found)}`);
    }
    expect(wide).toEqual([]);
  });
});
