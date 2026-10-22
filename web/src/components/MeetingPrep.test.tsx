import "@testing-library/jest-dom/vitest";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { forgetLine } from "../lib/today";
import { RestartProvider } from "../lib/restart";
import { fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { MeetingPrep } from "./MeetingPrep";
import { PersonMemory } from "./PersonMemory";
import { Today } from "./Today";

// Prep before a calendar entry, capture after it, and what to remember about a person (design 6.32, 7.14): the three lines on
// Today, the prep on the entry's page and the memory on the person's page. Everything is worked out by rules on the server;
// these tests check what the screens show of it, in plain words, with the cursor where the person types.

type Line = S["QueueLineView"];
type Item = S["OpenItemView"];
type Prep = S["MeetingPrepView"];
type Memory = S["PersonMemoryView"];

const ANA = "Ana Example";
const line = (kind: Line["kind"], over: Partial<Line> = {}): Line => ({ key: `${kind}:1`, group: "review", kind, count: 1, untrusted: false, unpriced: 0, actions: [], questions: [], outcome: {}, ...over });
const item = (over: Partial<Item> & Pick<Item, "kind" | "id" | "text">): Item => ({ record: "action", quiet: 0, ...over });

function today(lines: Line[], extra: Routes = {}) {
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: () => undefined, removeEventListener: () => undefined }));
  const calls = fakeApi({
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
    ...extra,
  });
  const onOpenRecord = vi.fn();
  renderApp(
    <RestartProvider hellos={1}>
      <Today workspace="Workspace" onView={vi.fn()} onAddSource={vi.fn()} onOpenGuide={vi.fn()} onOpenRecord={onOpenRecord} shortcuts={{ next: "j", previous: "k" }} />
    </RestartProvider>,
  );
  return { calls, onOpenRecord };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  forgetLine();
});

const rowOf = async (title: string) => (await screen.findByRole("group", { name: title })) as HTMLElement;

// ---- Today -----------------------------------------------------------------------------------------------------------

test("a meeting about to start is a line that says who is coming and how much is open, and its button opens the entry", async () => {
  const user = userEvent.setup();
  const { onOpenRecord } = today([line("meeting_prep", { key: "meeting_prep:EVT-1", text: "Design review", event: "EVT-1", names: [ANA], count: 2, open_items: 3, at: "2026-10-21T10:00:00-04:00" })]);
  const row = await rowOf("Prepare for Design review");
  expect(within(row).getByText("Prep")).toBeInTheDocument();
  expect(row).toHaveTextContent(`with ${ANA} and 1 other`);
  expect(row).toHaveTextContent("3 things open");
  await user.click(within(row).getByRole("button", { name: "Open prep" }));
  expect(onOpenRecord).toHaveBeenCalledWith("event", "EVT-1");
});

test("a meeting with nothing open and nobody on file says only who is coming", async () => {
  today([line("meeting_prep", { key: "meeting_prep:EVT-2", text: "Sync", event: "EVT-2", names: [], count: 1, open_items: 0, at: "2026-10-21T10:00:00-04:00" })]);
  const row = await rowOf("Prepare for Sync");
  expect(row).toHaveTextContent("with 1 other");
  expect(row).not.toHaveTextContent("open");
});

test("capture asks what happened with the cursor in the box, and Enter saves the words on the entry", async () => {
  const user = userEvent.setup();
  const { calls } = today([line("meeting_capture", { key: "meeting_capture:EVT-1", text: "Design review", event: "EVT-1", names: [ANA], at: "2026-10-20T11:00:00-04:00" })], {
    "POST meetings/EVT-1/capture": () => ({ request: "REQ-1", captured_at: "2026-10-20T12:00:00Z" }),
  });
  const row = await rowOf("Capture what happened at Design review");
  await user.click(within(row).getByRole("button", { name: "Capture" }));
  const box = await within(row).findByRole("textbox", { name: "What happened at Design review?" });
  await waitFor(() => expect(box).toHaveFocus());
  await user.type(box, "Ana will send the contract by Friday.{Enter}");
  await waitFor(() => expect(calls.find((c) => c.route === "POST meetings/EVT-1/capture")?.body).toEqual({ text: "Ana will send the contract by Friday." }));
  expect(await screen.findByText(/Saved what happened at Design review/)).toBeInTheDocument();
});

