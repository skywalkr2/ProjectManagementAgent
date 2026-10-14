import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { FollowUps } from "./FollowUps";
import { PluginToday } from "./PluginToday";
import { WhatChanged } from "./WhatChanged";

function line(extra: Partial<S["TodayLineView"]> = {}): S["TodayLineView"] {
  return { plugin: "demo", id: "L-1", text: "Chapter 3 is ready to look at", about: null, action: null, action_is: null, why: "", until: null, ...extra };
}

const about = { kind: "demo/chapter", id: "CH-3" };
const on = `kind=${encodeURIComponent(about.kind)}&id=${about.id}`;

const proposal = (): S["ActionProposalView"] => ({
  token: "tok-1",
  action: "demo/check",
  summary: "Check chapter 3",
  ops: [{ op: "note", label: "Note: checked" }],
  files: [],
  previews: [],
  choices: [],
  notes: [],
  expires_at: "2026-10-09T15:00:00Z",
});

test("nothing shows when no plugin has a line", async () => {
  const calls = fakeApi({ "GET plugin-today": () => [] });
  renderApp(<PluginToday />);
  await waitFor(() => expect(calls.length).toBe(1));
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
  expect(screen.queryByRole("region", { name: "More for today" })).toBeNull();
  expect(screen.queryByRole("heading")).toBeNull();
});

test("one row per line, text as plain text, with why and until said as waiting", async () => {
  fakeApi({
    "GET plugin-today": () => [
      line({ text: "Review <b>this</b>", why: "The author is away", until: "2026-10-20" }),
      line({ id: "L-2", text: "Second line", why: "Needs a reader" }),
      line({ id: "L-3", text: "Third line" }),
    ],
  });
  renderApp(<PluginToday />);
  const section = await screen.findByRole("region", { name: "More for today" });
  const rows = within(section).getAllByRole("listitem");
  expect(rows).toHaveLength(3);
  expect(rows[0]).toHaveTextContent("Review <b>this</b>");
  expect(rows[0].querySelector("b")).toBeNull();
  expect(rows[0]).toHaveTextContent(/Waiting: The author is away · until/);
  expect(rows[1]).toHaveTextContent("Waiting: Needs a reader");
  expect(rows[2]).not.toHaveTextContent("Waiting");
  expect(within(section).queryAllByRole("button")).toHaveLength(0);
});

test("a person action opens its review for the line's record, labelled from what the record offers", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET plugin-today": () => [line({ about, action: "demo/check", action_is: "action" })],
    [`GET plugin-actions?${on}`]: () => [{ name: "demo/check", label: "Check the chapter", on: about.kind }],
    "POST plugin-actions/demo/check/preview": () => proposal(),
  });
  renderApp(<PluginToday />);
  await user.click(await screen.findByRole("button", { name: "Check the chapter" }));
  await screen.findByRole("dialog", { name: "Check chapter 3" });
  expect(calls.find((c) => c.route === "POST plugin-actions/demo/check/preview")?.body).toEqual({ target: about, choices: {} });
});

test("a kind of work starts at once with a toast", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET plugin-today": () => [line({ about, action: "demo/read-through", action_is: "task" })],
    [`GET task-kinds?${on}`]: () => [{ name: "demo/read-through", label: "Read it through", on: about.kind }],
    "POST task-kinds/demo/read-through/start": () => ({ request: "REQ-1" }),
  });
  renderApp(<PluginToday />);
  await user.click(await screen.findByRole("button", { name: "Read it through" }));
  expect(await screen.findByText("Started: Read it through")).toBeInTheDocument();
  expect(calls.find((c) => c.route === "POST task-kinds/demo/read-through/start")?.body).toEqual({ about, note: "" });
});

test("a line about the whole workspace looks its action up there, and falls back to a plain label", async () => {
  fakeApi({
    "GET plugin-today": () => [
      line({ action: "demo/tidy", action_is: "action" }),
      line({ id: "L-2", text: "Other", action: "demo/unknown", action_is: "task" }),
    ],
    "GET plugin-actions": () => [{ name: "demo/tidy", label: "Tidy up", on: null }],
    "GET task-kinds": () => [],
  });
  renderApp(<PluginToday />);
  expect(await screen.findByRole("button", { name: "Tidy up" })).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "Open" })).toBeInTheDocument();
});

