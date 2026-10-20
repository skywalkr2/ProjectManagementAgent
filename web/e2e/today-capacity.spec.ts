// Today's capacity (C47, C56; the UI/UX re-review of B-7, R3): on a fresh demo, six lines fit at 1280x720 with their
// meta on one line. It has a server of its own, because the acceptance scenario leaves lines of its own on Today that
// would take the room this check measures.
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

async function layoutSettled(page: Page) {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        let height = -1;
        let same = 0;
        const frame = () => {
          const now = document.documentElement.scrollHeight;
          same = now === height ? same + 1 : 0;
          height = now;
          if (same >= 20) resolve();
          else requestAnimationFrame(frame);
        };
        requestAnimationFrame(frame);
      }),
  );
}

test.describe("Today's capacity", () => {
  test("Today at 1280x720 shows six lines in full when the held and moved lines are as long as the demo's, each with its meta on one line", async ({ page }) => {
    const base = { untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {}, count: 1 };
    const spine = { record: "ACT-1", owners: ["Robin Sample"], reporter: "Robin Sample", told: [] as string[] };
    const lines = [
      { ...base, key: "decision:Q-1", group: "decide", kind: "decision", text: "Cover finish for the hardcover: matte or soft-touch?", question: "Q-1" },
      {
        ...base,
        key: "held:CS-1:0",
        group: "decide",
        kind: "held",
        changeset: "CS-1",
        op: 0,
        text: "Close 'Send two spine options'",
        untrusted: true,
        held: { ask: "close", item: "Send two spine options", quote: "the spine options are in the shared folder and the printer has them", ...spine },
      },
      {
        ...base,
        key: "held:CS-2:0",
        group: "decide",
        kind: "held",
        changeset: "CS-2",
        op: 0,
        text: "Drop 'Confirm the seating plan for the launch reading'",
        untrusted: true,
        held: { ask: "drop", item: "Confirm the seating plan for the launch reading", quote: "the seating plan is no longer needed, we dropped the reading", ...spine, told: ["Casey Moor", "Jordan Pike"], told_on: "2026-10-10" },
      },
      {
        ...base,
        key: "moved:REQ-9",
        group: "decide",
        kind: "moved",
        count: 2,
        text: "Cover review",
        questions: ["Q-2", "Q-3"],
        changeset: "CS-9",
        after_move: { kind: "event", record: "EVT-1", title: "Cover review", to: "2026-10-22", earlier: false, by: "pm", replaced: false, request: "REQ-9", changeset: "CS-9", others: [{ name: "Robin Sample", count: 1 }] },
      },
      { ...base, key: "backup", group: "risk", kind: "backup", state: "failed" },
      { ...base, key: "overdue:ACT-9", group: "risk", kind: "overdue", subject: "Approve the back-cover copy", actions: ["ACT-9"] },
      { ...base, key: "overdue:ACT-8", group: "risk", kind: "overdue", subject: "Send the final interior file to the printer", actions: ["ACT-8"] },
    ];
    await page.route("**/api/today/queue", (route) => route.fulfill({ json: lines }));
    await page.setViewportSize({ width: 1280, height: 720 });
    await signIn(page);
    const rows = page.locator("[data-queue-line]");
    await expect(rows.first()).toBeVisible();
    await layoutSettled(page);
    const boxes = await rows.evaluateAll((els) =>
      els.map((e) => {
        const meta = e.querySelector<HTMLElement>("p[class*='meta']");
        const style = meta ? getComputedStyle(meta) : null;
        return {
          bottom: e.getBoundingClientRect().bottom,
          metaHeight: meta ? meta.getBoundingClientRect().height : 0,
          metaLine: style ? parseFloat(style.lineHeight) : 0,
          nowrap: style?.whiteSpace === "nowrap",
          outsideInMeta: !!meta?.querySelector("[data-outside]"),
          outsideInPill: !!e.querySelector("[data-outside]") && !meta?.querySelector("[data-outside]"),
        };
      }),
    );
    // Six lines are in the window, whole, and not by a hair.
    expect(boxes.filter((b) => b.bottom <= 720).length).toBeGreaterThanOrEqual(6);
    expect(boxes[5].bottom).toBeLessThanOrEqual(700);
    // Every line's meta is one line.
    for (const b of boxes.filter((x) => x.metaHeight > 0)) {
      expect(b.nowrap).toBe(true);
      expect(b.metaHeight).toBeLessThanOrEqual(b.metaLine + 1);
      expect(b.outsideInMeta).toBe(false);
    }
    expect(boxes.filter((b) => b.outsideInPill).length).toBe(2);
    await page.unrouteAll({ behavior: "ignoreErrors" });
  });
});
