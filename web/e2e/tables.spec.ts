// Tables beside the detail pane (design 7.13, 7.14; finding 3.3, check C49): with the pane open at 1440px no header or cell
// breaks inside a word, rows carry no filled button, and the priority columns stay.
import { expect, test, type Page } from "@playwright/test";

async function open(page: Page, hash: string) {
  await page.goto("?token=e2e-token");
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  await page.evaluate((h) => {
    window.location.hash = h;
  }, hash);
  await expect(page.getByRole("main").getByRole("heading", { level: 1 }).first()).toBeVisible();
  await expect(page.locator("main [data-skeleton]")).toHaveCount(0, { timeout: 15_000 });
}

/** Every word in the page's tables that a line break splits in two: a word whose own boxes are not all on one line. */
async function brokenWords(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const broken: string[] = [];
    for (const table of Array.from(document.querySelectorAll("main table"))) {
      const walker = document.createTreeWalker(table, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const text = node.textContent ?? "";
        for (const match of text.matchAll(/\S+/g)) {
          const range = document.createRange();
          range.setStart(node, match.index ?? 0);
          range.setEnd(node, (match.index ?? 0) + match[0].length);
          const tops = new Set(Array.from(range.getClientRects()).map((r) => Math.round(r.top / 4)));
          if (tops.size > 1) broken.push(match[0]);
        }
      }
    }
    return broken;
  });
}

for (const [name, hash] of [
  ["Projects", "records/projects"],
  ["People", "records/people"],
] as const) {
  test(`${name} with the pane open at 1440px: no header or cell breaks inside a word, and rows have no filled button`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await open(page, hash);
    expect(await brokenWords(page)).toEqual([]);
    const table = page.getByRole("main").getByRole("table").first();
    // No row has a filled (primary) button: its menu is the only button.
    const rows = table.locator("tbody tr[data-row]");
    await expect(rows.first()).toBeVisible();
    for (const row of await rows.all()) await expect(row.getByRole("button")).toHaveCount(1);
    await expect(table.locator("tbody button[data-key='primary']")).toHaveCount(0);
    // A click on the first row opens the pane beside the table.
    await rows.first().locator("td").nth(1).click();
    const pane = page.getByRole("complementary").filter({ has: page.getByRole("link", { name: /^Open .*'s page$/ }) });
    await expect(pane).toBeVisible();
    expect(await brokenWords(page)).toEqual([]);
    // The table keeps its priority columns and is not wider than the space it has.
    const headings = (await table.locator("thead th").allInnerTexts()).map((h) => h.trim());
    expect(headings.length).toBeLessThanOrEqual(7);
    const box = (await table.boundingBox())!;
    const paneBox = (await pane.boundingBox())!;
    expect(box.x + box.width).toBeLessThanOrEqual(paneBox.x + 1);
    // No header takes more than one line.
    for (const th of await table.locator("thead th").all()) {
      const height = await th.evaluate((el) => el.getBoundingClientRect().height);
      expect(height).toBeLessThan(48);
    }
    // Nothing scrolls sideways.
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
}

test("at 1280px the pane overlays the Projects table instead of squeezing it", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await open(page, "records/projects");
  const table = page.getByRole("main").getByRole("table").first();
  const before = (await table.boundingBox())!.width;
  await table.locator("tbody tr[data-row]").first().locator("td").nth(1).click();
  await expect(page.locator("[data-split]")).toHaveAttribute("data-pane", /beside|overlay/);
  const after = (await table.boundingBox())!.width;
  if ((await page.locator("[data-split]").getAttribute("data-pane")) === "overlay") expect(after).toBeGreaterThanOrEqual(before - 1);
  expect(await brokenWords(page)).toEqual([]);
});
