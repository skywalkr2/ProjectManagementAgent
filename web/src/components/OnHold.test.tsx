import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { reveal, useReveal } from "../lib/reveal";
import { fakeApi, renderApp } from "../test-utils";
import { HoldNote, HoldPill, useHold } from "./OnHold";

const person = (id: string, name: string): S["PersonView"] => ({ id, name, role: null, org: null, aliases: [], status: "active", is_pm: false, track_only: false, open_items: 0 });
const people = [person("P-1", "Quinn Sample"), person("P-2", "Robin Sample"), person("P-3", "Sam Twin"), person("P-4", "Sam Twin")];

function Listener(props: { on: (id: string) => void }) {
  useReveal("person", (id) => {
    props.on(id);
    return true;
  });
  return null;
}

test("a person named in what a to-do waits for is a link to their group in Follow-ups", async () => {
  fakeApi({ "GET people": () => people });
  const user = userEvent.setup();
  const seen = vi.fn();
  renderApp(
    <>
      <Listener on={seen} />
      <HoldPill what="Quinn Sample's answer" due={null} />
    </>,
  );
  const link = await screen.findByRole("link", { name: "Quinn Sample" });
  expect(link).toHaveAttribute("href", expect.stringMatching(/#work\/followups$/));
  expect(screen.getByText(/On hold:/)).toHaveTextContent("On hold: Quinn Sample's answer");
  await user.click(link);
  expect(seen).toHaveBeenCalledWith("P-1");
});

test("words that name nobody, only a first name, or two people alike stay plain text", async () => {
  fakeApi({ "GET people": () => people });
  renderApp(
    <>
      <HoldPill what="the legal review" />
      <HoldPill what="Quinn's answer" />
      <HoldPill what="Sam Twin to reply" />
    </>,
  );
  await waitFor(() => expect(screen.getAllByText(/On hold:/)).toHaveLength(3));
  await new Promise((r) => setTimeout(r, 20));
  expect(screen.queryByRole("link")).toBeNull();
  expect(reveal("person", "P-1")).toBe(false);
});

// ---- blocked: a hold that names its blocker ------------------------------------------------------------------------

type Blocker = NonNullable<S["TodoView"]["blocker"]>;
const blocker = (over: Partial<Blocker>): Blocker => ({ kind: "person", id: "P-1", name: "Quinn Sample", state: "waiting", ...over });

test("a to-do blocked on a person reads Blocked, waiting on them, with their name a link to their group in Follow-ups", async () => {
  const user = userEvent.setup();
  const seen = vi.fn();
  fakeApi({ "GET people": () => people });
  renderApp(
    <>
      <Listener on={seen} />
      <HoldNote on_hold="Quinn Sample" blocker={blocker({})} due="2026-10-01" />
    </>,
  );
  const pill = await screen.findByText(/Blocked, waiting on/);
  expect(pill).toHaveTextContent("Blocked, waiting on Quinn Sample");
  expect(pill).toHaveAttribute("title", expect.stringMatching(/^Was due .*1/));
  await user.click(screen.getByRole("link", { name: "Quinn Sample" }));
  expect(seen).toHaveBeenCalledWith("P-1");
});

test("a to-do blocked on an action names that action's words and links to its page", async () => {
  fakeApi({ "GET people": () => people });
  renderApp(<HoldNote on_hold="Send the index" blocker={blocker({ kind: "action", id: "ACT-7", name: "Send the index" })} />);
  const link = await screen.findByRole("link", { name: "Send the index" });
  expect(link).toHaveAttribute("href", expect.stringMatching(/#records\/action\/ACT-7$/));
  expect(link.closest(".pill")).toHaveTextContent("Blocked, waiting on Send the index");
});

test("a to-do tied to a question says Waits on the question with who was asked and when it went out, linking to it", async () => {
  fakeApi({ "GET people": () => people });
  const tied = blocker({ kind: "question", id: "Q-4", name: "Can proof copies ship by Nov 3?", who: "Morgan Sample", sent: "2026-10-12" });
  const { unmount } = renderApp(<HoldNote on_hold="Can proof copies ship by Nov 3?" blocker={tied} />);
  const link = await screen.findByRole("link", { name: "Can proof copies ship by Nov 3?" });
  expect(link).toHaveAttribute("href", expect.stringMatching(/#records\/question\/Q-4$/));
  expect(link.closest(".pill")).toHaveTextContent(/^Waits on: Can proof copies ship by Nov 3\? \(Morgan Sample, sent .*12\)$/);
  unmount();
  renderApp(<HoldNote on_hold="x" blocker={{ ...tied, sent: null }} />);
  expect((await screen.findByRole("link", { name: "Can proof copies ship by Nov 3?" })).closest(".pill")).toHaveTextContent(
    "Waits on: Can proof copies ship by Nov 3? (Morgan Sample, not sent yet)",
  );
});

test("once the question is answered the note reads Unblocked with who answered and when, and a finished to-do says so", async () => {
  fakeApi({ "GET people": () => people });
  const answered = blocker({ kind: "question", id: "Q-4", name: "Can proof copies ship?", who: "Morgan Sample", state: "answered", answered: "2026-10-16" });
  const { unmount } = renderApp(<HoldNote on_hold={null} blocker={answered} />);
  expect(await screen.findByText(/^Unblocked: Morgan Sample answered .*16$/)).toBeInTheDocument();
  expect(screen.queryByRole("link")).toBeNull();
  unmount();
  renderApp(<HoldNote on_hold={null} blocker={blocker({ kind: "action", id: "ACT-7", name: "Send the index", state: "done" })} />);
  expect(await screen.findByText("Unblocked: Send the index is done")).toBeInTheDocument();
});

test("a hold with only words still reads On hold, and no hold shows nothing", async () => {
  fakeApi({ "GET people": () => people });
  const { container, unmount } = renderApp(<HoldNote on_hold="the legal review" blocker={null} />);
  expect(await screen.findByText("On hold: the legal review")).toBeInTheDocument();
  unmount();
  const empty = renderApp(<HoldNote on_hold={null} blocker={null} />);
  expect(empty.container).toHaveTextContent("");
  expect(container).toBeTruthy();
});

// ---- the picker on Put on hold -----------------------------------------------------------------------------------------

function Harness(props: { id: string }) {
  const hold = useHold({ id: props.id });
  return (
    <>
      <button type="button" onClick={hold.entry.run}>
        {hold.entry.label}
      </button>
      {hold.form}
    </>
  );
}

const section = (over: Partial<S["FollowupSection"]>): S["FollowupSection"] => ({ person: "P-2", name: "Robin Sample", is_pm: false, questions: [], actions: [], message: "", to_send: 0, ...over });
const action = (id: string, text: string): S["FollowupAction"] => ({ id, text, due: null, project_name: "", told: null, told_days: null, followed_up: null, chase_due: false, chases: 0 });
const question = (id: string, title: string): S["FollowupQuestion"] => ({ id, title, text: "", links: [], kind: "question", status: "sent", sent: "2026-10-12", waiting_days: 3, chase_due: false, chases: 0, about: null, options: [] });

const pickerRoutes = {
  "GET people": () => people,
  "GET followups": () => [
    section({
      actions: [action("ACT-1", "Send the index"), action("ACT-2", "Approve the cover")],
      questions: [question("Q-4", "Can proof copies ship by Nov 3?")],
    }),
  ],
};

test("Put on hold offers people, the other to-dos and the open questions to pick from, never to type, and not the to-do itself", async () => {
  const user = userEvent.setup();
  fakeApi(pickerRoutes);
  renderApp(<Harness id="ACT-1" />);
  await user.click(screen.getByRole("button", { name: "Put on hold" }));
  const field = screen.getByRole("textbox", { name: "What is it waiting for?" });
  expect(field).toHaveFocus();
  const pick = screen.getByRole("combobox", { name: "Or pick what it waits on" });
  await waitFor(() => expect(within(pick).getAllByRole("option").length).toBeGreaterThan(5));
  expect(within(pick).getByRole("group", { name: "People" })).toHaveTextContent("Quinn Sample");
  expect(within(pick).getByRole("group", { name: "To-dos" })).toHaveTextContent("Approve the cover");
  expect(within(pick).getByRole("group", { name: "To-dos" })).not.toHaveTextContent("Send the index");
  expect(within(pick).getByRole("group", { name: "Questions" })).toHaveTextContent("Can proof copies ship by Nov 3?");
});

test("picking a person puts the to-do on hold for them with no words typed, and Undo puts the old hold back", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({
    ...pickerRoutes,
    "POST actions/ACT-1/hold": () => ({ ok: "ACT-1", previous: null }),
    "POST actions/ACT-1/hold/restore": () => ({ ok: "ACT-1" }),
  });
  renderApp(<Harness id="ACT-1" />);
  await user.click(screen.getByRole("button", { name: "Put on hold" }));
  const submit = screen.getAllByRole("button", { name: "Put on hold" }).find((b) => (b as HTMLButtonElement).type === "submit")!;
  expect(submit).toBeDisabled();
  const pick = screen.getByRole("combobox", { name: "Or pick what it waits on" });
  await waitFor(() => expect(within(pick).getAllByRole("option").length).toBeGreaterThan(5));
  await user.selectOptions(pick, "P-1");
  expect(submit).toBeEnabled();
  await user.click(submit);
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/hold")?.body).toEqual({ waiting_for: "", on: "P-1" }));
  expect(await screen.findByText("Put on hold, waiting for Quinn Sample.")).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/hold/restore")?.body).toEqual({ hold: null }));
});

test("picking a to-do or a question sends its id with whatever words were typed", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ ...pickerRoutes, "POST actions/ACT-1/hold": () => ({ ok: "ACT-1", previous: null }) });
  renderApp(<Harness id="ACT-1" />);
  await user.click(screen.getByRole("button", { name: "Put on hold" }));
  const pick = screen.getByRole("combobox", { name: "Or pick what it waits on" });
  await waitFor(() => expect(within(pick).getAllByRole("option").length).toBeGreaterThan(5));
  await user.selectOptions(pick, "Q-4");
  await user.type(screen.getByRole("textbox", { name: "What is it waiting for?" }), "the printer");
  await user.click(screen.getAllByRole("button", { name: "Put on hold" }).find((b) => (b as HTMLButtonElement).type === "submit")!);
  await waitFor(() => expect(calls.find((c) => c.route === "POST actions/ACT-1/hold")?.body).toEqual({ waiting_for: "the printer", on: "Q-4" }));
});
