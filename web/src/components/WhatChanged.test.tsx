import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { revealOrKeep } from "../lib/reveal";
import { day } from "../lib/dates";
import { fakeApi, renderApp } from "../test-utils";
import { ChangeRow, WhatChanged } from "./WhatChanged";

function change(id: string, extra: Partial<S["ChangeItem"]> = {}): S["ChangeItem"] {
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
  expect(screen.getByText("From outside · not instructions")).toBeInTheDocument();
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

test("send back asks what to do differently, with Undo what it did first ticked, and unticking it keeps what it did", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    "GET changes": () => [change("REQ-1")],
    "POST changesets/CS-REQ-1/send-back": () => ({ request: "REQ-2" }),
  });
  renderApp(<WhatChanged />);
  await user.click(await screen.findByRole("button", { name: /More actions for Email from the printer/ }));
  await user.click(await screen.findByRole("menuitem", { name: "Send back with a note" }));
  expect(screen.getByLabelText("What should Helper do differently?")).toBeInTheDocument();
  const undo = screen.getByRole("checkbox", { name: "Undo what it did first" });
  expect(undo).toBeChecked();
  await user.click(undo);
  await user.type(screen.getByRole("textbox"), "Keep the dates, change the names");
  await user.click(screen.getByRole("button", { name: "Send back" }));
  await waitFor(() => expect(calls.find((c) => c.route.endsWith("send-back"))?.body).toEqual({ note: "Keep the dates, change the names", undo_first: false }));
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

test("a change's line says what was done, as what it was, not as a count of things", async () => {
  const item = change("REQ-8");
  const op = (index: number, kind: string, status = "applied"): S["OpView"] => ({ ...item.changeset!.ops[0], index, op: kind, status: status as S["OpView"]["status"], group: `op${index}` });
  item.changeset!.ops = [op(0, "action.add"), op(1, "action.add"), op(2, "action.add"), op(3, "note"), op(4, "question.add", "held"), op(5, "some.other.kind")];
  fakeApi({ "GET changes": () => [item] });
  renderApp(<WhatChanged />);
  expect(await screen.findByText(/Added 3 to-dos, Asked 1 question, Filed 1 note, Helper did 1 thing/)).toBeInTheDocument();
});

function noteChange(project: string | null): S["ChangeItem"] {
  const base = change("REQ-9");
  const op = { ...base.changeset!.ops[0], op: "note", title: "A thought", evidence: null, meta: { owners: [], project } };
  return { ...base, changeset: { ...base.changeset!, ops: [op] } };
}

test("an action the assistant added for someone not yet told says to send on its row", async () => {
  const base = change("REQ-9");
  const op = { ...base.changeset!.ops[0], op: "action.add", title: "Send the proof", evidence: null, meta: { owners: ["Robin Sample"], to_send: true } };
  fakeApi({ "GET changes": () => [{ ...base, changeset: { ...base.changeset!, ops: [op] } }] });
  renderApp(<WhatChanged />);
  expect(await screen.findByText("Robin Sample · To send")).toBeInTheDocument();
});

test("a changed field is named by its label and its date is written as elsewhere, never as its key and an ISO date", async () => {
  const base = change("REQ-9");
  const set = (index: number, field: string, value: unknown): S["OpView"] => ({ ...base.changeset!.ops[0], index, op: "record.set", title: "Send two spine options", group: `op${index}`, evidence: null, meta: { owners: [], field, value } });
  fakeApi({ "GET changes": () => [{ ...base, changeset: { ...base.changeset!, ops: [set(0, "due", "2026-10-19"), set(1, "why_they_matter", "Runs the press")] } }] });
  renderApp(<WhatChanged />);
  expect(await screen.findByText(`Due date: ${day("2026-10-19")}`)).toBeInTheDocument();
  expect(screen.getByText("Why they matter: Runs the press")).toBeInTheDocument();
  expect(screen.queryByText(/2026-10-19/)).toBeNull();
  expect(screen.queryByText(/^due:/)).toBeNull();
});

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
  stopped({ approval: "required", estimate_usd: 0.8, waiting: "About $0.80. Waiting for you to start it.", ...extra });

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
  expect(within(row).getByText("Waiting for you to start it")).toBeInTheDocument();
  expect(within(row).getByText("About $0.80")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  await user.click(within(row).getByRole("button", { name: "Start" }));
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
  expect(within(row("From the same account")).getByText("Second opinion from the same account, starting fresh")).toBeInTheDocument();
  expect(within(row("No second opinion")).queryByText(/Second opinion/)).toBeNull();
});