// ---- the core's own actions

const core = (action: string, target: { kind: string; id: string } | null = about) =>
  line({ about: target, action, action_is: "core" });

const stageList = [
  { id: "first", label: "First step" },
  { id: "second", label: "Second step" },
];

function stageView(extra: Partial<S["StageView"]> = {}): S["StageView"] {
  return {
    record: about,
    title: "Chapter 3",
    version: 5,
    current: "first",
    current_label: "First step",
    next: stageList[1],
    stages: stageList,
    checks: [],
    ready: true,
    ...extra,
  };
}

function change(extra: Partial<S["ChangeItem"]> = {}): S["ChangeItem"] {
  return {
    id: "REQ-4",
    version: 7,
    dismissed: false,
    stage_task: false,
    first_go: false,
    refused: false,
    state: "needs_you",
    approval: "required",
    estimate_usd: 0.8,
    waiting: null,
    created_at: "2026-10-09T14:00:00Z",
    note: null,
    source: null,
    source_title: "A read-through",
    changeset: null,
    ...extra,
  };
}

test("open goes to the record's page, through the app's own way of opening a record", async () => {
  const user = userEvent.setup();
  const open = vi.fn();
  fakeApi({ "GET plugin-today": () => [core("open")] });
  renderApp(<PluginToday onOpenRecord={open} />);
  const button = await screen.findByRole("button", { name: "Open" });
  expect(button).toHaveClass("primary");
  expect(button).toHaveAccessibleDescription("Chapter 3 is ready to look at");
  await user.click(button);
  expect(open).toHaveBeenCalledWith(about.kind, about.id);
});

test("review of a record's own draft opens the record's page", async () => {
  const user = userEvent.setup();
  const open = vi.fn();
  fakeApi({ "GET plugin-today": () => [core("review")] });
  renderApp(<PluginToday onOpenRecord={open} />);
  await user.click(await screen.findByRole("button", { name: "Review" }));
  expect(open).toHaveBeenCalledWith(about.kind, about.id);
});

test("review of the assistant's answer opens that answer's review in What changed, whatever its filter", async () => {
  const user = userEvent.setup();
  const open = vi.fn();
  const reviewed = change({
    id: "REQ-8",
    state: "done",
    approval: null,
    source_title: "Email from the printer",
    changeset: { id: "CS-8", summary: "One thing was filed.", status: "applied", reviewed: true, trust: "trusted", ops: [] },
  } as Partial<S["ChangeItem"]>);
  fakeApi({
    "GET plugin-today": () => [core("review", { kind: "changeset", id: "CS-8" })],
    "GET changes": () => [reviewed],
    "GET stages/records": () => [],
    "GET stages/requests": () => [],
    "GET stages/ready": () => [],
    "GET own-requests": () => [],
  });
  renderApp(
    <>
      <WhatChanged />
      <PluginToday onOpenRecord={open} />
    </>,
  );
  // Finished work is not in the default list.
  await screen.findByText("Nothing needs a look right now.");
  await user.click(await screen.findByRole("button", { name: "Review" }));
  const row = await screen.findByRole("listitem", { name: "Email from the printer" });
  expect(within(row).getByText("One thing was filed.")).toBeInTheDocument();
  await waitFor(() => expect(row).toHaveFocus());
  expect(open).not.toHaveBeenCalled();
});

test("review of an answer that isn't listed falls back to the record", async () => {
  const user = userEvent.setup();
  const open = vi.fn();
  fakeApi({ "GET plugin-today": () => [core("review", { kind: "changeset", id: "CS-9" })] });
  renderApp(<PluginToday onOpenRecord={open} />);
  await user.click(await screen.findByRole("button", { name: "Review" }));
  expect(open).toHaveBeenCalledWith("changeset", "CS-9");
});

