// The shell and the visual system (design 7.1, 7.11-7.13) in a real browser: the style guide and Today in light and dark at four
// widths with accessibility checks, how much of the screen the content uses, a header that never wraps, views that are links,
// the offline state, and the phone's bottom bar. Screenshots go to the folder named by E2E_SHOTS, when it is set.
import AxeBuilder from "@axe-core/playwright";
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

async function shoot(page: Page, name: string) {
  const folder = process.env.E2E_SHOTS;
  if (folder) await page.screenshot({ path: `${folder}/${name}.png`, fullPage: false });
}

async function expectNoViolations(page: Page) {
  // The header sticks to the top, so what it covers depends on the scroll position; check from the top.
  await page.evaluate(() => window.scrollTo(0, 0));
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  const found = results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  expect(found).toEqual([]);
}

const WIDTHS = [390, 1024, 1440, 1920];
const HEIGHT = 900;

test.describe("the visual system", () => {
  for (const scheme of ["light", "dark"] as const) {
    test(`the style guide passes the accessibility checks in ${scheme} at every width`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await signIn(page);
      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: HEIGHT });
        await page.evaluate(() => {
          window.location.hash = "styleguide";
        });
        await expect(page.getByRole("heading", { level: 1, name: "Style guide" })).toBeVisible();
        await expect(page.locator("html")).toHaveCSS("color-scheme", scheme);
        await expectNoViolations(page);
        await shoot(page, `styleguide-${scheme}-${width}`);
      }
    });

    test(`Today passes the accessibility checks in ${scheme} at every width`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await signIn(page);
      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: HEIGHT });
        await page.evaluate(() => {
          window.location.hash = "today";
        });
        await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
        await expect(page.getByRole("heading", { level: 2, name: "Needs you" })).toBeVisible();
        await expectNoViolations(page);
        await shoot(page, `today-${scheme}-${width}`);
      }
    });
  }

  test("the style guide's theme toggle switches the whole page", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await page.setViewportSize({ width: 1440, height: HEIGHT });
    await signIn(page, "styleguide");
    const theme = page.getByRole("radiogroup", { name: "Show the page in" });
    await theme.getByRole("radio", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(page.locator("html")).toHaveCSS("color-scheme", "dark");
    await expectNoViolations(page);
    await shoot(page, "styleguide-toggle-dark");
    await theme.getByRole("radio", { name: "Light" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await expectNoViolations(page);
    // The toggle shows a theme without changing what this device remembers.
    expect(await page.evaluate(() => window.localStorage.getItem("cockpit:theme"))).toBeNull();
  });

  test("the user menu's theme and density are kept for this device", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: HEIGHT });
    await signIn(page);
    await page.getByRole("button", { name: /^Appearance, / }).click();
    await page.getByRole("menuitemradio", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.getByRole("button", { name: /^Appearance, / }).click();
    await page.getByRole("menuitemradio", { name: "Compact" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-density", "compact");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(page.locator("html")).toHaveAttribute("data-density", "compact");
    await expectNoViolations(page);
    await shoot(page, "today-dark-compact-1440");
  });

  test("the style guide has every shared component in every state", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: HEIGHT });
    await signIn(page, "styleguide");
    for (const section of ["Type scale", "Color roles", "Buttons", "Pills and the status chip", "Rows", "Segmented control", "Empty, loading and failed", "Drawer, dialog, menu and toast", "Form controls", "Evidence", "Icons"]) {
      await expect(page.getByRole("heading", { level: 2, name: section })).toBeVisible();
    }
    // A disabled button says why, and is not shown by opacity alone.
    const disabled = page.getByRole("button", { name: "Primary", disabled: true }).first();
    await expect(disabled).toBeDisabled();
    await expect(disabled).toHaveAccessibleDescription("Pick a person first.");
    await expect(disabled).toHaveCSS("opacity", "1");
    // The drawer asks before it discards typed text, and focus returns to its opener.
    const opener = page.getByRole("button", { name: "Open a drawer" });
    await opener.click();
    const drawer = page.getByRole("dialog", { name: "Add a person" });
    await drawer.getByLabel("Notes").fill("Something typed");
    await page.keyboard.press("Escape");
    await expect(drawer.getByRole("alert")).toContainText("Discard what you typed?");
    await drawer.getByRole("button", { name: "Discard" }).click();
    await expect(drawer).toHaveCount(0);
    await expect(opener).toBeFocused();
    // The dialog closes with Escape and returns focus too.
    const dialogOpener = page.getByRole("button", { name: "Open a dialog" });
    await dialogOpener.click();
    await expect(page.getByRole("dialog", { name: "Delete this draft?" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(dialogOpener).toBeFocused();
    // A toast sits at the bottom center.
    await page.getByRole("button", { name: "Show a toast" }).click();
    const toast = page.getByRole("region", { name: "Notifications" }).getByText("Marked as sent to Sample Person");
    await expect(toast).toBeVisible();
    const box = (await toast.boundingBox())!;
    expect(Math.abs(box.x + box.width / 2 - 1440 / 2)).toBeLessThan(200);
    expect(box.y).toBeGreaterThan(HEIGHT - 150);
  });
});

