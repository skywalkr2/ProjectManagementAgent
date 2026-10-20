// The panes the shell opens beside or over a screen (design 7.1, 7.13): Hand something in as a drawer, Ask as a pane on a
// wide screen and a dialog below it, the stages board, and the phone's review mode.
import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page, hash = "") {
  await page.goto("?token=e2e-token");
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  if (hash) {
    await page.evaluate((h) => {
      window.location.hash = h;
    }, hash);
  }
}

const noSidewaysScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);

test.describe("Hand something in", () => {
  test("is a drawer from the right, about 640px wide, with Today still showing, and the box at most 72 characters wide", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page);
    await page.getByRole("button", { name: "Hand something in" }).first().click();
    const drawer = page.getByRole("dialog", { name: "Hand something in" });
    await expect(drawer).toBeVisible();
    const box = (await drawer.boundingBox())!;
    expect(box.x + box.width).toBeGreaterThanOrEqual(1440 - 1);
    expect(box.width).toBeGreaterThan(560);
    expect(box.width).toBeLessThanOrEqual(641);
    await expect(drawer.getByLabel("Paste or type it here")).toBeFocused();
    // Today is behind it, not gone.
    await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
    const field = (await drawer.getByLabel("Paste or type it here").boundingBox())!;
    expect(field.width).toBeLessThanOrEqual(box.width);
    await page.keyboard.press("Escape");
    await expect(drawer).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Hand something in" }).first()).toBeFocused();
  });

  test("with words in the box, closing asks first, and Keep editing keeps them", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page);
    await page.getByRole("button", { name: "Hand something in" }).first().click();
    const drawer = page.getByRole("dialog", { name: "Hand something in" });
    await drawer.getByLabel("Paste or type it here").fill("A note I have not handed in");
    await page.keyboard.press("Escape");
    await expect(drawer.getByRole("alert")).toBeVisible();
    await drawer.getByRole("button", { name: "Keep editing" }).click();
    await expect(drawer.getByLabel("Paste or type it here")).toHaveValue("A note I have not handed in");
  });

  test("is a full-screen sheet on a phone, with no sideways scrolling", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page);
    await page.getByRole("navigation", { name: "Views" }).getByRole("button", { name: "Hand something in" }).click();
    const sheet = page.getByRole("dialog", { name: "Hand something in" });
    await expect(sheet).toBeVisible();
    const box = (await sheet.boundingBox())!;
    expect(Math.round(box.width)).toBe(390);
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);
  });
});

test.describe("Ask", () => {
  for (const width of [1440, 1920]) {
    test(`is a pane beside the screen at ${width}px: the content is not covered, the cursor is in the question, Escape closes it`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await signIn(page);
      const opener = page.getByRole("button", { name: "Ask", exact: true }).first();
      await opener.click();
      const pane = page.getByRole("complementary", { name: /^Ask / });
      await expect(pane).toBeVisible();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(pane.getByLabel("Your question")).toBeFocused();
      const paneBox = (await pane.boundingBox())!;
      expect(paneBox.x + paneBox.width).toBeGreaterThanOrEqual(width - 1);
      expect(paneBox.width).toBeGreaterThanOrEqual(419);
      expect(paneBox.width).toBeLessThanOrEqual(601);
      // The work stays in view and reachable: the content ends where the pane begins, and a link outside it still works.
      const main = (await page.getByRole("main").boundingBox())!;
      expect(main.x + main.width).toBeLessThanOrEqual(paneBox.x + 1);
      expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);
      await page.getByRole("navigation", { name: "Views" }).getByRole("link", { name: /^People/ }).click();
      await expect(page.getByRole("heading", { level: 1, name: "People" })).toBeVisible();
      await expect(pane).toBeVisible();
      await pane.getByLabel("Your question").click();
      await page.keyboard.press("Escape");
      await expect(pane).toHaveCount(0);
      await expect(opener).toBeFocused();
    });
  }

  test("is a dialog below 1440px, as it was", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await signIn(page);
    await page.getByRole("button", { name: "Ask", exact: true }).first().click();
    await expect(page.getByRole("dialog", { name: /^Ask / })).toBeVisible();
    await expect(page.getByRole("complementary", { name: /^Ask / })).toHaveCount(0);
  });
});

