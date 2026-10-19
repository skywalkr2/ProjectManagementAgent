import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { Ask } from "./Ask";

type AskItem = S["AskView"];

const ask = (id: string, extra: Partial<AskItem> = {}): AskItem => ({
  id,
  question: `Question ${id}`,
  state: "queued",
  waiting: "With the assistant, starting now",
  created_at: "2026-03-04T10:30:00+00:00",
  changeset: null,
  answer: null,
  proposals: [],
  reports: [],
  ...extra,
});

const setting = (key: string, value: unknown, description = key): S["SettingItem"] => ({
  key,
  file: "demo",
  group: "demo",
  description,
  type: "text",
  options: [],
  value,
  default: value,
  source: "default",
  locked: false,
  basic: true,
  editable: true,
});

const saved = (key: string, before: unknown, after: unknown): S["SettingsSaved"] => ({
  changes: [{ key, before, after, was_default: true, is_default: false }],
  fingerprint: "fp-2",
  needs_restart: false,
});

function open(asks: AskItem[], extra: Record<string, (b: unknown) => unknown> = {}, initial?: string, feedbackTo?: string | null) {
  const calls = fakeApi({
    "GET asks": () => asks,
    "GET settings": () => ({ fingerprint: "fp-1", items: [setting("demo.thing", 5, "How many things")] }),
    ...extra,
  });
  const onClose = vi.fn();
  renderApp(<Ask onClose={onClose} initial={initial} feedbackTo={feedbackTo} />);
  return { calls, onClose };
}

const item = async (question: string) => (await screen.findByRole("listitem", { name: question })) as HTMLElement;
const sent = (calls: Array<{ route: string; body: unknown }>, route: string) => calls.find((c) => c.route === route)?.body;

test("the dialog is named for the assistant and the question field has the focus", async () => {
  open([]);
  expect(screen.getByRole("dialog", { name: "Ask Helper" })).toBeInTheDocument();
  expect(screen.getByLabelText("Your question")).toHaveFocus();
  expect(await screen.findByText("No questions yet.")).toBeInTheDocument();
});

test("a question can start filled in", async () => {
  open([], {}, "How do I add a source?");
  expect(screen.getByLabelText("Your question")).toHaveValue("How do I add a source?");
});

test("asking posts the question, clears the field and lists it", async () => {
  const asks: AskItem[] = [];
  const { calls } = open(asks, {
    "POST ask": (body) => {
      asks.unshift(ask("r1", { question: (body as { question: string }).question }));
      return { id: "r1" };
    },
  });
  const user = userEvent.setup();
  const field = screen.getByLabelText("Your question");
  await user.type(field, "What is due this week?");
  await user.click(screen.getByRole("button", { name: "Ask" }));
  await waitFor(() => expect(sent(calls, "POST ask")).toEqual({ question: "What is due this week?" }));
  expect(await item("What is due this week?")).toHaveTextContent("Waiting");
  expect(field).toHaveValue("");
  expect(field).toHaveFocus();
});

test("Enter asks and Shift+Enter starts a new line", async () => {
  const { calls } = open([], { "POST ask": () => ({ id: "r1" }) });
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Your question"), "First{Shift>}{Enter}{/Shift}Second{Enter}");
  await waitFor(() => expect(sent(calls, "POST ask")).toEqual({ question: "First\nSecond" }));
});

test("nothing is asked with an empty field", async () => {
  open([]);
  expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
});

