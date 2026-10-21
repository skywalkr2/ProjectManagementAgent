import "@testing-library/jest-dom/vitest";
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { setSideChoice } from "../lib/sides";
import { forgetLine } from "../lib/today";
import { RestartProvider } from "../lib/restart";
import { fakeApi, renderApp, statusFixture, type Routes } from "../test-utils";
import { FollowUps } from "./FollowUps";
import { Today } from "./Today";

// The All / Personal / <business> filter on Today and Follow-ups (design 6.32, S1-4b). The names are made up here.
const BUSINESS = "Example Works";

type Line = S["QueueLineView"];
const line = (kind: Line["kind"], over: Partial<Line> = {}): Line => ({
  key: `${kind}:1`,
  group: "decide",
  kind,
  count: 1,
  untrusted: false,
  unpriced: 0,
  actions: [],
  questions: [],
  outcome: {},
  ...over,
});
const personal = line("decision", { key: "question:Q-1", text: "Pick the family photo", question: "Q-1", side: "personal" });
const work = line("decision", { key: "question:Q-2", text: "Approve the invoice run", question: "Q-2", side: "business" });
const restart = line("restart", { key: "restart", count: 2 });
const sort = line("unfiled", { key: "unfiled", group: "review", count: 3, state: "which_side", subject: BUSINESS });

const hasBusiness: Routes = { "GET setup/business": () => ({ business: true, name: BUSINESS }) };
const noBusiness: Routes = { "GET setup/business": () => ({ business: false, name: null }) };

function showToday(lines: Line[], extra: Routes = {}) {
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
    "GET today/priorities": () => ({ lines: [], more: 0, blocker: 0, coming: [] }),
    "GET today/week": () => ({ first: "2026-10-19", last: "2026-10-23", due: [], waiting: [], meetings: [] }),
    "GET watch": () => [],
    "GET projects": () => [],
    "GET status": () => statusFixture({ can_restart: true }, { assistant: { last_run_at: "2026-10-20T08:00:00Z" } }),
    "GET runtime-config": () => ({ instance: null }),
    ...extra,
  });
  return renderApp(
    <RestartProvider hellos={1}>
      <Today workspace="Workspace" onView={vi.fn()} onAddSource={vi.fn()} onOpenGuide={vi.fn()} onOpenRecord={vi.fn()} shortcuts={{ next: "j", previous: "k" }} />
    </RestartProvider>,
  );
}

const lineKeys = () => Array.from(document.querySelectorAll("[data-queue-line]")).map((el) => el.getAttribute("data-queue-line"));
const choice = (name: string) => screen.getByRole("radio", { name });

beforeEach(() => {
  window.localStorage.clear();
  setSideChoice("all");
  window.localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  forgetLine();
});

test("with no business there is no filter on Today, whatever this browser remembered", async () => {
  window.localStorage.setItem("cockpit:side-filter", "personal");
  showToday([personal, work], noBusiness);
  expect(await screen.findByText("Approve the invoice run", { selector: "li *" })).toBeInTheDocument();
  expect(screen.getByText("Pick the family photo", { selector: "li *" })).toBeInTheDocument();
  expect(screen.queryByRole("radiogroup", { name: "Show" })).toBeNull();
});

test("with a business, Today offers All, Personal and the business by its name, with All picked", async () => {
  showToday([personal, work], hasBusiness);
  const group = await screen.findByRole("radiogroup", { name: "Show" });
  expect(within(group).getAllByRole("radio").map((r) => r.textContent)).toEqual(["All", "Personal", BUSINESS]);
  expect(choice("All")).toBeChecked();
  expect(screen.getByText("Approve the invoice run", { selector: "li *" })).toBeInTheDocument();
});

test("picking Personal hides the business lines and keeps the app's own lines and the Sort line", async () => {
  const user = userEvent.setup();
  showToday([personal, work, restart, sort], hasBusiness);
  await user.click(await screen.findByRole("radio", { name: "Personal" }));
  await waitFor(() => expect(screen.queryByText("Approve the invoice run", { selector: "li *" })).toBeNull());
  expect(screen.getByText("Pick the family photo", { selector: "li *" })).toBeInTheDocument();
  expect(lineKeys().sort()).toEqual(["decision", "restart", "unfiled"]);
  expect(screen.getByText(`Sort 3 items: Personal or ${BUSINESS}?`)).toBeInTheDocument();
  // The heading counts what shows: the personal line, the restart and the Sort line.
  expect(screen.getAllByText(/3 things need you/).length).toBeGreaterThan(0);
  await user.click(screen.getByRole("radio", { name: BUSINESS }));
  expect(await screen.findByText("Approve the invoice run", { selector: "li *" })).toBeInTheDocument();
  expect(screen.queryByText("Pick the family photo", { selector: "li *" })).toBeNull();
  expect(lineKeys().sort()).toEqual(["decision", "restart", "unfiled"]);
});

test("a side with nothing on it says which side it is", async () => {
  const user = userEvent.setup();
  showToday([personal], hasBusiness);
  await user.click(await screen.findByRole("radio", { name: BUSINESS }));
  expect(await screen.findByText(`Nothing on the ${BUSINESS} side today.`)).toBeInTheDocument();
  expect(screen.getByText(new RegExp(`Nothing on the ${BUSINESS} side needs you`))).toBeInTheDocument();
  expect(screen.queryByText("Nothing needs you right now.")).toBeNull();
});

