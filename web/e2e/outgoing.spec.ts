// Waiting to go out, end to end (design 6.12, 7.4): a message drafted to a known person on the core's stand-in channel waits
// for the person's yes. The person opens the screen, reads the exact content and who it goes to, acknowledges the recipient
// called out, chooses Approve and send, confirms, and the message is handed to the channel exactly as shown. The project has a
// server of its own (`--fake-channel`), which says what the channel was handed.
import { expect, test, type Page } from "@playwright/test";
import { checkAccessibility, collectProblems } from "./journey-helpers";

interface Outgoing {
  enabled: boolean;
  name: string;
  address: string;
  subject: string;
  body: string;
  delivered: Array<{ parts: Record<string, string>; to: string[] }>;
}

async function signIn(page: Page) {
  await page.goto("?token=e2e-token");
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
}

const handed = async (page: Page): Promise<Outgoing> => (await page.request.get("/__e2e/delivered")).json();

test.describe("Waiting to go out", () => {
  test("a message is approved and sent as shown: the content, the target, the recipient acknowledged, a confirm, then the channel has it", async ({ page }) => {
    const problems: string[] = [];
    collectProblems(page, problems);
    const first = await handed(page);
    expect(first.enabled).toBe(true);
    expect(first.delivered).toEqual([]);

    await signIn(page);
    await page.getByRole("navigation", { name: "Views" }).getByRole("link", { name: /^Waiting to go out/ }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Waiting to go out" })).toBeVisible();

    // One line for the message, with its state in words, and its detail beside it with the exact content and the target.
    const line = page.getByRole("list", { name: "Waiting to go out" }).getByRole("listitem");
    await expect(line).toHaveCount(1);
    await expect(line).toContainText(`Message to ${first.name}`);
    await expect(line).toContainText("To approve");
    const pane = page.getByRole("complementary", { name: `Message to ${first.name}` });
    await expect(pane).toContainText(first.subject);
    await expect(pane).toContainText(first.body);
    await expect(pane).toContainText(`${first.name}, ${first.address}`);

    // A recipient never written to is called out: Approve and send waits for the acknowledgement by name.
    const send = pane.getByRole("button", { name: "Approve and send" });
    await expect(send).toBeDisabled();
    await pane.getByRole("checkbox", { name: new RegExp(`I know about ${first.name}`) }).check();
    await expect(send).toBeEnabled();
    await checkAccessibility(page);

    // A send confirms, in words, before anything leaves.
    await send.click();
    const dialog = page.getByRole("dialog", { name: `Send this message to ${first.name} now?` });
    await expect(dialog).toBeVisible();
    expect((await handed(page)).delivered).toEqual([]);
    await dialog.getByRole("button", { name: "Send" }).click();

    await expect(page.getByText(`Sent the message to ${first.name}.`)).toBeVisible();
    await expect(page.getByText("Nothing is waiting to go out.")).toBeVisible();

    // The channel was handed exactly what was shown, once.
    const after = await handed(page);
    expect(after.delivered).toHaveLength(1);
    expect(after.delivered[0].to).toEqual([first.address]);
    expect(after.delivered[0].parts).toEqual({ subject: first.subject, body: first.body });
    expect(problems).toEqual([]);
  });
});