test("each state is said in words, with why it is waiting", async () => {
  open([
    ask("q", { state: "queued", waiting: "Next batch at 3:00" }),
    ask("w", { state: "running", waiting: "Working now" }),
    ask("n", { state: "needs_you", waiting: "Waiting for your answer" }),
    ask("f", { state: "failed", waiting: "Paused until the limit resets" }),
    ask("a", { state: "done", waiting: null, answer: { text: "It is Tuesday.", cites: [] } }),
    ask("r", { state: "review", waiting: "In your list to look at", answer: { text: "Done.", cites: [] } }),
  ]);
  expect(await item("Question q")).toHaveTextContent(/Waiting\s*Next batch at 3:00/);
  expect(await item("Question w")).toHaveTextContent("Working on it");
  expect(await item("Question n")).toHaveTextContent(/Needs you\s*Waiting for your answer/);
  expect(await item("Question f")).toHaveTextContent(/Stopped\s*Paused until the limit resets/);
  const answered = await item("Question a");
  expect(answered).toHaveTextContent("Answered");
  expect(answered).toHaveTextContent("It is Tuesday.");
  const review = await item("Question r");
  expect(review).toHaveTextContent("Answered");
  expect(review).not.toHaveTextContent("In your list to look at");
});

test("an answer lists the words it is based on, in quote marks, as text", async () => {
  open([
    ask("a", {
      state: "done",
      answer: {
        text: "Backups run every day.",
        cites: [
          { quote: "Backups run on a schedule", source: "help" },
          { quote: "<b>bold</b> words", source: null },
        ],
      },
    }),
  ]);
  const row = await item("Question a");
  expect(within(row).getByText("Based on")).toBeInTheDocument();
  expect(within(row).getByText("“Backups run on a schedule”")).toBeInTheDocument();
  expect(within(row).getByText("“<b>bold</b> words”")).toBeInTheDocument();
  expect(row.querySelector("b")).toBeNull();
  // The place a quote came from is an internal name and is not shown.
  expect(row).not.toHaveTextContent("help");
});

test("a suggested setting shows its label, value and why, and Apply sends the current fingerprint and the version read", async () => {
  const proposal: S["SettingProposalView"] = { id: "sp1", version: 3, key: "demo.thing", value: 8, why: "You asked for more.", status: "open" };
  const { calls, onClose } = open([ask("a", { state: "done", answer: { text: "Try this.", cites: [] }, proposals: [proposal] })], {
    "POST setting-proposals/sp1/apply": () => saved("demo.thing", 5, 8),
  });
  const user = userEvent.setup();
  const row = await item("Question a");
  await waitFor(() => expect(row).toHaveTextContent("How many things: 8"));
  expect(row).toHaveTextContent("You asked for more.");
  await user.click(await within(row).findByRole("button", { name: "Make this change: How many things" }));
  await waitFor(() =>
    expect(sent(calls, "POST setting-proposals/sp1/apply")).toEqual({ fingerprint: "fp-1", read_version: 3 }),
  );
  // The read-back with Undo, as after any saved setting.
  expect(await screen.findByText("Saved. How many things: 8")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
  // The dialog closes, so the Undo can be reached from the keyboard.
  expect(onClose).toHaveBeenCalled();
});

test("a setting with a name on the wording sheet uses it", async () => {
  const proposal: S["SettingProposalView"] = {
    id: "sp1",
    version: 1,
    key: "storage.backups.every_hours",
    value: 6,
    why: "",
    status: "open",
  };
  open([ask("a", { state: "done", answer: { text: "Ok.", cites: [] }, proposals: [proposal] })], {
    "GET settings": () => ({ fingerprint: "fp-1", items: [] }),
  });
  const row = await item("Question a");
  await waitFor(() => expect(row).toHaveTextContent("Hours between backups: 6"));
});

test("a suggestion that changed since it was read is refused in words", async () => {
  const proposal: S["SettingProposalView"] = { id: "sp1", version: 3, key: "demo.thing", value: 8, why: "", status: "open" };
  const { Refuse } = await import("../test-utils");
  open([ask("a", { state: "done", answer: { text: "Try.", cites: [] }, proposals: [proposal] })], {
    "POST setting-proposals/sp1/apply": () => new Refuse(409, "That suggestion changed since you saw it."),
  });
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: /^Make this change/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent("That suggestion changed since you saw it.");
});

test("Not now sets the suggestion aside with the version read", async () => {
  const proposal: S["SettingProposalView"] = { id: "sp1", version: 3, key: "demo.thing", value: 8, why: "", status: "open" };
  const { calls } = open([ask("a", { state: "done", answer: { text: "Try.", cites: [] }, proposals: [proposal] })], {
    "POST setting-proposals/sp1/dismiss": () => ({ id: "sp1" }),
  });
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: /^Not now/ }));
  await waitFor(() => expect(sent(calls, "POST setting-proposals/sp1/dismiss")).toEqual({ read_version: 3 }));
  expect(await screen.findByText("Left as it is.")).toBeInTheDocument();
});