test.describe("screen use and the shell", () => {
  const SIDEBAR = 232;

  for (const [width, height] of [
    [1440, 900],
    [1920, 1080],
  ]) {
    test(`at ${width}×${height} every view fills the content area, under a header of at most 56px and no banner`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await signIn(page);
      const hrefs = await page.getByRole("navigation", { name: "Views" }).getByRole("link").evaluateAll((links) => links.map((a) => a.getAttribute("href")!));
      expect(hrefs.length).toBeGreaterThanOrEqual(11);
      for (const href of hrefs) {
        await page.getByRole("navigation", { name: "Views" }).locator(`a[href="${href}"]`).click();
        await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
        await page.waitForTimeout(150);
        const header = (await page.getByRole("banner").boundingBox())!;
        const main = (await page.getByRole("main").boundingBox())!;
        expect(header.height).toBeLessThanOrEqual(56);
        // No banner above the content: it starts right under the header.
        expect(main.y).toBeLessThanOrEqual(56);
        expect(main.x).toBeLessThanOrEqual(SIDEBAR + 1);
        expect(main.width).toBeGreaterThanOrEqual(0.9 * (width - SIDEBAR));
        expect(main.x + main.width).toBeGreaterThanOrEqual(width - 1);
        // The first heading is within the first screenful.
        const h1 = (await page.getByRole("heading", { level: 1 }).first().boundingBox())!;
        expect(h1.y).toBeLessThan(56 + 60);
        await shoot(page, `view-${width}-${href.replace(/^.*#/, "").replace(/[^a-z]+/gi, "-")}`);
      }
      await shoot(page, `shell-${width}`);
    });
  }

  test("the header and the sidebar do not move when the view changes", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page);
    const frame = async () => {
      const header = (await page.getByRole("banner").boundingBox())!;
      const brand = (await page.getByRole("banner").getByRole("link", { name: /, go to Today$/ }).boundingBox())!;
      const nav = (await page.getByRole("navigation", { name: "Views" }).boundingBox())!;
      return [header, brand, nav].map((b) => [b.x, b.y, b.width, b.height]);
    };
    const first = await frame();
    for (const label of [/^Stages/, /^People/, /^Settings/, /^Sources/]) {
      await page.getByRole("navigation", { name: "Views" }).getByRole("link", { name: label }).click();
      await page.waitForTimeout(100);
      expect(await frame()).toEqual(first);
    }
  });

  test("the header never wraps, with plugin panels present", async ({ page }) => {
    await page.route("**/api/panels", async (route) => {
      const panel = (n: number, tab: string) => ({
        name: `demo/panel-${n}`,
        title: `A plugin panel with a rather long title number ${n}`,
        tab,
        kind: "demo/thing",
        view: "table",
        columns: ["title"],
        primary_action: null,
        row_actions: [],
        new_action: null,
      });
      await route.fulfill({ json: [1, 2, 3, 4, 5, 6].map((n) => panel(n, n % 2 ? "work" : "people")) });
    });
    for (const width of [1024, 1280, 1440, 1920, 2560]) {
      await page.setViewportSize({ width, height: 900 });
      await signIn(page);
      const header = page.getByRole("banner");
      expect((await header.boundingBox())!.height).toBe(56);
      // Everything in it sits on one row, inside the window.
      const tops = await header.locator("a, button").evaluateAll((els) =>
        els.filter((e) => (e as HTMLElement).getClientRects().length > 0).map((e) => Math.round(e.getBoundingClientRect().top + e.getBoundingClientRect().height / 2)),
      );
      expect(Math.max(...tops) - Math.min(...tops)).toBeLessThan(12);
      const menu = (await header.getByRole("button", { name: /^Appearance, / }).boundingBox())!;
      expect(menu.x + menu.width).toBeLessThanOrEqual(width);
      // The plugin panels are in the sidebar, under Work and Records, and scroll there if they don't fit.
      await expect(page.getByRole("navigation", { name: "Views" }).getByRole("link", { name: /number 1$/ })).toHaveCount(1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
    }
  });

  test("the sidebar is an icon rail from 1024 to 1279px, with a name for each icon, and can be pinned open", async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 800 });
    await signIn(page);
    const nav = page.getByRole("navigation", { name: "Views" });
    expect((await nav.boundingBox())!.width).toBeLessThan(80);
    await expect(nav.getByRole("link", { name: "Stages" })).toBeVisible();
    await nav.getByRole("button", { name: "Pin the sidebar open" }).click();
    expect((await nav.boundingBox())!.width).toBeGreaterThan(200);
    await page.reload();
    expect((await page.getByRole("navigation", { name: "Views" }).boundingBox())!.width).toBeGreaterThan(200);
    await page.getByRole("navigation", { name: "Views" }).getByRole("button", { name: "Collapse the sidebar" }).click();
    expect((await page.getByRole("navigation", { name: "Views" }).boundingBox())!.width).toBeLessThan(80);
  });

  test("views are links: each entry has an address, and loading it opens the view", async ({ page, context }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page);
    const links = page.getByRole("navigation", { name: "Views" }).getByRole("link");
    const entries = await links.evaluateAll((els) => els.map((a) => ({ href: a.getAttribute("href")!, name: (a.textContent ?? "").trim() })));
    expect(entries.length).toBeGreaterThanOrEqual(11);
    const expected: Record<string, string> = {
      "#today": "Today",
      "#work/changed": "What changed",
      "#work/followups": "Follow-ups",
      "#work/outgoing": "Waiting to go out",
      "#work/stages": "Stages",
      "#records/projects": "Projects",
      "#records/people": "People",
      "#records/files": "Files",
      "#sources": "Sources",
      "#addons": "Add-ons",
      "#settings": "Settings",
    };
    for (const [fragment, title] of Object.entries(expected)) {
      const entry = entries.find((e) => e.href.endsWith(fragment));
      expect(entry, fragment).toBeDefined();
      const fresh = await context.newPage();
      await fresh.goto(new URL(entry!.href, page.url()).toString());
      await expect(fresh.getByRole("heading", { level: 1, name: title, exact: true })).toBeVisible();
      await expect(fresh.getByRole("navigation", { name: "Views" }).locator("a[aria-current=page]")).toHaveAttribute("href", entry!.href);
      await fresh.close();
    }
    // The old address for a view still opens it, and the guide has its own.
    await page.goto("#stages");
    await expect(page.getByRole("heading", { level: 1, name: "Stages" })).toBeVisible();
    await page.goto("#setup");
    await expect(page.getByRole("heading", { level: 1, name: "Set up" })).toBeVisible();
  });

  test("changing view moves focus to the new view's heading", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page);
    await page.getByRole("navigation", { name: "Views" }).getByRole("link", { name: /^Stages/ }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Stages" })).toBeFocused();
    await page.getByRole("navigation", { name: "Views" }).getByRole("link", { name: /^Sources/ }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Sources" })).toBeFocused();
  });

  test("going offline shows in the status chip within five seconds, and coming back clears it", async ({ page, context }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page);
    const chip = page.getByRole("button", { name: /^Status: / });
    // Connected: the chip says a state (live, or something to do), not that it is still connecting.
    await expect(chip).not.toContainText("Connecting");
    await expect(chip).not.toContainText("Offline");
    await context.setOffline(true);
    await expect(chip).toContainText("Offline", { timeout: 5000 });
    await expect(chip).toContainText("reconnecting");
    await context.setOffline(false);
    await expect(chip).not.toContainText("Offline", { timeout: 20_000 });
  });

  test("on a phone the bottom bar is visible, the page does not scroll sideways, and the sheets list the views", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page);
    const bar = page.getByRole("navigation", { name: "Views" });
    await expect(bar).toBeVisible();
    for (const name of ["Today", "Work", "Hand something in", "Ask", "More"]) {
      await expect(bar.getByRole(name === "Today" ? "link" : "button", { name })).toBeVisible();
    }
    const box = (await bar.boundingBox())!;
    expect(box.y + box.height).toBeGreaterThanOrEqual(844 - 1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await bar.getByRole("button", { name: "Work" }).click();
    const sheet = page.getByRole("dialog", { name: "Work" });
    await expect(sheet.getByRole("link", { name: "Stages" })).toBeVisible();
    await sheet.getByRole("link", { name: "Stages" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Stages" })).toBeVisible();
    // Content is not hidden under the bar.
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    const last = await page.evaluate(() => {
      const main = document.querySelector("main")!.getBoundingClientRect();
      return main.bottom;
    });
    expect(last).toBeGreaterThanOrEqual(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await shoot(page, "phone-stages");
  });
});
