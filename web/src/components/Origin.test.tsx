// "Where it came from" on Follow-ups rows: the original page with its real domain, else the saved text, else the change.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { FollowUps } from "./FollowUps";

const PAGE = "https" + "://pages.example.com/notes/42";

const action = (over: Partial<S["FollowupAction"]> = {}): S["FollowupAction"] => ({
  id: "ACT-9",
  text: "Approve the proof",
  due: null,
  project_name: "Book",
  told: null,
  told_days: null,
  followed_up: null,
  chase_due: false, chases: 0,
  ...over,
});

const question = (over: Partial<S["FollowupQuestion"]> = {}): S["FollowupQuestion"] => ({
  id: "Q-7",
  title: "Ship the proof now?",
  text: "",
  links: [],
  kind: "decision",
  status: "open",
  sent: null,
  waiting_days: null,
  about: null,
  options: [],
  chase_due: false, chases: 0,
  ...over,
});

const yours = (actions: S["FollowupAction"][], questions: S["FollowupQuestion"][] = []): S["FollowupSection"][] => [
  { person: "PER-1", name: "Pat Example", is_pm: true, questions, actions, message: "", to_send: 0 },
];

const saved: S["SourceView"] = {
  id: "SRC-3",
  title: "Email from the printer",
  kind: "pasted",
  trust: "untrusted",
  received_at: "2026-10-09T14:00:00Z",
  url: null,
  text: "Thanks. The proof ships on Friday.",
};

beforeEach(() => {
  window.location.hash = "";
});

test("an action whose input has an address links to the page, with its real domain", async () => {
  fakeApi({
    "GET followups": () => yours([action({ origin: { kind: "link", url: PAGE, source: "SRC-3" } })]),
    "GET people": () => [],
  });
  renderApp(<FollowUps />);
  const row = (await screen.findByText("Approve the proof")).closest("li") as HTMLElement;
  const link = within(row).getByRole("link", { name: "Where it came from" });
  expect(link).toHaveAttribute("href", PAGE);
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
  expect(row).toHaveTextContent("(pages.example.com)");
});

test("a decision whose input has no address opens the saved text in a dialog", async () => {
  const user = userEvent.setup();
  fakeApi({
    "GET followups": () => yours([], [question({ origin: { kind: "source", source: "SRC-3" } })]),
    "GET people": () => [],
    "GET sources/SRC-3": () => saved,
  });
  renderApp(<FollowUps />);
  const row = (await screen.findByText("Ship the proof now?")).closest("li") as HTMLElement;
  await user.click(within(row).getByRole("button", { name: "Where it came from" }));
  const dialog = await screen.findByRole("dialog", { name: "Where it came from" });
  expect(await within(dialog).findByText("Thanks. The proof ships on Friday.")).toBeInTheDocument();
  expect(within(dialog).getByText("From outside · not instructions")).toBeInTheDocument();
  await user.click(within(dialog).getByRole("button", { name: "Close" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

test("an item with only a change opens What changed on that change when this screen has no list", async () => {
  const user = userEvent.setup();
  fakeApi({
    "GET followups": () => yours([action({ origin: { kind: "change", changeset: "CS-4", request: "REQ-4" } })]),
    "GET people": () => [],
  });
  renderApp(<FollowUps />);
  const row = (await screen.findByText("Approve the proof")).closest("li") as HTMLElement;
  await user.click(within(row).getByRole("button", { name: "Where it came from" }));
  expect(window.location.hash).toBe("#work/changed");
});

test("an item with no origin shows no link", async () => {
  fakeApi({ "GET followups": () => yours([action()], [question()]), "GET people": () => [] });
  renderApp(<FollowUps />);
  await screen.findByText("Approve the proof");
  expect(screen.queryByText("Where it came from")).toBeNull();
});