test("a suggestion already dealt with says so and offers nothing", async () => {
  const proposal: S["SettingProposalView"] = { id: "sp1", version: 4, key: "demo.thing", value: 8, why: "", status: "applied" };
  open([ask("a", { state: "done", answer: { text: "Done.", cites: [] }, proposals: [proposal] })]);
  const row = await item("Question a");
  expect(row).toHaveTextContent("Changed");
  expect(within(row).queryByRole("button", { name: /^Make this change/ })).toBeNull();
});

test("Copy puts the draft report on the clipboard; Mark sent then records it", async () => {
  const report: S["ReportView"] = { id: "rp1", version: 2, title: "A missing button", text: "It would help to have one.", status: "draft" };
  const { calls } = open([ask("a", { state: "done", answer: { text: "Not yet.", cites: [] }, reports: [report] })], {
    "POST reports/rp1/sent": () => ({ id: "rp1" }),
  });
  const user = userEvent.setup();
  const row = await item("Question a");
  expect(row).toHaveTextContent("A missing button");
  expect(row).toHaveTextContent("It would help to have one.");
  await user.click(within(row).getByRole("button", { name: "Copy: A missing button" }));
  expect(await navigator.clipboard.readText()).toBe("A missing button\n\nIt would help to have one.");
  expect(await screen.findByText("Copied. Send it, then mark it sent.")).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST reports/rp1/sent")).toBe(false);
  await user.click(within(row).getByRole("button", { name: "Mark sent: A missing button" }));
  await waitFor(() => expect(sent(calls, "POST reports/rp1/sent")).toEqual({ read_version: 2 }));
  expect(await screen.findByText("Marked as sent.")).toBeInTheDocument();
});

const draft = (extra: Partial<S["ReportView"]> = {}): S["ReportView"] => ({
  id: "rp1",
  version: 2,
  title: "A missing button",
  text: "It would help\nto have one.",
  status: "draft",
  ...extra,
});
const withReport = (report: S["ReportView"], feedbackTo: string | null | undefined, extra: Record<string, (b: unknown) => unknown> = {}) =>
  open([ask("a", { state: "done", answer: { text: "Not yet.", cites: [] }, reports: [report] })], extra, undefined, feedbackTo);

test("with an address a report has a mail link with its title and text encoded, beside Copy", async () => {
  withReport(draft(), "feedback@example.com");
  const row = await item("Question a");
  const link = within(row).getByRole("link", { name: "Open in your email app: A missing button" });
  expect(link).toHaveAttribute(
    "href",
    `mailto:feedback@example.com?subject=${encodeURIComponent("A missing button")}&body=${encodeURIComponent("It would help\r\nto have one.")}`,
  );
  expect(link).toHaveClass("primary");
  expect(within(row).getByRole("button", { name: "Copy: A missing button" })).not.toHaveClass("primary");
  expect(within(row).getByRole("button", { name: "Mark sent: A missing button" })).not.toHaveClass("primary");
});

test("without an address a report has no mail link and Copy stays the main action", async () => {
  withReport(draft(), null);
  const row = await item("Question a");
  expect(within(row).queryByRole("link", { name: /Open in your mail/ })).toBeNull();
  expect(within(row).getByRole("button", { name: "Copy: A missing button" })).toHaveClass("primary");
});

