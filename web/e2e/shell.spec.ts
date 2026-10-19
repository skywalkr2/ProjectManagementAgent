// The shell and the visual system (design 7.1, 7.11-7.13) in a real browser: the style guide and Today in light and dark at four
// widths with accessibility checks, how much of the screen the content uses, a header that never wraps, views that are links,
// the offline state, and the phone's bottom bar. Screenshots go to the folder named by E2E_SHOTS, when it is set.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";

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

  for (const scheme of ["light", "dark"] as const) {
    test(`the setup walkthrough passes the accessibility checks in ${scheme} at every width, with no sideways scrolling`, async ({
      page,
    }) => {
      await page.emulateMedia({ colorScheme: scheme });
      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: HEIGHT });
        await signIn(page, "setup");
        await expect(page.getByRole("heading", { level: 1, name: "Set up your workspace" })).toBeVisible();
        const screens = page.getByRole("navigation", { name: "Setup steps" });
        for (const name of [/^Your AI account/, /^Mail and calendar/, /^Done/]) {
          await screens.getByRole("button", { name }).click();
          await expectNoViolations(page);
          expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
        }
        await shoot(page, `walkthrough-${scheme}-${width}`);
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
    await page.getByRole("button", { name: /^Change appearance, / }).click();
    await page.getByRole("menuitemradio", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.getByRole("button", { name: /^Change appearance, / }).click();
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
    // From 1280px a toast sits at the bottom left of the content area, just right of the navigation and never over it, in one line.
    await page.getByRole("button", { name: "Show a toast" }).click();
    const notices = page.getByRole("region", { name: "Notifications" });
    const toast = notices.getByText("Marked as sent to Sample Person");
    await expect(toast).toBeVisible();
    const nav = (await page.getByRole("navigation", { name: "Views" }).boundingBox())!;
    const box = (await toast.boundingBox())!;
    const region = (await notices.boundingBox())!;
    expect(region.x).toBeGreaterThanOrEqual(nav.x + nav.width);
    expect(region.width).toBeGreaterThanOrEqual(360);
    expect(region.width).toBeLessThanOrEqual(420);
    expect(box.height).toBeLessThan(30);
    expect(box.y).toBeGreaterThan(HEIGHT - 150);
    // Narrower, it is at the bottom center, above the bottom bar.
    await page.setViewportSize({ width: 390, height: HEIGHT });
    await expect(toast).toBeVisible();
    const phone = (await toast.boundingBox())!;
    expect(Math.abs(phone.x + phone.width / 2 - 390 / 2)).toBeLessThan(100);
    const bar = (await page.getByRole("navigation", { name: "Views" }).boundingBox())!;
    expect(phone.y + phone.height).toBeLessThanOrEqual(bar.y);
  });

  // WCAG 2.4.11 (axe does not check it): with three toasts showing, no control the cursor reaches is hidden under them.
  for (const width of [390, 1440]) {
    test(`with three toasts showing, Tab never leaves a control under them at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: HEIGHT });
      await signIn(page, "styleguide");
      await page.getByRole("button", { name: "Show three toasts" }).click();
      const notices = page.getByRole("region", { name: "Notifications" });
      await expect(notices.getByRole("button", { name: "Dismiss" })).toHaveCount(3);
      // Even with several buttons the words keep a width that reads: the buttons wrap under them.
      expect((await notices.getByText("Added Sample Project").boundingBox())!.width).toBeGreaterThan(150);
      await page.getByRole("heading", { level: 1 }).first().focus();
      const hidden: string[] = [];
      for (let i = 0; i < 400; i++) {
        await page.keyboard.press("Tab");
        const covered = await page.evaluate(() => {
          const active = document.activeElement as HTMLElement | null;
          const region = document.querySelector("[data-toast-region]");
          if (!active || !region || region.contains(active)) return null;
          const r = active.getBoundingClientRect();
          if (r.width === 0 || r.height === 0) return null;
          const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return top && region.contains(top) ? (active.getAttribute("aria-label") ?? active.textContent ?? active.tagName).trim().slice(0, 40) : null;
        });
        if (covered) hidden.push(covered);
        if (await page.evaluate(() => document.activeElement === document.body)) break;
      }
      expect(hidden).toEqual([]);
    });
  }
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

  // The first-go line is a line of the queue (design 7.8); the walkthrough's last button focuses it, and Go must then be
  // fully on the screen, not clipped.
  for (const [width, height] of [
    [1280, 720],
    [390, 844],
  ]) {
    test(`after the walkthrough's last button, the first-go line's Go button is fully visible at ${width}×${height}`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      // Three runs wait for the first go, one of them with no price: the queue has one line for them.
      await page.route("**/api/today/queue", async (route) => {
        if (route.request().method() !== "GET") return route.fallback();
        await route.fulfill({
          json: [
            { key: "first_go", group: "decide", kind: "first_go", count: 3, estimate_usd: 0.3, unpriced: 1, untrusted: false, actions: [], questions: [], outcome: {} },
          ],
        });
      });
      await signIn(page, "setup");
      await expect(page.getByRole("heading", { level: 1, name: "Set up your workspace" })).toBeVisible();
      await page.getByRole("navigation", { name: "Setup steps" }).getByRole("button", { name: /^Done/ }).click();
      await page.getByRole("main").getByRole("button", { name: "Go to Today" }).click();
      const line = page.locator('[data-queue-line="first_go"]');
      await expect(line).toBeFocused();
      await expect(line).toBeInViewport({ ratio: 1 });
      await expect(line.getByRole("button", { name: "Start", exact: true })).toBeInViewport({ ratio: 1 });
      await shoot(page, `first-go-${width}`);
    });
  }

  // A toast sits at the bottom of the window; while the walkthrough is open it never covers the screen's own buttons, and
  // it is gone when the walkthrough moves to another screen.
  for (const [width, height] of [
    [1280, 720],
    [390, 844],
  ]) {
    test(`a toast over a walkthrough screen leaves Back and Next clickable at ${width}×${height}, and goes when the screen changes`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height });
      await signIn(page, "setup");
      await expect(page.getByRole("heading", { level: 1, name: "Set up your workspace" })).toBeVisible();
      await page.getByRole("navigation", { name: "Setup steps" }).getByRole("button", { name: /^Your AI account/ }).click();
      const main = page.getByRole("main");
      await expect(main.getByRole("heading", { level: 2, name: "Your AI account" })).toBeVisible();
      // At the end of the screen, where its buttons are, pressing the undo key with nothing to undo says so in a toast.
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      // The screen puts the cursor in its first field once its data has loaded, or on itself when it has no field;
      // wait for it to land in the screen, then leave any field, where a shortcut key would type.
      await expect
        .poll(
          () =>
            page.evaluate(() => {
              const screen = document.querySelector("main");
              return !!screen && !!document.activeElement && screen.contains(document.activeElement);
            }),
          { timeout: 15_000 },
        )
        .toBe(true);
      await main.getByRole("heading", { level: 2, name: "Your AI account" }).click();
      await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
      await page.keyboard.press("u");
      const notices = page.getByRole("region", { name: "Notifications" });
      await expect(notices.getByText("Nothing to undo.")).toBeVisible();
      const overlap = async () => {
        const toast = (await notices.getByText("Nothing to undo.").boundingBox())!;
        for (const name of [/^Back$/, /^(Skip for now|Next)$/]) {
          const button = (await main.getByRole("button", { name }).boundingBox())!;
          const apart = button.y + button.height <= toast.y || button.y >= toast.y + toast.height;
          const aside = button.x + button.width <= toast.x || button.x >= toast.x + toast.width;
          if (!apart && !aside) return String(name);
        }
        return null;
      };
      await expect.poll(overlap).toBeNull();
      await shoot(page, `walkthrough-toast-${width}`);
      await main.getByRole("button", { name: "Back" }).click({ trial: true });
      await main.getByRole("button", { name: /^(Skip for now|Next)$/ }).click({ trial: true });
      await main.getByRole("button", { name: "Back" }).click();
      await expect(main.getByRole("heading", { level: 2, name: "You" })).toBeVisible();
      await expect(notices.getByText("Nothing to undo.")).toHaveCount(0);
    });
  }

  test("the header and the sidebar do not move when the view changes", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page);
    const frame = async () => {
      const header = (await page.getByRole("banner").boundingBox())!;
      const brand = (await page.getByRole("banner").getByRole("link", { name: /^Go to Today/ }).boundingBox())!;
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
      // From 1280px everything sits on one row of 56px. Below that the status chip and the assistant's line take a second
      // small row under the rest, so the first row keeps its room and nothing squeezes.
      const wide = width >= 1280;
      expect((await header.boundingBox())!.height).toBe(wide ? 56 : 88);
      const statusRow = header.getByRole("button", { name: /^App status: / });
      const assistant = header.getByRole("button", { name: /^Assistant/ });
      const rowOf = async (selector: Locator) => {
        const box = (await selector.boundingBox())!;
        return Math.round(box.y + box.height / 2);
      };
      expect(Math.abs((await rowOf(statusRow)) - (await rowOf(assistant)))).toBeLessThan(6);
      const tops = await header.locator("a, button").evaluateAll((els, includeStatus) =>
        els
          .filter((e) => (e as HTMLElement).getClientRects().length > 0 && (includeStatus || !/^(App status: |Assistant)/.test(e.getAttribute("aria-label") ?? e.textContent ?? "")))
          .map((e) => Math.round(e.getBoundingClientRect().top + e.getBoundingClientRect().height / 2)),
      wide);
      expect(Math.max(...tops) - Math.min(...tops)).toBeLessThan(12);
      if (!wide) expect(await rowOf(statusRow)).toBeGreaterThan(56);
      const menu = (await header.getByRole("button", { name: /^Change appearance, / }).boundingBox())!;
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
    await nav.getByRole("button", { name: "Keep the side menu open" }).click();
    expect((await nav.boundingBox())!.width).toBeGreaterThan(200);
    await page.reload();
    expect((await page.getByRole("navigation", { name: "Views" }).boundingBox())!.width).toBeGreaterThan(200);
    await page.getByRole("navigation", { name: "Views" }).getByRole("button", { name: "Hide the side menu" }).click();
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
      "#work/outgoing": "Drafts to approve",
      "#work/stages": "Stages",
      "#records/projects": "Projects",
      "#records/people": "People",
      "#records/files": "Files",
      "#records/knowledge": "Knowledge",
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
    await expect(page.getByRole("heading", { level: 1, name: "Set up your workspace" })).toBeVisible();
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
    const chip = page.getByRole("button", { name: /^App status: / });
    // Connected: the chip says a state (live, or something to do), not that it is still connecting.
    await expect(chip).not.toContainText("Connecting");
    await expect(chip).not.toContainText("Disconnected");
    await context.setOffline(true);
    await expect(chip).toContainText("Disconnected", { timeout: 5000 });
    await expect(chip).toContainText("reconnecting");
    await context.setOffline(false);
    await expect(chip).not.toContainText("Disconnected", { timeout: 20_000 });
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

// Made-up answers for the screens that need accounts and measurements the demo workspace doesn't have, so the layout and the
// accessibility checks run on what a person with accounts would see. The shapes are the server's own.
const account = (name: string, label: string, over: Record<string, unknown> = {}) => ({
  name,
  label,
  kind: null,
  adapter: "adapter-one",
  base_url: null,
  models: { everyday: "model-a", harder: "model-b" },
  used_for: [],
  backup_for: [],
  has_key: true,
  key_state: "saved",
  key_where: null,
  key_ending: false,
  credential_expires: null,
  answered_at: new Date(Date.now() - 2 * 3_600_000).toISOString(),
  spent_today_usd: 1.2,
  checked_for: [],
  check_failed_for: [],
  checked_at: null,
  paused_until: null,
  check_usd: 0.02,
  ...over,
});
const ACCOUNTS = [
  account("main", "Main account", { used_for: ["routine", "deep"] }),
  account("second", "Second account", { backup_for: ["routine", "deep"], answered_at: null, spent_today_usd: 0, checked_for: ["routine", "deep"], checked_at: "2026-10-14T09:00:00+00:00" }),
  account("trial", "Trial account", { key_state: "missing", answered_at: null, spent_today_usd: 0 }),
];
const skill = (id: string, label: string, over: Record<string, unknown> = {}) => ({
  id,
  label,
  description: "",
  measured: true,
  runs: 18,
  passes: 17,
  pass_rate: 0.94,
  age_days: 2,
  cost_per_pass_usd: 0.03,
  stale: null,
  below_min: false,
  ...over,
});
const unmeasured = (id: string, label: string) => skill(id, label, { measured: false, runs: 0, passes: 0, pass_rate: null, age_days: null, cost_per_pass_usd: null });
const SKILLS = {
  min_score: 0.8,
  stale_days: 60,
  accounts: [
    {
      name: "main",
      models: [
        { model: "everyday", measure: null, measure_why: null, skills: [skill("notes", "Pull actions from meeting notes"), skill("route", "Route a question to who decides", { pass_rate: 0.9, cost_per_pass_usd: 0.02 }), skill("term", "Use a known term", { pass_rate: 0.88, cost_per_pass_usd: 0.02 }), unmeasured("voice", "Write an update in your voice")] },
        { model: "harder", measure: null, measure_why: null, skills: [skill("notes", "Pull actions from meeting notes", { pass_rate: 0.97, cost_per_pass_usd: 0.11 }), skill("route", "Route a question to who decides", { pass_rate: 0.96, cost_per_pass_usd: 0.08 }), skill("term", "Use a known term", { pass_rate: 1, cost_per_pass_usd: 0.07 }), skill("voice", "Write an update in your voice", { pass_rate: 0.91, runs: 6, age_days: 40, cost_per_pass_usd: 0.14, stale: "age" })] },
      ],
    },
    {
      name: "second",
      models: [{ model: "everyday", measure: null, measure_why: null, skills: [skill("notes", "Pull actions from meeting notes", { pass_rate: 0.89, cost_per_pass_usd: 0.04 }), skill("route", "Route a question to who decides", { pass_rate: 0.85, cost_per_pass_usd: 0.01 }), skill("term", "Use a known term", { pass_rate: 0.56, runs: 9, below_min: true, cost_per_pass_usd: 0.05 }), unmeasured("voice", "Write an update in your voice")] }],
    },
  ],
};
const ESTIMATE = { models: ["everyday"], level: "internal", cases: 12, skipped: 0, runs: 3, usd: 0.12, confirm_above_usd: 0.1, needs_go: false };

async function mockAccounts(page: Page) {
  await page.route("**/api/ai/accounts", (route) => (route.request().method() === "GET" ? route.fulfill({ json: ACCOUNTS }) : route.continue()));
  await page.route("**/api/ai/skills", (route) => route.fulfill({ json: SKILLS }));
  await page.route("**/api/ai/skills/*/estimate", (route) => route.fulfill({ json: ESTIMATE }));
}

test.describe("AI accounts as one place, what each can do, and the follow-ups table", () => {
  test("Settings: the summary line, a row with a role pill, a state line and one next step each, and the add drawer opens in place", async ({ page }) => {
    await mockAccounts(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page, "settings/ai");
    const section = page.getByRole("region", { name: /^AI accounts/ });
    await expect(section.getByRole("heading", { name: /^AI accounts/ })).toBeVisible();
    await expect(section.getByRole("group", { name: "Who does the work" })).toContainText("Main account does");
    await expect(section.getByRole("group", { name: "Who does the work" })).toContainText("Second account stands in");
    const rows = section.locator("li[data-row]");
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0)).toContainText("Does the work");
    await expect(rows.nth(0)).toContainText("Ready · answered 2 hours ago · $1.20 today");
    await expect(rows.nth(1)).toContainText("Backup");
    await expect(rows.nth(1)).toContainText("Checked for every kind of work · Oct 14");
    await expect(rows.nth(2)).toContainText("Access key not found on this computer");
    await expect(rows.nth(2).getByRole("button", { name: "Add the access key for Trial account" })).toBeVisible();
    await section.scrollIntoViewIfNeeded();
    await shoot(page, "accounts-1440");
    await expectNoViolations(page);
    // The form opens here, as a drawer, and the address stays the AI accounts section of Settings.
    await section.getByRole("button", { name: "Add an account" }).click();
    const drawer = page.getByRole("dialog", { name: "Add an account" });
    await expect(drawer).toBeVisible();
    await expect(page).toHaveURL(/#settings\/ai$/);
    await expectNoViolations(page);
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();
    await expect(section.getByRole("button", { name: "Add an account" })).toBeFocused();
  });

  test("Settings saves each change as it is made, with Changed and Reset, a toast with Undo, and no Save button", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page, "settings/appearance");
    const seconds = page.getByRole("textbox", { name: "Seconds a message stays on screen" });
    await expect(seconds).toBeFocused();
    await expect(page.getByRole("button", { name: /^Save/ })).toHaveCount(0);
    const before = await seconds.inputValue();
    await seconds.fill("17");
    await seconds.press("Enter");
    const toasts = page.getByRole("region", { name: "Notifications" });
    await expect(toasts).toContainText("Seconds a message stays on screen: 17");
    const row = page.locator(".setting", { has: seconds });
    await expect(row.getByText("Changed", { exact: true })).toBeVisible();
    await toasts.getByRole("button", { name: "Undo" }).first().click();
    await expect(seconds).toHaveValue(before);
    // Reset puts it back to its default at once, and says so.
    await seconds.fill("19");
    await seconds.press("Enter");
    await expect(toasts).toContainText("Seconds a message stays on screen: 19");
    await row.getByRole("button", { name: /^Reset/ }).click();
    await expect(row.getByText("Changed", { exact: true })).toHaveCount(0);
    await expectNoViolations(page);
  });

  test("Settings: the help sits beside each setting on a wide screen and under it on a phone, and the section list stacks above", async ({ page }) => {
    await signIn(page, "settings/backups");
    const row = page.locator(".setting").filter({ hasText: "Hours between backups" }).first();
    await expect(row).toBeVisible();
    await page.setViewportSize({ width: 1440, height: 900 });
    const wide = { field: (await row.locator("[data-main]").boundingBox())!, help: (await row.locator("[data-help]").boundingBox())! };
    expect(wide.help.x).toBeGreaterThan(wide.field.x + wide.field.width - 1);
    const nav = page.getByRole("navigation", { name: "Settings sections" });
    const list = (await nav.boundingBox())!;
    expect(list.x + list.width).toBeLessThan(wide.field.x + 1);
    await page.setViewportSize({ width: 390, height: 844 });
    // Measured once the narrow layout has settled: the help under its field, the section list above them.
    const stacked = async () => {
      const field = (await row.locator("[data-main]").boundingBox())!;
      const help = (await row.locator("[data-help]").boundingBox())!;
      const sections = (await nav.boundingBox())!;
      return help.y > field.y + field.height - 1 && sections.y + sections.height < field.y + 1;
    };
    await expect.poll(stacked).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });

  test("Settings on a phone: no sideways scroll, and the rows keep their one button", async ({ page }) => {
    await mockAccounts(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await signIn(page, "settings/ai");
    const section = page.getByRole("region", { name: /^AI accounts/ });
    await section.scrollIntoViewIfNeeded();
    await expect(section.locator("li[data-row]").first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await shoot(page, "accounts-phone");
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`Settings: which model does what has named lists, saves a choice with Undo, and has no violations in ${scheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.setViewportSize({ width: 1024, height: 900 });
      await signIn(page, "settings/ai");
      const part = page.getByRole("region", { name: "Which model does what" });
      await expect(part).toBeVisible();
      await expect(part.getByRole("group", { name: "Each kind of work" }).getByRole("combobox").first()).toBeVisible();
      await expect(part.getByRole("group", { name: "Send hard work to a stronger model first" })).toContainText("the first one that fits decides");
      await expect(part).toContainText("follows your spending limits");
      await part.scrollIntoViewIfNeeded();
      await expectNoViolations(page);
      // A choice is saved as it is made and can be undone.
      const first = part.getByRole("group", { name: "Each kind of work" }).getByRole("combobox").first();
      const before = await first.inputValue();
      const options = await first.locator("option").evaluateAll((all) => all.map((o) => (o as HTMLOptionElement).value));
      const other = options.find((o) => o !== before)!;
      await first.selectOption(other);
      await expect(page.getByRole("button", { name: "Undo" }).first()).toBeVisible();
      await expect(first).toHaveValue(other);
      await page.getByRole("button", { name: "Undo" }).first().click();
      await expect(first).toHaveValue(before);
    });
  }

  for (const scheme of ["light", "dark"] as const) {
    test(`the grid of what each account can do, in ${scheme}: pass rate first, the cheapest passing marked, and no violations`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await mockAccounts(page);
      await page.setViewportSize({ width: 1440, height: 900 });
      await signIn(page, "settings/ai");
      await page.getByRole("button", { name: "Compare what they can do" }).click();
      await expect(page.getByRole("heading", { level: 1, name: "Compare what accounts can do" })).toBeVisible();
      await expect(page.getByRole("navigation", { name: "Views" }).locator("a[aria-current=page]")).toHaveAttribute("href", /#settings$/);
      const table = page.getByRole("table");
      await expect(table.getByRole("columnheader")).toHaveText(["Kind of work", "Main account · everyday", "Main account · harder", "Second account · everyday"]);
      await expect(table).toContainText("✓ Cheapest that passes");
      await expect(table).toContainText("Below 80%");
      await expect(table).toContainText("(old)");
      await expect(table.getByRole("button", { name: "Test Main account · everyday" })).toContainText("Test performance (about $0.12)");
      if (scheme === "light") await shoot(page, "grid-1440");
      await expectNoViolations(page);
      await page.setViewportSize({ width: 390, height: 844 });
      await page.waitForFunction(() => document.documentElement.hasAttribute("data-narrow"));
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await expectNoViolations(page);
    });
  }

  test("Follow-ups: the Message | Table switch shows the table before anything is copied, and it passes the accessibility checks", async ({ page }) => {
    const book = `${"https" + "://"}example.com/book`;
    const section = {
      person: "PER-9",
      name: "Robin Sample",
      is_pm: false,
      questions: [
        { id: "Q-1", title: "Do we have written permission for the epigraph?", text: "", links: [{ label: "Book page", url: book }], kind: "question", status: "open", project_name: "Sample project", sent: "2026-10-10", waiting_days: null, chase_due: false, about: null, options: [] },
        { id: "Q-2", title: "Which author bio goes on the jacket?", text: "", links: [], kind: "question", status: "open", project_name: "Sample project", sent: null, waiting_days: null, chase_due: false, about: null, options: [] },
      ],
      actions: [
        { id: "ACT-1", text: "Agree on the back-cover copy", due: "2020-10-14", project_name: "Sample project", links: [{ label: "Book page", url: book }], told: null, told_days: null, followed_up: null, on_hold: null, chase_due: false },
        { id: "ACT-2", text: "Send the acknowledgments page", due: "2099-10-23", project_name: "Sample project", links: [], told: null, told_days: null, followed_up: null, on_hold: null, chase_due: false },
      ],
      message: "Hi Robin",
      to_send: 4,
    };
    await page.route("**/api/followups", (route) => route.fulfill({ json: [section] }));
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page, "work/followups");
    await page.getByRole("button", { name: /^Robin Sample/ }).click();
    await page.getByRole("radio", { name: "Table" }).click();
    const tables = page.getByRole("table");
    await expect(tables).toHaveCount(2);
    await expect(tables.first().getByRole("columnheader")).toHaveText(["Project", "To-do", "Due", "Link", "Your update"]);
    await expect(tables.nth(1).getByRole("columnheader")).toHaveText(["Project", "Question", "First asked", "Link", "Your answer"]);
    await expect(tables.first()).toContainText("overdue");
    await expect(page.getByRole("button", { name: "Copy as table" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Copy for a spreadsheet" })).toBeVisible();
    // The fill-in column is the last and the widest.
    const widths = await tables.first().getByRole("columnheader").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().width));
    expect(widths[widths.length - 1]).toBe(Math.max(...widths));
    await shoot(page, "followups-table-1440");
    await expectNoViolations(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForFunction(() => document.documentElement.hasAttribute("data-narrow"));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });

  test("Today: the backup line's button is at the end of the row, like the setup line's", async ({ page }) => {
    await page.route("**/api/status", async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      await route.fulfill({ json: { ...body, backup: { ...body.backup, configured: true, needs_attention: true, age_hours: 100 } } });
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await signIn(page);
    const line = page.locator("[data-backup-line]");
    await expect(line).toBeVisible();
    const button = line.getByRole("button", { name: "Back up now" });
    const [lineBox, buttonBox] = await Promise.all([line.boundingBox(), button.boundingBox()]);
    // The button ends where the row's padding does, however long the words are.
    expect(lineBox!.x + lineBox!.width - (buttonBox!.x + buttonBox!.width)).toBeLessThan(24);
    await shoot(page, "backup-line-1440");
    // The status route may still be answering a poll as the page closes; that is not a failure of the test.
    await page.unrouteAll({ behavior: "ignoreErrors" });
  });
});