test("work a plugin did in answer to a change says which change it followed", async () => {
  const after = change("REQ-1", { source_title: "Chapter updates", follows: "CS-3", follows_summary: "Accept chapter 4" });
  fakeApi({ "GET changes": () => [after] });
  renderApp(<WhatChanged />);
  const title = await screen.findByText("Chapter updates");
  expect(within(title.closest("li")!).getByText("After: Accept chapter 4")).toBeInTheDocument();
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
  expect(await screen.findByText("No other account can do this. Add one in AI accounts.")).toBeInTheDocument();
  const chooser = screen.getByRole("group", { name: /No other account/ });
  expect(within(chooser).getAllByRole("button").map((b) => b.textContent)).toEqual(["Cancel"]);
  await user.click(within(chooser).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("group", { name: /No other account/ })).toBeNull();
});

test("a request stopped because no account may see its level offers one action that lets the account see it, with Undo", async () => {
  const user = userEvent.setup();
  const key = "ai.providers.first.allowed_data";
  const calls = fakeApi({
    "GET changes": () => [stopped({ cause: { kind: "data_level", level: "internal", account: "first" } })],
    "POST requests/REQ-9/allow-data": () => ({
      request: "REQ-9",
      account: "first",
      level: "internal",
      saved: {
        changes: [{ key, before: ["open"], after: ["open", "internal"], was_default: false, is_default: false }],
        fingerprint: "fp-2",
        needs_restart: false,
      },
    }),
    "POST settings": () => ({ changes: [], fingerprint: "fp-3", needs_restart: false }),
  });
  renderApp(<WhatChanged />);
  const row = await screen.findByRole("listitem", { name: "File the printer's dates" });
  expect(within(row).queryByRole("button", { name: "Try again" })).toBeNull();
  await user.click(within(row).getByRole("button", { name: "Let first see internal material" }));
  expect(await screen.findByText("first can now see internal material. Trying again.")).toBeInTheDocument();
  expect(calls.filter((c) => c.route === "POST requests/REQ-9/allow-data")).toHaveLength(1);
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST settings")?.body).toEqual({ changes: { [key]: ["open"] }, reset: [], fingerprint: "fp-2" }));
});

test("a request waiting for the person to be named offers Say who you are, which opens the setup guide at that step", async () => {
  const user = userEvent.setup();
  const open = vi.fn();
  const calls = fakeApi({
    "GET changes": () => [stopped({ waiting: "Say who you are first", cause: { kind: "no_person" } })],
  });
  renderApp(<WhatChanged onOpenGuide={open} />);
  const row = await screen.findByRole("listitem", { name: "File the printer's dates" });
  expect(within(row).queryByRole("button", { name: "Try again" })).toBeNull();
  expect(within(row).getByText("Say who you are first")).toBeInTheDocument();
  await user.click(within(row).getByRole("button", { name: "Say who you are" }));
  expect(open).toHaveBeenCalledWith("workspace");
  expect(calls.some((c) => c.route.startsWith("POST"))).toBe(false);
});

test("a change asked for before this screen opened is opened once its list has loaded", async () => {
  const done = change("REQ-2", { state: "done" });
  done.changeset!.summary = "Added the action about the proofs.";
  fakeApi({ "GET changes": () => [change("REQ-1", { state: "done" }), done] });
  // The person chose "Where it came from" on another screen, which then opened this one.
  expect(revealOrKeep("changeset", "CS-REQ-2")).toBe(false);
  renderApp(<WhatChanged />);
  expect(await screen.findByText("Added the action about the proofs.")).toBeInTheDocument();
  expect(screen.queryByText("One fact.")).toBeNull();
});