test("a report too long for a mail link has none, and says to copy it", async () => {
  withReport(draft({ text: "word ".repeat(600) }), "feedback@example.com");
  const row = await item("Question a");
  expect(within(row).queryByRole("link", { name: /Open in your mail/ })).toBeNull();
  expect(within(row).getByText(/too long for a mail link/)).toBeInTheDocument();
  expect(within(row).getByRole("button", { name: "Copy: A missing button" })).toHaveClass("primary");
});

test("opening the report in the mail program makes Mark sent the main action, and Mark sent records it", async () => {
  const { calls } = withReport(draft(), "feedback@example.com", { "POST reports/rp1/sent": () => ({ id: "rp1" }) });
  const user = userEvent.setup();
  const row = await item("Question a");
  const link = within(row).getByRole("link", { name: "Open in your email app: A missing button" });
  // The browser would follow the link; the test only checks what the page does about the click.
  link.addEventListener("click", (e) => e.preventDefault());
  await user.click(link);
  expect(within(row).getByRole("button", { name: "Mark sent: A missing button" })).toHaveClass("primary");
  expect(within(row).getByRole("link", { name: "Open in your email app: A missing button" })).not.toHaveClass("primary");
  expect(calls.some((c) => c.route === "POST reports/rp1/sent")).toBe(false);
  await user.click(within(row).getByRole("button", { name: "Mark sent: A missing button" }));
  await waitFor(() => expect(sent(calls, "POST reports/rp1/sent")).toEqual({ read_version: 2 }));
});

test("copying a report with a mail link also makes Mark sent the main action", async () => {
  withReport(draft(), "feedback@example.com");
  const user = userEvent.setup();
  const row = await item("Question a");
  await user.click(within(row).getByRole("button", { name: "Copy: A missing button" }));
  expect(await navigator.clipboard.readText()).toBe("A missing button\n\nIt would help\nto have one.");
  expect(within(row).getByRole("button", { name: "Mark sent: A missing button" })).toHaveClass("primary");
  expect(within(row).getByRole("link", { name: "Open in your email app: A missing button" })).toBeInTheDocument();
});

test("when copying is blocked the report is not marked sent", async () => {
  const report: S["ReportView"] = { id: "rp1", version: 2, title: "T", text: "Body", status: "draft" };
  const { calls } = open([ask("a", { state: "done", answer: { text: "No.", cites: [] }, reports: [report] })]);
  const user = userEvent.setup();
  vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("blocked"));
  await user.click(await screen.findByRole("button", { name: "Copy: T" }));
  expect(await screen.findByText(/Your browser blocked copying/)).toBeInTheDocument();
  expect(calls.some((c) => c.route === "POST reports/rp1/sent")).toBe(false);
});

test("Set aside dismisses the report with the version read", async () => {
  const report: S["ReportView"] = { id: "rp1", version: 2, title: "T", text: "Body", status: "draft" };
  const { calls } = open([ask("a", { state: "done", answer: { text: "No.", cites: [] }, reports: [report] })], {
    "POST reports/rp1/dismiss": () => ({ id: "rp1" }),
  });
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Set aside: T" }));
  await waitFor(() => expect(sent(calls, "POST reports/rp1/dismiss")).toEqual({ read_version: 2 }));
});

test("a report already sent has no buttons", async () => {
  const report: S["ReportView"] = { id: "rp1", version: 2, title: "T", text: "Body", status: "sent" };
  open([ask("a", { state: "done", answer: { text: "No.", cites: [] }, reports: [report] })]);
  const row = await item("Question a");
  expect(row).toHaveTextContent("Sent");
  expect(within(row).queryByRole("button", { name: /^Copy/ })).toBeNull();
});

test("Close and Escape both close the dialog", async () => {
  const { onClose } = open([]);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Close" }));
  expect(onClose).toHaveBeenCalledTimes(1);
  await user.keyboard("{Escape}");
  await waitFor(() => expect(onClose).toHaveBeenCalledTimes(2));
});
