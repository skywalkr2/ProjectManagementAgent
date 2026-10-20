// The yes to an AI account reading work mail and notes (design 6.16, 7.7), in a real browser. The access server
// (`--standin-account`) has a second stand-in account whose person said Not now, so Today offers the yes: one line, one
// button, an Undo, and the line is gone once it is given. Screenshots go to the folder named by E2E_SHOTS, when it is set.
import { expect, test, type Page } from "@playwright/test";

async function shoot(page: Page, name: string) {
  const folder = process.env.E2E_SHOTS;
  if (folder) await page.screenshot({ path: `${folder}/${name}.png`, fullPage: false });
}

const SAVED = { timeout: 20_000 };

test("Today offers Allow for an account the person said Not now about, and Allow and Undo work", async ({ page }) => {
  await page.goto("?token=e2e-token");
  const line = page.locator('[data-queue-line="work_access"]');
  await expect(line).toBeVisible(SAVED);
  await expect(line).toContainText("Let Second stand-in read your work mail and notes");
  await expect(line.getByRole("button")).toHaveCount(1);
  await shoot(page, "work-access-line");

  await line.getByRole("button", { name: "Allow Second stand-in to read your work mail and notes" }).click();
  await expect(page.getByText("Second stand-in can now read your work mail and notes.")).toBeVisible(SAVED);
  await expect(line).toHaveCount(0, SAVED);
  await shoot(page, "work-access-allowed");

  await page.getByRole("region", { name: "Notifications" }).getByRole("button", { name: "Undo" }).click();
  await expect(line).toBeVisible(SAVED);
});