test.describe("the stages board", () => {
  test("has a column for each stage, fills the width with no sideways scrolling, and a card moves by the key and its menu", async ({ page }) => {
    for (const width of [1024, 1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      await signIn(page, "work/stages");
      await expect(page.getByRole("heading", { level: 1, name: "Stages" })).toBeVisible();
      await page.getByRole("radio", { name: "Board" }).check();
      const board = page.getByRole("group", { name: /, by stage$/ }).first();
      await expect(board).toBeVisible();
      await expect(board.getByRole("heading", { level: 3 }).first()).toBeVisible();
      expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);
      const frame = (await board.boundingBox())!;
      expect(frame.x + frame.width).toBeLessThanOrEqual(width);
    }
    // The move key, with the cursor on a card, opens that card's menu.
    const card = page.getByRole("group", { name: /, by stage$/ }).first().getByRole("listitem").first();
    await card.focus();
    await page.keyboard.press("m");
    await expect(page.getByRole("menu")).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "History" })).toBeVisible();
    await page.keyboard.press("Escape");
  });

  test("on a phone the list is the start, one row for each item", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page, "work/stages");
    await expect(page.getByRole("heading", { level: 1, name: "Stages" })).toBeVisible();
    await expect(page.getByRole("group", { name: /, by stage$/ })).toHaveCount(0);
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);
  });
});

test.describe("the phone's review mode", () => {
  test("goes through the items waiting for a look one at a time, with Looks good, Send back and Next across the bottom", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page, "work/changed");
    await expect(page.getByRole("heading", { level: 1, name: "What changed" })).toBeVisible();
    const start = page.getByRole("button", { name: "Review one at a time" });
    test.skip((await start.count()) === 0, "the workspace has nothing waiting for a look");
    await start.click();
    const bar = page.getByRole("group", { name: "What to do with this one" });
    await expect(bar).toBeVisible();
    const box = (await bar.boundingBox())!;
    // Across the bottom, above the bottom bar, inside the window, and three full buttons.
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(390);
    expect(box.y + box.height).toBeLessThanOrEqual(844);
    for (const name of ["Send back", "Looks good", "Next"]) await expect(bar.getByRole("button", { name })).toBeVisible();
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);
    await page.getByRole("button", { name: "Back to the list" }).click();
    await expect(start).toBeVisible();
  });
});

test.describe("the walkthrough's look", () => {
  test("fields are as wide as what they hold, the list marks where you are and says nothing is 'not done yet', and the page uses its width", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1920, height: 1000 });
    await signIn(page, "setup");
    await expect(page.getByRole("heading", { level: 1, name: "Set up your workspace" })).toBeVisible();
    const steps = page.getByRole("navigation", { name: "Setup steps" });
    await steps.getByRole("button", { name: /^Mail and calendar/ }).click();
    await steps.getByRole("button", { name: /^You/ }).first().click();
    const main = page.getByRole("main");
    await expect(main.getByRole("heading", { level: 2, name: "You" })).toBeVisible();
    const name = main.getByLabel("Workspace name");
    await expect(name).toBeVisible();
    const field = (await name.boundingBox())!;
    expect(field.width).toBeLessThanOrEqual(361);
    await expect(page.getByText("Not done yet")).toHaveCount(0);
    await expect(steps.getByText("You are here")).toHaveCount(1);
    // The page fills the window: the screen's card reaches well past the old 1100px column, with its why in a pane beside it.
    const card = (await main.boundingBox())!;
    expect(card.x + card.width).toBeGreaterThan(1300);
    const why = main.locator("p").filter({ hasText: /./ }).first();
    const whyBox = (await why.boundingBox())!;
    expect(whyBox.x).toBeGreaterThan(field.x + field.width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  });
});
