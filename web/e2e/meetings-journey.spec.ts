// Meetings and people, end to end (design 6.32, 7.14): a calendar entry about to start with another person on it is a line on
// Today that opens its page, where the prep says who is coming and what is open with them; one that has ended asks what
// happened, and the words typed are saved on it; and a promise that person made, gone quiet, is a line that opens their page,
// where what to remember about them shows it. The server is started with `--meetings`, which seeds the two entries and the
// promise from the fixtures' people; the words typed for the note are the only thing the test makes up. Written to run in the
// browser tests; it has not been run yet.
import { expect, test, type Page } from "@playwright/test";
import { checkAccessibility, collectProblems } from "./journey-helpers";

interface Seeded {
  enabled: boolean;
  guest: { id: string; name: string };
  coming: { id: string; title: string };
  ended: { id: string; title: string };
  promise: { id: string; text: string };
  captured: boolean;
}

const seeded = async (page: Page): Promise<Seeded> => (await page.request.get("/__e2e/meetings")).json();

async function signIn(page: Page) {
  await page.goto("?token=e2e-token");
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
}

const row = (page: Page, title: string) => page.getByRole("group", { name: title });

test.describe.configure({ mode: "serial" });

test.describe("meetings and people", () => {
  test("an entry about to start with someone is a line that opens its prep: who is coming and what is open with them", async ({ page }) => {
    const problems: string[] = [];
    collectProblems(page, problems);
    const found = await seeded(page);
    expect(found.enabled).toBe(true);

    await signIn(page);
    const line = row(page, `Prepare for ${found.coming.title}`);
    await expect(line).toBeVisible();
    await expect(line).toContainText(`with ${found.guest.name}`);
    await expect(line).toContainText(/things? open/);
    await checkAccessibility(page);

    await line.getByRole("button", { name: "Open prep" }).click();
    await expect(page.getByRole("heading", { level: 1, name: found.coming.title })).toBeVisible();
    const prep = page.getByRole("region", { name: "Prep" });
    await expect(prep).toContainText(found.guest.name);
    // What is open with them is shown with the words it was made from.
    await expect(prep).toContainText(found.promise.text);
    await checkAccessibility(page);
    expect(problems).toEqual([]);
  });

  test("an entry that has ended asks what happened, with the cursor in the box, and the words typed are saved on it", async ({ page }) => {
    const problems: string[] = [];
    collectProblems(page, problems);
    const found = await seeded(page);
    expect(found.captured).toBe(false);

    await signIn(page);
    const line = row(page, `Capture what happened at ${found.ended.title}`);
    await expect(line).toBeVisible();
    await line.getByRole("button", { name: "Capture" }).click();
    const box = line.getByRole("textbox", { name: `What happened at ${found.ended.title}?` });
    await expect(box).toBeFocused();
    await checkAccessibility(page);
    await box.fill("Nothing was decided. I will send the file by Friday.");
    await box.press("Enter");

    await expect(page.getByText(`Saved what happened at ${found.ended.title}`)).toBeVisible();
    await expect(row(page, `Capture what happened at ${found.ended.title}`)).toHaveCount(0);
    expect((await seeded(page)).captured).toBe(true);
    expect(problems).toEqual([]);
  });

  test("a promise gone quiet is a line that opens the person's page, which remembers what is open with them", async ({ page }) => {
    const problems: string[] = [];
    collectProblems(page, problems);
    const found = await seeded(page);

    await signIn(page);
    const line = row(page, `Follow up with ${found.guest.name}: ${found.promise.text} has gone quiet`);
    await expect(line).toBeVisible();
    await expect(line).toContainText("They promised you");
    await expect(line).toContainText("No news for 8 days");
    await line.getByRole("button", { name: "Open", exact: true }).click();

    await expect(page.getByRole("heading", { level: 1, name: found.guest.name })).toBeVisible();
    const memory = page.getByRole("region", { name: "What to remember" });
    await expect(memory).toContainText(found.promise.text);
    await checkAccessibility(page);
    expect(problems).toEqual([]);
  });
});
