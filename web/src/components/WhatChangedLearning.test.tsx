// Learning on What changed (design 7.18): the Learned line on a card, and which knowledge shaped the work.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { learnedLine, project } from "../lib/learned-fixtures";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { WhatChanged } from "./WhatChanged";

const RULE = "Questions about release dates go to the schedule, not to people.";

const entry = (over: Partial<S["AppliedEntryView"]> = {}): S["AppliedEntryView"] => ({
  id: "LES-3",
  kind: "lesson",
  version: 2,
  text: RULE,
  status: "active",
  applies_to: { scope: "workspace" },
  ...over,
});

function change(id: string, changeset: Partial<S["ChangesetView"]> | null, extra: Partial<S["ChangeItem"]> = {}): S["ChangeItem"] {
  return {
    id,
    version: 4,
    dismissed: false,
    stage_task: false,
    first_go: false,
    refused: false,
    state: "review",
    waiting: null,
    created_at: "2026-10-09T14:00:00Z",
    note: null,
    source: null,
    source_title: "Email from the printer",
    changeset: changeset && {
      id: `CS-${id}`,
      summary: "One fact.",
      status: "applied",
      reviewed: false,
      trust: "trusted",
      ops: [],
      ...changeset,
    },
    ...extra,
  };
}

function show(items: S["ChangeItem"][], extra: Routes = {}) {
  return fakeApi({
    "GET changes": () => items,
    "GET projects": () => [project("PRJ-1", "Spring launch"), project("PRJ-2", "Autumn list")],
    "GET knowledge/learned": () => ({ lines: [] }),
    "POST changesets/CS-9/undo": () => ({ restored: [1], skipped: [] }),
    ...extra,
  });
}

const posted = (calls: { route: string; body: unknown }[], route: string) => calls.find((c) => c.route === route)?.body;

test("the Learned line shows under the card the correction was about, and Keep works from there", async () => {
  const user = userEvent.setup();
  const calls = show([change("REQ-1", {})], {
    "GET knowledge/learned": () => ({ lines: [learnedLine({ changeset: "CS-REQ-1" })] }),
    "POST knowledge/LES-1/keep": () => ({ changeset: "CS-9" }),
  });
  renderApp(<WhatChanged />);
  const row = (await screen.findByText("Email from the printer")).closest("li")!;
  expect(await within(row).findByText(/Interior files go to the editor before the printer/)).toBeInTheDocument();
  await user.click(within(row).getByRole("button", { name: "Keep" }));
  await waitFor(() => expect(posted(calls, "POST knowledge/LES-1/keep")).toEqual({ read_version: 3 }));
});

test("work redone after a send-back shows what is being learned from the send-back, even while the card is closed", async () => {
  show([change("REQ-2", null, { state: "queued", redoes: "CS-REQ-1" })], {
    "GET knowledge/learned": () => ({
      lines: [learnedLine({ changeset: "CS-REQ-1", state: "learning", proposal: null, waiting: "With the assistant, starting now" })],
    }),
  });
  renderApp(<WhatChanged />);
  const row = (await screen.findByText("Email from the printer")).closest("li")!;
  expect(await within(row).findByRole("status")).toHaveTextContent("Learning from this…");
  expect(within(row).getByText("With the assistant, starting now")).toBeInTheDocument();
});

test("a card says which knowledge shaped it, linked to the entry", async () => {
  show([change("REQ-1", { applied: [entry()] })]);
  renderApp(<WhatChanged />);
  const because = await screen.findByRole("list", { name: "What shaped this" });
  expect(within(because).getByText("Because you told me:")).toBeInTheDocument();
  const link = within(because).getByRole("link", { name: RULE });
  expect(link.getAttribute("href")).toContain("#records/knowledge");
});

test("a first run on a standing-in account says which one", async () => {
  show([change("REQ-1", { first_on_account: "second" })]);
  renderApp(<WhatChanged />);
  expect(await screen.findByText("First run on second")).toBeInTheDocument();
});

test("This doesn't apply here narrows the entry by leaving a project out, at once with Undo", async () => {
  const user = userEvent.setup();
  const calls = show([change("REQ-1", { applied: [entry()] })], { "POST knowledge/LES-3/narrow": () => ({ changeset: "CS-9" }) });
  renderApp(<WhatChanged />);
  await user.click(await screen.findByRole("button", { name: `More actions for ${RULE}` }));
  await user.click(screen.getByRole("menuitem", { name: "This doesn't apply here" }));
  const pick = await screen.findByRole("combobox", { name: "Stop it applying to" });
  expect(screen.getByRole("button", { name: "Narrow it" })).toBeDisabled();
  await waitFor(() => expect(within(pick).getAllByRole("option")).toHaveLength(3));
  await user.selectOptions(pick, "PRJ-1");
  await user.click(screen.getByRole("button", { name: "Narrow it" }));
  await waitFor(() =>
    expect(posted(calls, "POST knowledge/LES-3/narrow")).toEqual({ read_version: 2, applies_to: { scope: "workspace", except: ["PRJ-1"] } }),
  );
  expect(await screen.findByText("Narrowed. It no longer applies there.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-9/undo"));
});

test("This doesn't apply here can retire the entry instead, with Undo", async () => {
  const user = userEvent.setup();
  const calls = show([change("REQ-1", { applied: [entry()] })], { "POST knowledge/LES-3/retire": () => ({ changeset: "CS-9" }) });
  renderApp(<WhatChanged />);
  await user.click(await screen.findByRole("button", { name: `More actions for ${RULE}` }));
  await user.click(screen.getByRole("menuitem", { name: "This doesn't apply here" }));
  await user.click(await screen.findByRole("button", { name: "Retire it" }));
  await waitFor(() => expect(posted(calls, "POST knowledge/LES-3/retire")).toEqual({ read_version: 2 }));
  expect(await screen.findByText("Retired. It won't guide the assistant any more.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-9/undo"));
});

test("an entry for one project only can be retired but not narrowed, and says so", async () => {
  const user = userEvent.setup();
  show([change("REQ-1", { applied: [entry({ applies_to: { scope: "projects", projects: ["PRJ-1"] } })] })]);
  renderApp(<WhatChanged />);
  await user.click(await screen.findByRole("button", { name: `More actions for ${RULE}` }));
  await user.click(screen.getByRole("menuitem", { name: "This doesn't apply here" }));
  expect(await screen.findByText("It applies to one project only, so the way to stop it is to retire it.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Narrow it" })).toBeNull();
  expect(screen.getByRole("button", { name: "Retire it" })).toBeInTheDocument();
});

test("a fact, or an entry already retired, shows no menu to change it", async () => {
  show([
    change("REQ-1", {
      applied: [entry({ id: "FACT-1", kind: "fact", text: "The interior is due on the 16th.", applies_to: null }), entry({ id: "LES-4", text: "An old rule.", status: "retired" })],
    }),
  ]);
  renderApp(<WhatChanged />);
  expect(await screen.findByText("The interior is due on the 16th.")).toBeInTheDocument();
  expect(screen.getByText("An old rule.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /More actions for (The interior|An old)/ })).toBeNull();
});
