// Late evening (the UI/UX re-review of B-9, R-0): after midnight UTC, in a workspace whose time zone is behind UTC, the
// day is still the earlier one where the person is. Marking a message sent and recording a follow-up are written in that
// day, so a wait counts zero days ("sent today"), never a negative number. The project's server starts its clock at
// 00:30 UTC (`--clock-at`), which is the evening before in the demo workspace's zone, and has a server of its own so no
// other scenario's clock or lines are mixed in.
import { expect, test, type Page } from "@playwright/test";

interface Section {
  person: string;
  name: string;
  is_pm: boolean;
  to_send: number;
  questions: Array<{ id: string; status: string }>;
  actions: Array<{ id: string; text: string; told: string | null }>;
}

const NEGATIVE_DAYS = /-\d+\s*days?/;

async function signIn(page: Page) {
  await page.goto("?token=e2e-token");
  await expect(page.getByRole("heading", { level: 2, name: "Needs you", exact: true })).toBeVisible();
}

async function openView(page: Page, label: string) {
  const dismiss = page.getByRole("region", { name: "Notifications" }).getByRole("button", { name: "Dismiss" });
  while (await dismiss.count()) await dismiss.last().click();
  const link = page.getByRole("navigation", { name: "Views" }).getByRole("link", { name: new RegExp(`^${label}`) });
  await link.click();
  await expect(link).toHaveAttribute("aria-current", "page");
}

/** No wait on the screen is counted below zero. */
async function expectNoNegativeDays(page: Page) {
  await expect(page.getByRole("main")).not.toContainText(NEGATIVE_DAYS);
}

test.describe("Late evening", () => {
  test("after midnight UTC, in a workspace behind UTC, a message marked sent and a follow-up count zero days, never below", async ({ page }) => {
    await signIn(page);
    await expectNoNegativeDays(page);

    // Someone with an action to send, from the server's own list.
    const sections = (await (await page.request.get("api/followups")).json()) as Section[];
    const target = sections.find((s) => !s.is_pm && s.to_send > 0 && s.actions.some((a) => a.told === null));
    expect(target, "someone with an action to send").toBeTruthy();
    const { name, to_send: toSend } = target!;
    const sent = target!.actions.filter((a) => a.told === null);

    await openView(page, "Follow-ups");
    await expect(page.getByRole("heading", { name: "Follow-ups", exact: true })).toBeVisible();
    const card = page.locator("li.line", { has: page.locator("strong", { hasText: new RegExp(`^${name}$`) }) });
    await expectNoNegativeDays(page);

    // Copy opens the message, the second Copy puts it on the clipboard, and Mark sent records it.
    await card.getByRole("button", { name: `Copy ${toSend}` }).click();
    await expect(card.getByRole("textbox").first()).toBeVisible();
    await card.getByRole("button", { name: `Copy ${toSend}` }).click();
    await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toContain(sent[0].text);
    await card.getByRole("button", { name: "Mark sent" }).first().click();
    await expect(page.getByText(`Marked as sent to ${name}`)).toBeVisible();
    await expectNoNegativeDays(page);

    // Under Waiting on them it was sent today, and no wait shows yet.
    await page.getByRole("button", { name: "Waiting on them" }).click();
    const waiting = page.locator("li.line", { has: page.getByRole("heading", { name }) });
    const item = waiting.locator("li.child", { hasText: sent[0].text });
    await expect(item).toContainText("sent today");
    await expect(item).not.toContainText(/waiting \d+ days?/);
    await expectNoNegativeDays(page);

    // Recording a follow-up on it starts the wait again, still without a negative count.
    await item.getByRole("button", { name: /^More actions for / }).click();
    await page.getByRole("menuitem", { name: "Followed up" }).click();
    await expect(page.getByText(/^Recorded your follow-up with /)).toBeVisible();
    await expect(waiting.locator("li.child", { hasText: sent[0].text })).toContainText("followed up");
    await expectNoNegativeDays(page);

    // Today shows the same wait without a negative number, however it counts it.
    await openView(page, "Today");
    await expect(page.getByRole("heading", { level: 2, name: "Needs you", exact: true })).toBeVisible();
    await expectNoNegativeDays(page);
    await expect(page.getByRole("main")).not.toContainText(/waiting up to -/);
  });
});