test("Nothing to note ends the question with no words, and Escape closes the box without sending", async () => {
  const user = userEvent.setup();
  const { calls } = today([line("meeting_capture", { key: "meeting_capture:EVT-1", text: "Design review", event: "EVT-1", at: "2026-10-20T11:00:00-04:00" })], {
    "POST meetings/EVT-1/capture": () => ({ request: null, captured_at: "2026-10-20T12:00:00Z" }),
  });
  const row = await rowOf("Capture what happened at Design review");
  await user.click(within(row).getByRole("button", { name: "Capture" }));
  await user.type(await within(row).findByRole("textbox"), "x{Escape}");
  expect(within(row).queryByRole("textbox")).toBeNull();
  expect(calls.some((c) => c.route === "POST meetings/EVT-1/capture")).toBe(false);
  await user.click(within(row).getByRole("button", { name: "Capture" }));
  await user.click(await within(row).findByRole("button", { name: "Nothing to note" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST meetings/EVT-1/capture")?.body).toEqual({ text: "" }));
  expect(await screen.findByText(/Marked Design review as nothing to note/)).toBeInTheDocument();
});

test("a promise gone quiet is one line that says who to follow up with and which way the promise went", async () => {
  const user = userEvent.setup();
  const { onOpenRecord } = today([line("quiet_promise", { key: "quiet_promise:ACT-1", group: "send", text: "Send the cover", person: "PER-2", person_name: ANA, actions: ["ACT-1"], waiting_days: 9, state: "to", due: "2026-10-30" })]);
  const row = await rowOf(`Follow up with ${ANA}: Send the cover has gone quiet`);
  expect(row).toHaveTextContent("You promised them");
  expect(row).toHaveTextContent("No news for 9 days");
  expect(row).toHaveTextContent("due");
  await user.click(within(row).getByRole("button", { name: "Open" }));
  expect(onOpenRecord).toHaveBeenCalledWith("person", "PER-2");
});

test("a promise the other person made says so", async () => {
  today([line("quiet_promise", { key: "quiet_promise:ACT-2", group: "send", text: "Return the contract", person: "PER-2", person_name: ANA, actions: ["ACT-2"], waiting_days: 1, state: "from" })]);
  const row = await rowOf(`Follow up with ${ANA}: Return the contract has gone quiet`);
  expect(row).toHaveTextContent("They promised you");
  expect(row).toHaveTextContent("No news for 1 day");
});

// ---- the entry's page ------------------------------------------------------------------------------------------------

const prep = (over: Partial<Prep> = {}): Prep => ({
  event: "EVT-1",
  title: "Design review",
  start: "2026-10-21T10:00:00-04:00",
  end: "2026-10-21T11:00:00-04:00",
  untrusted: false,
  over: false,
  coming: [{ person: "PER-2", name: ANA }],
  people: [
    {
      person: "PER-2",
      name: ANA,
      promised_to: [item({ kind: "promised_to", id: "ACT-1", text: "Send the cover", due: "2026-10-30", quote: "I'll send the cover", quiet: 4 })],
      promised_by: [item({ kind: "promised_by", id: "ACT-2", text: "Return the contract" })],
      asked_by: [item({ kind: "asked_by", id: "ACT-3", text: "Reply about the date" })],
      asked_of: [item({ kind: "asked_of", record: "question", id: "Q-1", text: "Which trim size?" })],
      more: 2,
      last_in_touch: { kind: "from", on: "2026-10-18", subject: "Re: the proofs", untrusted: true },
      left_open: { event: "EVT-0", title: "Kickoff", on: "2026-10-12", untrusted: false, items: [item({ kind: "left_open", id: "ACT-4", text: "Book the room" })] },
    },
  ],
  note: { state: "none" },
  ...over,
});

function entryPage(shown: Prep, extra: Routes = {}) {
  const calls = fakeApi({ "GET meetings/EVT-1/prep": () => shown, ...extra });
  renderApp(<MeetingPrep entry="EVT-1" title="Design review" />);
  return calls;
}

test("the prep shows, for each person coming, what is open both ways with the words it came from, when you were last in touch and what the last meeting left open", async () => {
  entryPage(prep());
  const region = await screen.findByRole("region", { name: ANA });
  expect(within(region).getByRole("link", { name: ANA })).toHaveAttribute("href", expect.stringContaining("PER-2"));
  expect(within(region).getByText("You promised Ana Example")).toBeInTheDocument();
  expect(within(region).getByText("Ana Example promised you")).toBeInTheDocument();
  expect(within(region).getByText("Ana Example asked you")).toBeInTheDocument();
  expect(within(region).getByText("You asked Ana Example")).toBeInTheDocument();
  expect(within(region).getByText("Send the cover")).toBeInTheDocument();
  expect(region).toHaveTextContent("“I'll send the cover”");
  expect(region).toHaveTextContent("4 days quiet");
  expect(region).toHaveTextContent("Last in touch: mail from them on");
  expect(region).toHaveTextContent("Re: the proofs");
  expect(within(region).getByText("Outside")).toBeInTheDocument();
  expect(region).toHaveTextContent("2 more open things aren't listed.");
  expect(region).toHaveTextContent("Still open from Kickoff");
  expect(within(region).getByText("Book the room")).toBeInTheDocument();
});

test("a person with nothing open and no contact says so, and someone not on file is named without a link", async () => {
  entryPage(
    prep({
      coming: [
        { person: "PER-2", name: ANA },
        { person: null, name: "Sam Stranger", address: "sam@example.com" },
      ],
      people: [{ person: "PER-2", name: ANA, promised_to: [], promised_by: [], asked_by: [], asked_of: [], more: 0 }],
    }),
  );
  const region = await screen.findByRole("region", { name: ANA });
  expect(region).toHaveTextContent("Nothing is open with Ana Example.");
  expect(region).toHaveTextContent("No contact on file yet.");
  expect(screen.getByText("1 other isn't on file: Sam Stranger")).toBeInTheDocument();
});

test("an entry nobody else is on says so and offers no prep note", async () => {
  entryPage(prep({ coming: [], people: [] }));
  expect(await screen.findByText("Nobody else is on this calendar entry.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Draft a prep note" })).toBeNull();
});

test("a prep note is asked for in one press, and the page says where it stands afterwards", async () => {
  const user = userEvent.setup();
  const calls = entryPage(prep(), { "POST meetings/EVT-1/prep-note": () => ({ request: "REQ-1" }) });
  await user.click(await screen.findByRole("button", { name: "Draft a prep note" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST meetings/EVT-1/prep-note")?.body).toEqual({ note: null }));
  cleanup();
  entryPage(prep({ note: { state: "needs_go", request: "REQ-1" } }));
  expect(await screen.findByText("A prep note is waiting for your go on Today.")).toBeInTheDocument();
  cleanup();
  entryPage(prep({ note: { state: "draft", request: "REQ-1" } }));
  expect(await screen.findByText("A prep note is waiting below for you to read.")).toBeInTheDocument();
});

test("once the entry has ended the page offers to capture what happened, and says when it was written down", async () => {
  const user = userEvent.setup();
  const calls = entryPage(prep({ over: true }), { "POST meetings/EVT-1/capture": () => ({ request: "REQ-1", captured_at: "2026-10-21T12:00:00Z" }) });
  await user.click(await screen.findByRole("button", { name: "Capture what happened" }));
  const box = await screen.findByRole("textbox", { name: "What happened at Design review?" });
  await waitFor(() => expect(box).toHaveFocus());
  await user.type(box, "Agreed the trim size.");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST meetings/EVT-1/capture")?.body).toEqual({ text: "Agreed the trim size." }));
  cleanup();
  entryPage(prep({ over: true, captured_at: "2026-10-21T12:00:00Z" }));
  expect(await screen.findByText(/What happened was written down on/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Capture what happened" })).toBeNull();
});

test("an entry still ahead has no capture button", async () => {
  entryPage(prep());
  await screen.findByRole("region", { name: ANA });
  expect(screen.queryByRole("button", { name: "Capture what happened" })).toBeNull();
});

// ---- a person's page -------------------------------------------------------------------------------------------------

const memory = (over: Partial<Memory> = {}): Memory => ({
  person: "PER-2",
  name: ANA,
  last_in_touch: { kind: "to", on: "2026-10-19", untrusted: false },
  asked_of: [],
  asked_by: [],
  promised_to: [item({ kind: "promised_to", id: "ACT-1", text: "Send the cover", quote: "I'll send the cover" })],
  promised_by: [],
  reach: { kept: { email: "ana@example.com", phone: "555-0100" }, replies_on: "email", replies_record: "SRC-1" },
  dates: [
    { fact: "FACT-1", text: "Ana Example's birthday is March 3", on: "2027-03-03", yearly: true, quote: "birthday is March 3" },
    { fact: "FACT-2", text: "Ana Example's contract ends 2027-01-15", on: "2027-01-15", yearly: false },
  ],
  matters: [{ fact: "FACT-3", text: "Ana Example prefers short notes", as_of: "2026-10-01", quote: "prefers short notes" }],
  ...over,
});

test("a person's page shows each part with the words it rests on: last in touch, what is open, how to reach them, their dates and what matters", async () => {
  fakeApi({ "GET people/PER-2/memory": () => memory() });
  renderApp(<PersonMemory person="PER-2" />);
  const region = await screen.findByRole("region", { name: "What to remember" });
  expect(region).toHaveTextContent("Last in touch: a message to them on");
  expect(within(region).getByText("You promised Ana Example")).toBeInTheDocument();
  expect(region).toHaveTextContent("“I'll send the cover”");
  expect(region).toHaveTextContent("ana@example.com · email · where they last wrote from");
  expect(region).toHaveTextContent("555-0100 · phone");
  expect(region).not.toHaveTextContent("555-0100 · phone · where they last wrote from");
  expect(region).toHaveTextContent("Ana Example's birthday is March 3 · every year, next on");
  expect(region).toHaveTextContent("Ana Example's contract ends 2027-01-15 · on");
  expect(region).toHaveTextContent("Ana Example prefers short notes · as of");
  expect(within(region).getByText("How to reach them")).toBeInTheDocument();
  expect(within(region).getByText("What matters to them")).toBeInTheDocument();
});

test("a part with nothing in it is left out, and a person with nothing on file says so", async () => {
  fakeApi({ "GET people/PER-2/memory": () => memory({ last_in_touch: null, promised_to: [], reach: { kept: {} }, dates: [], matters: [] }) });
  renderApp(<PersonMemory person="PER-2" />);
  expect(await screen.findByText("Nothing is on file about Ana Example yet.")).toBeInTheDocument();
  expect(screen.queryByText("How to reach them")).toBeNull();
  expect(screen.queryByText("Dates")).toBeNull();
  expect(screen.queryByText("What matters to them")).toBeNull();
});