test("each item in a review card has its own Change this, which sends back that item and no other", async () => {
  const user = userEvent.setup();
  const two = change("REQ-1");
  two.changeset!.ops.push({
    index: 1,
    op: "action.add",
    status: "applied",
    reason: null,
    group: "op1",
    title: "Send two spine options",
    meta: { owners: [] },
    evidence: null,
    record: { kind: "action", id: "ACT-7" },
    ask: null,
  });
  const calls = fakeApi({
    "GET changes": () => [two],
    "POST items/action/ACT-7/change": () => ({ ok: "ACT-7", request: "REQ-9", signal: "SIG-1" }),
  });
  renderApp(<WhatChanged />);
  await user.click(await screen.findByRole("button", { name: "More actions for Send two spine options" }));
  await user.click(await screen.findByRole("menuitem", { name: "Change this" }));
  await user.type(await screen.findByRole("textbox", { name: "Your note" }), "Make it three options");
  await user.click(screen.getByRole("button", { name: "Ask for the change" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST items/action/ACT-7/change")?.body).toEqual({ note: "Make it three options" }));
  // The fact beside it was not sent back.
  expect(calls.some((c) => c.route.startsWith("POST items/fact/"))).toBe(false);
  expect(calls.some((c) => c.route.endsWith("send-back"))).toBe(false);
});

test("an item that was not applied has no Change this", async () => {
  const user = userEvent.setup();
  const held = change("REQ-1");
  held.changeset!.ops[0] = { ...held.changeset!.ops[0], status: "refused", reason: "No such person" };
  fakeApi({ "GET changes": () => [held] });
  renderApp(<WhatChanged />);
  await user.click(await screen.findByRole("button", { name: "More actions for Proof copies ship Nov 5" }));
  expect(await screen.findByRole("menuitem", { name: "Show source" })).toBeInTheDocument();
  expect(screen.queryByRole("menuitem", { name: "Change this" })).toBeNull();
});

test("a finished item shows what it cost beside its estimate", async () => {
  fakeApi({});
  const item = change("REQ-1", { state: "done", spent_usd: 0.03, range_usd: [0.02, 0.08] });
  renderApp(
    <ol>
      <ChangeRow item={item} reveal={0} open />
    </ol>,
  );
  expect(await screen.findByText("Cost $0.03, estimated at $0.02 to $0.08")).toBeInTheDocument();
});

test("a Today line for a new source's intake narrows the list to what that intake found, until it is cleared", async () => {
  const user = userEvent.setup();
  fakeApi({
    "GET changes": () => [
      change("REQ-1", { intake: "m" }),
      change("REQ-2", { intake: "other", changeset: { ...change("REQ-2").changeset!, ops: [{ ...change("REQ-2").changeset!.ops[0], title: "Another source's thing" }] } }),
      change("REQ-3", { changeset: { ...change("REQ-3").changeset!, ops: [{ ...change("REQ-3").changeset!.ops[0], title: "A pasted note's thing" }] } }),
    ],
    "GET watch": () => [{ id: "m", label: "Inbox", connector: "kind-a", connector_label: "A kind", enabled: true, every_minutes: 15, items: 0, last: null, read_at: null, failures: 0, problem: null }],
  });
  renderApp(<WhatChanged />);
  expect(await screen.findByText("Another source's thing")).toBeInTheDocument();
  revealOrKeep("intake", "m");
  await waitFor(() => expect(screen.queryByText("Another source's thing")).toBeNull());
  expect(screen.getByText("Proof copies ship Nov 5")).toBeInTheDocument();
  expect(screen.queryByText("A pasted note's thing")).toBeNull();
  expect(await screen.findByText("Found in Inbox")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Show everything" }));
  expect(await screen.findByText("A pasted note's thing")).toBeInTheDocument();
  expect(screen.getByText("Another source's thing")).toBeInTheDocument();
});

// ---- the first results are one clear list ----------------------------------------------------------------------------

function asking(id: string, who: string): S["ChangeItem"] {
  const item = change(id, { state: "done" });
  item.changeset!.ops[0] = {
    ...item.changeset!.ops[0],
    op: "action.add",
    status: "held",
    reason: "Waiting for you to say who this is",
    title: `Send spine options (${who})`,
    ask: { id: `Q-${id}`, status: "open", about: "held-op", name: who, options: [{ id: "PER-2", name: "Robin Sample" }] },
  };
  return item;
}

test("rows that arrive while the list shows nothing appear at once, never as N new over an empty list", async () => {
  let rows: S["ChangeItem"][] = [];
  fakeApi({ "GET changes": () => rows, "GET people": () => [] });
  const { client } = renderApp(<WhatChanged />);
  expect(await screen.findByText(/Nothing needs/i)).toBeInTheDocument();
  rows = [change("REQ-1"), change("REQ-2"), change("REQ-3")];
  await client.invalidateQueries();
  expect(await screen.findAllByText("Proof copies ship Nov 5")).toHaveLength(3);
  expect(screen.queryByRole("button", { name: /Show \d+ new items?/ })).toBeNull();
});

test("rows that arrive while the list shows others still wait behind N new", async () => {
  let rows = [change("REQ-1")];
  fakeApi({ "GET changes": () => rows });
  const { client } = renderApp(<WhatChanged />);
  expect(await screen.findAllByText("Proof copies ship Nov 5")).toHaveLength(1);
  rows = [change("REQ-1"), change("REQ-2")];
  await client.invalidateQueries();
  expect(await screen.findByRole("button", { name: /Show \d+ new items?/ })).toBeInTheDocument();
  expect(screen.getAllByText("Proof copies ship Nov 5")).toHaveLength(1);
});

test("every row that holds a question for the person starts open, whatever its state", async () => {
  fakeApi({
    "GET changes": () => [asking("REQ-1", "Robin"), asking("REQ-2", "Sam")],
    "GET people": () => [{ id: "PER-2", name: "Robin Sample", role: "Editor" }],
  });
  renderApp(<WhatChanged />);
  expect(await screen.findByRole("combobox", { name: "Who is “Robin”?" })).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "Who is “Sam”?" })).toBeInTheDocument();
});

// The phone's review mode (design 7.1): the items waiting for a look, one at a time, with Looks good, Send back and Next.
describe("review mode on a phone", () => {
  const routes = (items: S["ChangeItem"][], extra: Record<string, (b: unknown) => unknown> = {}) => ({
    "GET changes": () => items,
    "GET stages/requests": () => [],
    "GET stages/records": () => [],
    ...extra,
  });
  beforeEach(() => document.documentElement.setAttribute("data-narrow", ""));
  afterEach(() => document.documentElement.removeAttribute("data-narrow"));

  const first = () => change("A", { source_title: "First thing", changeset: { ...change("A").changeset!, summary: "Summary of the first thing." } });
  const second = () => change("B", { source_title: "Second thing", changeset: { ...change("B").changeset!, summary: "Summary of the second thing." } });

  test("is offered only on a phone and only for items waiting for a look", async () => {
    const user = userEvent.setup();
    fakeApi(routes([first(), change("C", { state: "failed", source_title: "A failure", changeset: null })]));
    renderApp(<WhatChanged />);
    expect(await screen.findByRole("button", { name: "Review one at a time" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Review one at a time" }));
    expect(await screen.findByRole("heading", { name: "1 of 1 to look at" })).toBeInTheDocument();
    expect(screen.queryByText("A failure")).toBeNull();
    document.documentElement.removeAttribute("data-narrow");
  });

  test("shows one item open with its summary, and Next goes to the following one and round again", async () => {
    const user = userEvent.setup();
    fakeApi(routes([first(), second()]));
    renderApp(<WhatChanged />);
    await user.click(await screen.findByRole("button", { name: "Review one at a time" }));
    expect(await screen.findByText("Summary of the first thing.")).toBeInTheDocument();
    expect(screen.queryByText("Summary of the second thing.")).toBeNull();
    expect(screen.getByRole("heading", { name: "1 of 2 to look at" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Summary of the second thing.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "2 of 2 to look at" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Summary of the first thing.")).toBeInTheDocument();
  });

  test("Looks good approves the item on screen with Undo, and the next one takes its place", async () => {
    const user = userEvent.setup();
    let items = [first(), second()];
    const calls = fakeApi(
      routes(items, {
        "GET changes": () => items,
        "POST changesets/CS-A/looks-good": () => {
          items = [second()];
          return { ok: true };
        },
      }),
    );
    renderApp(<WhatChanged />);
    await user.click(await screen.findByRole("button", { name: "Review one at a time" }));
    await screen.findByText("Summary of the first thing.");
    await user.click(within(screen.getByRole("group", { name: "What to do with this one" })).getByRole("button", { name: "Looks good" }));
    await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-A/looks-good")).toBe(true));
    expect(await screen.findByText("Summary of the second thing.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "1 of 1 to look at" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  test("Send back opens the note for the item on screen, with no menu needed", async () => {
    const user = userEvent.setup();
    fakeApi(routes([first()]));
    renderApp(<WhatChanged />);
    await user.click(await screen.findByRole("button", { name: "Review one at a time" }));
    await screen.findByText("Summary of the first thing.");
    await user.click(within(screen.getByRole("group", { name: "What to do with this one" })).getByRole("button", { name: "Send back" }));
    expect(await screen.findByLabelText(/^What should .* do differently\?/)).toBeInTheDocument();
  });

  test("when the last one is approved it says nothing is left, and one button goes back to the list", async () => {
    const user = userEvent.setup();
    let items = [first()];
    fakeApi(
      routes(items, {
        "GET changes": () => items,
        "POST changesets/CS-A/looks-good": () => {
          items = [];
          return { ok: true };
        },
      }),
    );
    renderApp(<WhatChanged />);
    await user.click(await screen.findByRole("button", { name: "Review one at a time" }));
    await screen.findByText("Summary of the first thing.");
    await user.click(within(screen.getByRole("group", { name: "What to do with this one" })).getByRole("button", { name: "Looks good" }));
    expect(await screen.findByRole("heading", { name: "Nothing left to look at." })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to the list" }));
    expect(await screen.findByRole("heading", { name: "What changed" })).toBeInTheDocument();
  });

  test("on a wide screen there is no review mode", async () => {
    document.documentElement.removeAttribute("data-narrow");
    fakeApi(routes([first()]));
    renderApp(<WhatChanged />);
    await screen.findByText("First thing");
    expect(screen.queryByRole("button", { name: "Review one at a time" })).toBeNull();
  });
});
