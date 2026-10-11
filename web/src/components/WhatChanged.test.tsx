import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { WhatChanged } from "./WhatChanged";

function change(id: string, extra: Partial<S["ChangeItem"]> = {}): S["ChangeItem"] {
  return {
    id,
    version: 4,
    dismissed: false,
    stage_task: false,
    refused: false,
    state: "review",
    waiting: null,
    created_at: "2026-10-09T14:00:00Z",
    note: null,
    source: "SRC-1",
    source_title: "Email from the printer",
    changeset: {
      id: `CS-${id}`,
      summary: "One fact.",
      status: "applied",
      reviewed: false,
      trust: "untrusted",
      ops: [
        {
          index: 0,
          op: "fact",
          status: "applied",
          reason: null,
          group: "op0",
          title: "Proof copies ship Nov 5",
          meta: { owners: [] },
          evidence: { quote: "proof copies will ship on November 5" },
          record: { kind: "fact", id: "FACT-1" },
          ask: null,
        },
      ],
    },
    ...extra,
  };
}

test("a change shows what was done, why, and the highlighted source", async () => {
  const user = userEvent.setup();
  fakeApi({
    "GET changes": () => [change("REQ-1")],
    "GET sources/SRC-1": () => ({
      id: "SRC-1",
      title: "Email from the printer",
      kind: "pasted",
      trust: "untrusted",
      received_at: "2026-10-09T14:00:00Z",
      url: null,
      text: "Thanks. Our proof copies will ship on November 5 by courier.",
    }),
  });
  renderApp(<WhatChanged />);
  expect(await screen.findByText("Proof copies ship Nov 5")).toBeInTheDocument();
  expect(screen.getByText("Recorded a fact")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Show source" }));
  const mark = await screen.findByText((_, el) => el?.tagName === "MARK");
  expect(mark.textContent).toContain("proof copies will ship on November 5");
  expect(screen.getByText("outside content")).toBeInTheDocument();
});

test("Looks good acts at once and offers Undo", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET changes": () => [change("REQ-1")],
    "POST changesets/CS-REQ-1/looks-good": () => ({ ok: "CS-REQ-1" }),
    "POST changesets/CS-REQ-1/reopen": () => ({ ok: "CS-REQ-1" }),
  });
  renderApp(<WhatChanged />);
  await user.click(await screen.findByRole("button", { name: "Looks good" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-REQ-1/looks-good"));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-REQ-1/reopen"));
});