test("the pick is remembered on this browser and survives the screen being drawn again", async () => {
  const user = userEvent.setup();
  showToday([personal, work], hasBusiness);
  await user.click(await screen.findByRole("radio", { name: "Personal" }));
  expect(window.localStorage.getItem("cockpit:side-filter")).toBe("personal");
  cleanup();
  showToday([personal, work], hasBusiness);
  await screen.findByRole("radiogroup", { name: "Show" });
  expect(choice("Personal")).toBeChecked();
  await waitFor(() => expect(screen.queryByText("Approve the invoice run", { selector: "li *" })).toBeNull());
  expect(screen.getByText("Pick the family photo", { selector: "li *" })).toBeInTheDocument();
});

test("the filter works from the keyboard", async () => {
  const user = userEvent.setup();
  showToday([personal, work], hasBusiness);
  await screen.findByRole("radiogroup", { name: "Show" });
  act(() => choice("All").focus());
  await user.keyboard("{ArrowRight}");
  expect(choice("Personal")).toHaveFocus();
  await user.keyboard(" ");
  expect(choice("Personal")).toBeChecked();
  await waitFor(() => expect(screen.queryByText("Approve the invoice run", { selector: "li *" })).toBeNull());
});

// ---- Follow-ups ------------------------------------------------------------------------------------------------------

const question = (id: string, title: string, side: S["FollowupQuestion"]["side"], over: Partial<S["FollowupQuestion"]> = {}): S["FollowupQuestion"] => ({
  id,
  title,
  text: "",
  links: [],
  kind: "question",
  status: "open",
  sent: null,
  waiting_days: null,
  chase_due: false,
  chases: 0,
  about: null,
  options: [],
  side,
  ...over,
});
const action = (id: string, text: string, side: S["FollowupAction"]["side"]): S["FollowupAction"] => ({
  id,
  text,
  due: null,
  project_name: "",
  told: null,
  told_days: null,
  followed_up: null,
  chase_due: false,
  chases: 0,
  side,
});
const sections: S["FollowupSection"][] = [
  {
    person: "PER-1",
    name: "Pat Example",
    is_pm: true,
    questions: [question("Q-1", "Pick the family photo", "personal", { kind: "decision" }), question("Q-2", "Approve the invoice run", "business", { kind: "decision" })],
    actions: [],
    message: "",
    to_send: 0,
  },
  {
    person: "PER-2",
    name: "Robin Sample",
    is_pm: false,
    questions: [question("Q-3", "Is the index final?", "personal")],
    actions: [action("ACT-1", "Send the invoice", "business")],
    message: "Hi Robin,\n\nIs the index final?\n\nAction items with you:\n- Send the invoice",
    to_send: 2,
  },
  {
    person: "PER-3",
    name: "Dana Sample",
    is_pm: false,
    questions: [question("Q-4", "Can the crew start Monday?", "business")],
    actions: [],
    message: "Hi Dana,\n\nCan the crew start Monday?",
    to_send: 1,
  },
];

function showFollowUps(extra: Routes = hasBusiness) {
  fakeApi({ "GET followups": () => sections, "GET people": () => [], ...extra });
  return renderApp(<FollowUps />);
}

test("Follow-ups has the same filter: the person's own rows go by side, and someone's message stays whole while any of it shows", async () => {
  const user = userEvent.setup();
  showFollowUps();
  await screen.findByRole("radiogroup", { name: "Show" });
  expect(await screen.findByText("Dana Sample")).toBeInTheDocument();
  await user.click(screen.getByRole("radio", { name: "Personal" }));
  await waitFor(() => expect(screen.queryByText("Dana Sample")).toBeNull());
  expect(screen.getByText("Robin Sample")).toBeInTheDocument();
  expect(screen.getByText("Pick the family photo")).toBeInTheDocument();
  expect(screen.queryByText("Approve the invoice run")).toBeNull();
  // Robin's one message still covers both of the rows it was made from.
  expect(screen.getByRole("button", { name: "Copy 2" })).toBeInTheDocument();
  await user.click(screen.getByRole("radio", { name: BUSINESS }));
  expect(await screen.findByText("Dana Sample")).toBeInTheDocument();
  expect(screen.getByText("Approve the invoice run")).toBeInTheDocument();
  expect(screen.queryByText("Pick the family photo")).toBeNull();
});

test("a side with nothing to follow up says which side it is, and with no business there is no filter", async () => {
  const user = userEvent.setup();
  showFollowUps({ ...hasBusiness, "GET followups": () => [sections[2]] });
  await user.click(await screen.findByRole("radio", { name: "Personal" }));
  expect(await screen.findByText("Nothing on the Personal side to follow up.")).toBeInTheDocument();
  cleanup();
  showFollowUps(noBusiness);
  expect(await screen.findByText("Dana Sample")).toBeInTheDocument();
  expect(screen.queryByRole("radiogroup", { name: "Show" })).toBeNull();
});
