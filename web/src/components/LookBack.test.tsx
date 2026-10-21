import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { day } from "../lib/dates";
import { fakeApi, renderApp } from "../test-utils";
import { CoverageLine } from "./Coverage";

// Mid-morning on a made-up Monday; only the date is faked so waiting still works.
const NOW = new Date(2026, 9, 19, 9, 0);

function mail(extra: Partial<S["WatchSourceView"]> = {}): S["WatchSourceView"] {
  const read = new Date(2026, 9, 19, 7, 40).toISOString();
  return {
    id: "m",
    label: "Work mail",
    connector: "kind-a",
    connector_label: "A kind",
    enabled: true,
    every_minutes: 15,
    items: 9,
    last: { outcome: "baseline", started_at: read, new: 0, changed: 0, removed: 0 },
    read_at: read,
    failures: 0,
    problem: null,
    looked_back_to: "2026-10-05",
    look_back_choices: [30, 90, 365],
    ...extra,
  };
}

const view = (over: Partial<S["LookBackView"]> = {}): S["LookBackView"] => ({
  days: 90,
  from_date: "2026-07-07",
  count: 5,
  estimate_usd: 0.4,
  unpriced: 0,
  reaches: true,
  available_from: null,
  taken: 0,
  started: false,
  ...over,
});

function open(sources: S["WatchSourceView"][], routes: Parameters<typeof fakeApi>[0] = {}) {
  const calls = fakeApi({ "GET watch": () => sources, ...routes });
  renderApp(<CoverageLine />);
  return calls;
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});
afterEach(() => vi.useRealTimers());

test("a mail source taken in quietly says the day before which it was not looked at", async () => {
  open([mail()]);
  const note = await screen.findByText(`Not looked at before ${day("2026-10-05")}`);
  expect(note.getAttribute("data-coverage")).toBe("looked");
  expect(note.closest("[data-coverage-line]")).not.toBeNull();
  expect(screen.getByRole("button", { name: "Look further back in Work mail" })).toHaveTextContent("Look further back");
});

test("a source with no look-back date says nothing about it and offers no way to look further back", async () => {
  open([mail({ looked_back_to: null, look_back_choices: [] })]);
  await screen.findByText(/Checked 1 connection/);
  expect(screen.queryByText(/Not looked at before/)).toBeNull();
  expect(screen.queryByRole("button", { name: /Look further back/ })).toBeNull();
});

test("looking further back is a list to pick from, with the cursor in it, never a box to type in", async () => {
  const user = userEvent.setup();
  open([mail()]);
  await user.click(await screen.findByRole("button", { name: /Look further back/ }));
  const list = await screen.findByRole("combobox", { name: "How much further" });
  expect(list).toHaveFocus();
  expect(within(list).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose how far", "30 more days", "90 more days", "365 more days"]);
  expect(screen.queryByRole("textbox")).toBeNull();
  expect(screen.getByRole("button", { name: "Look back" })).toBeDisabled();
});

test("picking how far shows the count and the cost before anything is read, and Look back does it", async () => {
  const user = userEvent.setup();
  let requested = 0;
  const calls = open([mail()], {
    "GET watch/m/look-back?days=90": () => {
      requested += 1;
      return view();
    },
    "POST watch/m/look-back": () => view({ taken: 5, started: true }),
  });
  await user.click(await screen.findByRole("button", { name: /Look further back/ }));
  await user.selectOptions(await screen.findByRole("combobox", { name: "How much further" }), "90");
  expect(await screen.findByText(`5 items from ${day("2026-07-07")} on. About $0.40 in all.`)).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST watch/m/look-back")).toBe(false);
  expect(requested).toBe(1);
  await user.click(screen.getByRole("button", { name: "Look back" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST watch/m/look-back")?.body).toEqual({ days: 90 }));
  expect(await screen.findByText("Taking in 5 older items from Work mail.")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole("combobox", { name: "How much further" })).toBeNull());
});

test("mail with no price says it uses the plan's allowance, and a held look says it waits for the go", async () => {
  const user = userEvent.setup();
  open([mail()], {
    "GET watch/m/look-back?days=30": () => view({ count: 1, estimate_usd: null, unpriced: 1 }),
    "POST watch/m/look-back": () => view({ count: 1, taken: 1, started: false }),
  });
  await user.click(await screen.findByRole("button", { name: /Look further back/ }));
  await user.selectOptions(await screen.findByRole("combobox", { name: "How much further" }), "30");
  expect(await screen.findByText(`1 item from ${day("2026-07-07")} on. It uses your plan's allowance.`)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Look back" }));
  expect(await screen.findByText("Taking in Work mail waits for you to start it.")).toBeInTheDocument();
});

test("when the source doesn't reach that far back the answer says where its mail starts, before and after", async () => {
  const user = userEvent.setup();
  open([mail()], {
    "GET watch/m/look-back?days=365": () => view({ reaches: false, available_from: "2026-09-29", count: 2 }),
    "POST watch/m/look-back": () => view({ reaches: false, available_from: "2026-09-29", count: 2, taken: 2, started: true }),
  });
  await user.click(await screen.findByRole("button", { name: /Look further back/ }));
  await user.selectOptions(await screen.findByRole("combobox", { name: "How much further" }), "365");
  expect(await screen.findByText(new RegExp(`Only mail from ${day("2026-09-29")} is available to read\\.`))).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Look back" }));
  expect(await screen.findByText(new RegExp(`Taking in 2 older items from Work mail\\. Only mail from ${day("2026-09-29")} is available to read\\.`))).toBeInTheDocument();
});

test("nothing to take in says so and leaves the button off", async () => {
  const user = userEvent.setup();
  open([mail()], { "GET watch/m/look-back?days=30": () => view({ count: 0, estimate_usd: null }) });
  await user.click(await screen.findByRole("button", { name: /Look further back/ }));
  await user.selectOptions(await screen.findByRole("combobox", { name: "How much further" }), "30");
  expect(await screen.findByText("There is no mail in those days to take in.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Look back" })).toBeDisabled();
});