test("send back needs a note", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET changes": () => [change("REQ-1")],
    "POST changesets/CS-REQ-1/send-back": () => ({ request: "REQ-2" }),
  });
  renderApp(<WhatChanged />);
  await user.click(await screen.findByRole("button", { name: /More actions for Email from the printer/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Send back with a note" }));
  const go = screen.getByRole("button", { name: "Send back" });
  expect(go).toBeDisabled();
  await user.type(screen.getByRole("textbox"), "That date is the courier's, not the printer's");
  await user.click(go);
  await waitFor(() => expect(calls.find((c) => c.route.endsWith("send-back"))?.body).toEqual({ note: "That date is the courier's, not the printer's" }));
});

test("a who-is question offers the likely people first", async () => {
  const user = userEvent.setup();
  const held = change("REQ-3");
  held.changeset!.ops[0] = {
    ...held.changeset!.ops[0],
    op: "action.add",
    status: "held",
    reason: "Waiting for you to say who this is",
    title: "Send spine options",
    ask: { id: "Q-7", status: "open", about: "held-op", name: "Robin", options: [{ id: "PER-2", name: "Robin Sample" }, { id: "PER-5", name: "Robin Other" }] },
  };
  const calls = fakeApi({
    "GET changes": () => [held],
    "GET people": () => [
      { id: "PER-2", name: "Robin Sample", role: "Editor" },
      { id: "PER-5", name: "Robin Other", role: "Designer" },
      { id: "PER-9", name: "Lee Third", role: null },
    ],
    "POST questions/Q-7/answer": () => ({ ok: "Q-7" }),
  });
  renderApp(<WhatChanged />);
  const picker = await screen.findByRole("combobox", { name: "Who is “Robin”?" });
  await user.selectOptions(picker, "PER-5");
  await user.click(screen.getByRole("button", { name: "Use this person" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST questions/Q-7/answer")?.body).toEqual({ person: "PER-5" }));
});

test("when nothing was recorded, the assistant's summary says why", async () => {
  const item = change("REQ-9", { source: null, source_title: null, note: "Write an email to the printer" });
  item.changeset!.ops = [];
  item.changeset!.summary = "You asked for an email draft; writing emails isn't something I can do from here.";
  fakeApi({ "GET changes": () => [item] });
  renderApp(<WhatChanged />);
  expect(await screen.findByText(item.changeset!.summary)).toBeInTheDocument();
  expect(screen.getByText("Helper says")).toBeInTheDocument();
  expect(screen.getByText(/Nothing recorded/)).toBeInTheDocument();
});


function noteChange(project: string | null): S["ChangeItem"] {
  const base = change("REQ-9");
  const op = { ...base.changeset!.ops[0], op: "note", title: "A thought", evidence: null, meta: { owners: [], project } };
  return { ...base, changeset: { ...base.changeset!, ops: [op] } };
}

test("a filed note says which project it went under", async () => {
  fakeApi({ "GET changes": () => [noteChange("A project")] });
  renderApp(<WhatChanged />);
  expect(await screen.findByText("Filed a note under A project")).toBeInTheDocument();
});

test("a filed note with no project says so", async () => {
  fakeApi({ "GET changes": () => [noteChange(null)] });
  renderApp(<WhatChanged />);
  expect(await screen.findByText("Filed a note (no project)")).toBeInTheDocument();
});

const stopped = (extra: Partial<S["ChangeItem"]> = {}) =>
  change("REQ-9", {
    state: "needs_you",
    waiting: "Something went wrong processing this: the account is out of credit.",
    note: "File the printer's dates",
    source: null,
    source_title: null,
    changeset: null,
    ...extra,
  });

test("a stopped hand-in keeps Try again as its action and offers Dismiss in its menu, with Undo", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET changes": () => [stopped()],
    "POST requests/REQ-9/dismiss": () => ({ ok: "REQ-9", version: 5 }),
    "POST requests/REQ-9/undismiss": () => ({ ok: "REQ-9", version: 6 }),
  });
  renderApp(<WhatChanged />);
  expect(await screen.findByRole("button", { name: "Try again" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /More actions for/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Dismiss" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST requests/REQ-9/dismiss")?.body).toEqual({ read_version: 4 }),
  );
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST requests/REQ-9/undismiss")?.body).toEqual({ read_version: 5 }),
  );
});

test("a review row has no Dismiss, and a dismissed hand-in leaves Needs attention and is labeled in Done", async () => {
  const user = userEvent.setup();
  fakeApi({
    "GET changes": () => [
      change("REQ-1"),
      stopped({ state: "done", dismissed: true }),
    ],
  });
  renderApp(<WhatChanged />);
  await screen.findByText("Email from the printer");
  expect(screen.queryByText("Dismissed")).toBeNull();
  await user.click(screen.getAllByRole("button", { name: /More actions for/ })[0]);
  expect(await screen.findByRole("menuitem", { name: "Send back with a note" })).toBeInTheDocument();
  expect(screen.queryByRole("menuitem", { name: "Dismiss" })).toBeNull();
  await user.keyboard("{Escape}");
  await user.click(screen.getByRole("button", { name: "Done" }));
  expect(await screen.findByText("Dismissed")).toBeInTheDocument();
  expect(screen.getByText(/you dismissed it/)).toBeInTheDocument();
  expect(screen.queryByText("Email from the printer")).toBeNull();
  await user.click(screen.getByRole("button", { name: "All" }));
  expect(screen.getByText("Dismissed")).toBeInTheDocument();
  expect(screen.getByText("Email from the printer")).toBeInTheDocument();
});

const gated = (extra: Partial<S["ChangeItem"]> = {}) =>
  stopped({ approval: "required", estimate_usd: 0.8, waiting: "About $0.80. Waiting for your go.", ...extra });

