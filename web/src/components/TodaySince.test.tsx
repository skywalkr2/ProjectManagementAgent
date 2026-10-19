import "@testing-library/jest-dom/vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { RestartProvider } from "../lib/restart";
import { forgetLine } from "../lib/today";
import { fakeApi, renderApp, statusFixture } from "../test-utils";
import { Today } from "./Today";

// What changed since yesterday on Today (design 6.32, 7.7): one line in the risk group that starts with Look over and counts
// what is unseen in plain words. Look over opens the list.

type Line = S["QueueLineView"];

function line(kind: Line["kind"], over: Partial<Line> = {}): Line {
  return { key: `${kind}:1`, group: "send", kind, count: 1, untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {}, ...over };
}

const since = (outcome: Record<string, number>, over: Partial<Line> = {}) =>
  line("since_yesterday", { key: "since_yesterday", group: "risk", count: Object.values(outcome).reduce((a, b) => a + b, 0), outcome, ...over });

function show(lines: Line[]) {
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => undefined, removeEventListener: () => undefined }));
  fakeApi({
    "GET today/queue": () => lines,
    "GET changes": () => [],
    "GET followups": () => [],
    "GET plugin-today": () => [],
    "GET stages/records": () => [],
    "GET stages/ready": () => [],
    "GET stages/requests": () => [],
    "GET today/agenda": () => [],
    "GET today/todo": () => [],
    "GET today/arrived": () => ({ items: [], left_out: 0, set_aside: 0 }),
    "GET watch": () => [],
    "GET projects": () => [],
    "GET people": () => [],
    "GET status": () => statusFixture(),
    "GET runtime-config": () => ({ instance: null }),
  });
  const onView = vi.fn();
  renderApp(
    <RestartProvider hellos={1}>
      <Today workspace="Workspace" onView={onView} onAddSource={vi.fn()} onOpenGuide={vi.fn()} onOpenRecord={vi.fn()} shortcuts={{ next: "j", previous: "k" }} />
    </RestartProvider>,
  );
  return { onView };
}

afterEach(() => {
  vi.unstubAllGlobals();
  forgetLine();
});

const TITLE = "Look over what changed since yesterday";

test("the line says what is unseen in plain words, in the order closed, moved, new", async () => {
  show([since({ added: 4, closed: 3, moved: 2 })]);
  const row = (await screen.findByRole("group", { name: TITLE })) as HTMLElement;
  expect(row).toHaveTextContent("3 closed, 2 moved, 4 new");
  expect(within(row).getByRole("button", { name: "Look over" })).toBeInTheDocument();
});

test("Look over is the one button and opens the list; the line is in the risk group", async () => {
  const user = userEvent.setup();
  const { onView } = show([since({ closed: 1 })]);
  const row = (await screen.findByRole("group", { name: TITLE })) as HTMLElement;
  expect(within(row).getAllByRole("button").map((b) => b.textContent)).not.toContain("Undo");
  await user.click(within(row).getByRole("button", { name: "Look over" }));
  expect(onView).toHaveBeenCalledWith("work/since");
});

test("with nothing unseen there is no line", async () => {
  show([]);
  await screen.findByRole("heading", { level: 1, name: "Today" });
  expect(screen.queryByRole("group", { name: TITLE })).not.toBeInTheDocument();
});
