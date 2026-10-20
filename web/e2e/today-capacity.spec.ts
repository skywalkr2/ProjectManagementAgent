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

  test("every line's title starts at the same place at 1440px, whichever kind of line it is", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await signIn(page);
    const rows = page.locator("[data-queue-line]");
    await expect(rows.first()).toBeVisible();
    await layoutSettled(page);
    // The words column is the second part of every line, after its pill column.
    const starts = await rows.evaluateAll((els) =>
      els.map((e) => ({
        kind: e.getAttribute("data-queue-line"),
        x: Math.round(e.children[1].getBoundingClientRect().left * 10) / 10,
        pill: Math.round(e.children[0].getBoundingClientRect().width),
      })),
    );
    expect(starts.length).toBeGreaterThan(5);
    expect(new Set(starts.map((r) => r.x)).size, JSON.stringify(starts)).toBe(1);
  });

  test("one decision is one line: no item is on two Today lines, read from the demo through the API", async ({ page }) => {
    await signIn(page);
    type Line = { key: string; kind: string; changeset: string | null; op: number | null; count: number; deciding?: string[]; outcome: Record<string, number> };
    type Change = { state: string; changeset: { id: string; reviewed: boolean; ops: Array<{ index: number; status: string }> } | null };
    const lines: Line[] = await (await page.request.get("api/today/queue")).json();
    const changes: Change[] = await (await page.request.get("api/changes")).json();
    const ops = new Map(changes.filter((c) => c.changeset).map((c) => [c.changeset!.id, c.changeset!.ops]));
    // Where each decision is asked: its own line, under Decide.
    const asked = new Map<string, string>();
    for (const l of lines.filter((x) => (x.kind === "held" || x.kind === "who_is") && x.changeset && x.op !== null)) {
      const key = `${l.changeset}:${l.op}`;
      expect(asked.has(key), `${l.key} and ${asked.get(key)} ask the same thing`).toBe(false);
      asked.set(key, l.key);
    }
    expect(asked.size, "the demo holds at least one decision for the person").toBeGreaterThan(0);
    // A review line counts what was done and nothing that is asked elsewhere, and says where the rest waits.
    for (const l of lines.filter((x) => x.kind === "review" && x.changeset)) {
      const mine = ops.get(l.changeset!) ?? [];
      const elsewhere = mine.filter((o) => asked.has(`${l.changeset}:${o.index}`));
      const counted = mine.filter((o) => (o.status === "applied" || o.status === "held") && !elsewhere.includes(o));
      if (counted.length > 0) expect(l.count, l.key).toBe(counted.length);
      expect([...(l.deciding ?? [])].sort(), l.key).toEqual(elsewhere.map((o) => asked.get(`${l.changeset}:${o.index}`)!).sort());
    }
    // A change whose only ops are asked elsewhere has no review line at all.
    for (const c of changes.filter((x) => x.changeset && x.state === "review" && !x.changeset.reviewed)) {
      const live = c.changeset!.ops.filter((o) => o.status === "applied" || o.status === "held");
      if (live.length > 0 && live.every((o) => asked.has(`${c.changeset!.id}:${o.index}`))) {
        expect(lines.some((l) => l.kind === "review" && l.changeset === c.changeset!.id), c.changeset!.id).toBe(false);
      }
    }
  });
});