test("a run held for its cost is its own row: the estimate, Go with the version read, and no Try again", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET changes": () => [gated()],
    "GET stages/records": () => [],
    "GET stages/ready": () => [],
    "GET stages/requests": () => [],
    "POST requests/REQ-9/go": () => ({ ok: "queued" }),
  });
  renderApp(<WhatChanged />);
  const row = await screen.findByRole("listitem", { name: "File the printer's dates" });
  expect(within(row).getByText("Needs your go")).toBeInTheDocument();
  expect(within(row).getByText("About $0.80")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  await user.click(within(row).getByRole("button", { name: "Go" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST requests/REQ-9/go")?.body).toEqual({ read_version: 4 }));
  expect(await screen.findByText("Approved. Helper is on it.")).toBeInTheDocument();
});

test("a cost-held row can be dismissed from its menu, which has nothing else", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET changes": () => [gated({ estimate_usd: 0.004 })],
    "GET stages/records": () => [],
    "GET stages/ready": () => [],
    "GET stages/requests": () => [],
    "POST requests/REQ-9/dismiss": () => ({ ok: "REQ-9", version: 5 }),
  });
  renderApp(<WhatChanged />);
  const row = await screen.findByRole("listitem", { name: "File the printer's dates" });
  expect(within(row).getByText("Less than a cent")).toBeInTheDocument();
  await user.click(within(row).getByRole("button", { name: /More actions for/ }));
  expect((await screen.findAllByRole("menuitem")).map((i) => i.textContent)).toEqual(["Dismiss"]);
  await user.click(screen.getByRole("menuitem", { name: "Dismiss" }));
  await waitFor(() =>
    expect(calls.find((c) => c.route === "POST requests/REQ-9/dismiss")?.body).toEqual({ read_version: 4 }),
  );
});

test("a second opinion is labeled in words, by where it came from", async () => {
  const other = change("REQ-1", { source_title: "From another account" });
  other.changeset!.second_opinion = "other_account";
  const same = change("REQ-2", { source_title: "From the same account" });
  same.changeset!.second_opinion = "same_account";
  const plain = change("REQ-3", { source_title: "No second opinion" });
  fakeApi({ "GET changes": () => [other, same, plain] });
  renderApp(<WhatChanged />);
  await screen.findByText("From another account");
  const row = (title: string) => screen.getByText(title).closest("li")!;
  expect(within(row("From another account")).getByText("Second opinion from another account")).toBeInTheDocument();
  expect(within(row("From the same account")).getByText("Second opinion from the same account, as a fresh run")).toBeInTheDocument();
  expect(within(row("No second opinion")).queryByText(/Second opinion/)).toBeNull();
});

test("a refused request offers Send to another account, with Try again and Dismiss in its menu", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET changes": () => [stopped({ refused: true })],
    "GET requests/REQ-9/accounts": () => [
      { use: "first/model-a", label: "Work account" },
      { use: "second/model-b", label: "Second account" },
    ],
    "POST requests/REQ-9/retry": () => ({ ok: "REQ-9" }),
  });
  renderApp(<WhatChanged />);
  expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  await user.click(await screen.findByRole("button", { name: "Send to another account" }));
  const chooser = await screen.findByRole("group", { name: "Choose an account to try it with." });
  expect(within(chooser).getAllByRole("button").map((b) => b.textContent)).toEqual(["Work account", "Second account", "Cancel"]);
  await waitFor(() => expect(within(chooser).getByRole("button", { name: "Work account" })).toHaveFocus());
  await user.click(within(chooser).getByRole("button", { name: "Second account" }));
  expect(await screen.findByText("Sent to Second account.")).toBeInTheDocument();
  expect(calls.find((c) => c.route === "POST requests/REQ-9/retry")?.body).toEqual({ use: "second/model-b" });
  await waitFor(() => expect(screen.queryByRole("group", { name: "Choose an account to try it with." })).toBeNull());
  await user.click(screen.getByRole("button", { name: /More actions for/ }));
  expect((await screen.findAllByRole("menuitem")).map((m) => m.textContent)).toEqual(["Try again", "Dismiss"]);
  await user.click(screen.getByRole("menuitem", { name: "Try again" }));
  await waitFor(() => expect(calls.filter((c) => c.route === "POST requests/REQ-9/retry")).toHaveLength(2));
  expect(calls.filter((c) => c.route === "POST requests/REQ-9/retry")[1].body).toBeUndefined();
});

test("with no other account, the chooser says so and points to the AI settings", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET changes": () => [stopped({ refused: true })], "GET requests/REQ-9/accounts": () => [] });
  renderApp(<WhatChanged />);
  await user.click(await screen.findByRole("button", { name: "Send to another account" }));
  expect(await screen.findByText("No other account can take this. You can add one in the AI settings.")).toBeInTheDocument();
  const chooser = screen.getByRole("group", { name: /No other account/ });
  expect(within(chooser).getAllByRole("button").map((b) => b.textContent)).toEqual(["Cancel"]);
  await user.click(within(chooser).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("group", { name: /No other account/ })).toBeNull();
});