test("go gives the go to the queued request with the version read, shows its estimate, and refreshes", async () => {
  const user = userEvent.setup();
  let given = false;
  const calls = fakeApi({
    "GET plugin-today": () => [core("go", { kind: "request", id: "REQ-4" })],
    "GET changes": () => [given ? change({ state: "running", approval: "granted" }) : change()],
    "POST requests/REQ-4/go": () => {
      given = true;
      return { ok: "queued" };
    },
  });
  renderApp(<PluginToday />);
  expect(await screen.findByText("About $0.80")).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Give the go" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST requests/REQ-4/go")?.body).toEqual({ read_version: 7 }));
  expect(await screen.findByText("Approved. Helper is on it.")).toBeInTheDocument();
  // The refreshed request no longer waits, so the line's button becomes the record's.
  expect(await screen.findByRole("button", { name: "Open" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Give the go" })).toBeNull();
});

test("go on a request that no longer waits just opens it", async () => {
  fakeApi({
    "GET plugin-today": () => [core("go", { kind: "request", id: "REQ-4" })],
    "GET changes": () => [],
  });
  renderApp(<PluginToday />);
  expect(await screen.findByRole("button", { name: "Open" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Give the go" })).toBeNull();
});

test("answer opens the question where the questions list shows it", async () => {
  const user = userEvent.setup();
  const open = vi.fn();
  const sections: S["FollowupSection"][] = [
    {
      person: "PER-1",
      name: "Pat Example",
      is_pm: true,
      questions: [
        { id: "Q-5", title: "Which cover?", text: "", links: [], kind: "question", status: "open", sent: null, waiting_days: null, chase_due: false, about: null, options: [] },
      ],
      actions: [],
      message: "",
      to_send: 0,
    },
  ];
  fakeApi({
    "GET plugin-today": () => [core("answer", { kind: "question", id: "Q-5" })],
    "GET followups": () => sections,
    "GET people": () => [],
  });
  renderApp(
    <>
      <FollowUps />
      <PluginToday onOpenRecord={open} />
    </>,
  );
  await screen.findByText("Which cover?");
  const lineRow = screen.getByRole("listitem", { name: "Chapter 3 is ready to look at" });
  await user.click(within(lineRow).getByRole("button", { name: "Answer" }));
  await waitFor(() => expect(screen.getByRole("textbox")).toHaveFocus());
  expect(open).not.toHaveBeenCalled();
});

test("answer falls back to the record when no list shows the question", async () => {
  const user = userEvent.setup();
  const open = vi.fn();
  fakeApi({ "GET plugin-today": () => [core("answer", { kind: "question", id: "Q-5" })] });
  renderApp(<PluginToday onOpenRecord={open} />);
  await user.click(await screen.findByRole("button", { name: "Answer" }));
  expect(open).toHaveBeenCalledWith("question", "Q-5");
});

test("move-stage moves the record to its next stage with the version read, and offers Undo", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET plugin-today": () => [core("move-stage")],
    "GET stages/records": () => [stageView()],
    "POST stages/move": () => ({ changeset: "CS-12", stages: stageView() }),
    "POST changesets/CS-12/undo": () => ({ restored: [about], skipped: [] }),
  });
  renderApp(<PluginToday />);
  await user.click(await screen.findByRole("button", { name: "Move on" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST stages/move")?.body).toEqual({ record: about, to: "second", read_version: 5 }),
  );
  expect(await screen.findByText("Moved Chapter 3 to Second step.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-12/undo"));
});

test("move-stage on a record that isn't ready opens the record instead of moving it", async () => {
  const user = userEvent.setup();
  const open = vi.fn();
  const calls = fakeApi({
    "GET plugin-today": () => [core("move-stage")],
    "GET stages/records": () => [stageView({ ready: false })],
  });
  renderApp(<PluginToday onOpenRecord={open} />);
  await user.click(await screen.findByRole("button", { name: "Open" }));
  expect(open).toHaveBeenCalledWith(about.kind, about.id);
  expect(calls.some((c) => c.route === "POST stages/move")).toBe(false);
});

test("a refused move says why on the row", async () => {
  const user = userEvent.setup();
  fakeApi({
    "GET plugin-today": () => [core("move-stage")],
    "GET stages/records": () => [stageView()],
    "POST stages/move": () => new Refuse(409, "A check no longer passes."),
  });
  renderApp(<PluginToday />);
  await user.click(await screen.findByRole("button", { name: "Move on" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("A check no longer passes.");
});
