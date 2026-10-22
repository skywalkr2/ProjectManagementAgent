import "@testing-library/jest-dom/vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { day } from "../lib/dates";
import { besidePane, fakeApi, renderApp } from "../test-utils";
import { LineDetail } from "./TodayDetail";
import { MadeBy } from "./MadeBy";

type Line = S["QueueLineView"];
type Made = NonNullable<Line["made_by"]>;

/** Made-up addresses are built from this, so no address is written out whole. */
const WEB = "https" + "://";
const PAGE = `${WEB}pages.example.com/notes`;

const made = (over: Partial<Made> = {}): Made => ({ kind: "assistant", state: "suggested", inferred: false, ...over });
const line = (over: Partial<Line> = {}): Line => ({
  key: "decision:Q-1",
  group: "decide",
  kind: "decision",
  count: 1,
  untrusted: false,
  unpriced: 0,
  actions: [],
  questions: [],
  outcome: {},
  ...over,
});
const inspector = (m: Made | null) => renderApp(<MadeBy line={line({ made_by: m })} />);
const said = () => document.querySelector("[data-made-by]")?.textContent ?? null;

afterEach(() => vi.unstubAllGlobals());

test("a suggestion nobody has answered says who suggested it, from what, and that it is waiting", () => {
  inspector(made({ source: { title: "Proof dates", origin: { kind: "source", source: "SRC-1" } } }));
  expect(said()).toContain("Suggested by Helper · no answer yet");
  expect(screen.getByRole("button", { name: "From Proof dates" })).toBeInTheDocument();
});

test("the source is one click to the input's saved text", async () => {
  fakeApi({ "GET sources/SRC-1": () => ({ id: "SRC-1", title: "Proof dates", received_at: "2026-10-14T09:00:00Z", trust: "untrusted", text: "The proofs ship Friday." }) });
  inspector(made({ source: { title: "Proof dates", origin: { kind: "source", source: "SRC-1" } } }));
  await userEvent.click(screen.getByRole("button", { name: "From Proof dates" }));
  expect(await screen.findByText("The proofs ship Friday.")).toBeInTheDocument();
});

test("a source with a page is a link that shows its real domain", () => {
  inspector(made({ state: "added", source: { title: "Release notes", origin: { kind: "link", url: PAGE, source: "SRC-2" } } }));
  const link = screen.getByRole("link", { name: "From Release notes" });
  expect(link).toHaveAttribute("href", PAGE);
  expect(document.querySelector("[data-made-by]")).toHaveTextContent("pages.example.com");
});

test("once the person has kept or answered it, it says so with the day instead of waiting", () => {
  const { unmount } = inspector(made({ answered: { how: "kept", on: "2026-10-21" } }));
  expect(said()).toContain(`Suggested by Helper · You kept it, ${day("2026-10-21")}`);
  expect(said()).not.toContain("no answer yet");
  unmount();
  inspector(made({ answered: { how: "answered", on: "2026-10-21", answer: "The later one" } }));
  expect(said()).toContain(`You answered, ${day("2026-10-21")}: The later one`);
});

test("an item that was added says Added by, and worked out when the assistant inferred it", () => {
  inspector(made({ state: "added", inferred: true }));
  expect(said()).toBe("Added by Helper · worked out");
});

test("an item a rule made names the rule, and says a rule when it has no name", () => {
  const { unmount } = inspector(made({ kind: "rule", state: "added", rule: { id: "reply_answered" } }));
  expect(said()).toBe("Added by the rule replies you sent");
  unmount();
  inspector(made({ kind: "rule", state: "added", rule: { id: "some_other", label: "Weekly sweep" } }));
  expect(said()).toBe("Added by the rule Weekly sweep");
});

test("the person's own item says nothing, and neither does a line with no maker", () => {
  const { unmount } = inspector(made({ kind: "person", state: "added" }));
  expect(said()).toBeNull();
  unmount();
  inspector(null);
  expect(said()).toBeNull();
});

test("the inspector of a line says it above the line's own detail", async () => {
  besidePane();
  fakeApi({ "GET followups": () => [] });
  renderApp(<LineDetail line={line({ kind: "decision", question: "Q-1", made_by: made() })} />);
  expect(await screen.findByText(/Suggested by Helper/)).toBeInTheDocument();
});

test("it never reaches a message to copy: what is copied is the message alone", async () => {
  besidePane();
  const message = "Hi Robin,\n\nIs the index final?\n\nThanks!";
  const section: S["FollowupSection"] = {
    person: "PER-2",
    name: "Robin Sample",
    is_pm: false,
    questions: [{ id: "Q-1", title: "Is the index final?", text: "", links: [], kind: "question", status: "open", sent: null, waiting_days: null, chase_due: false, chases: 0, about: null, options: [] }],
    actions: [],
    message,
    to_send: 1,
  };
  fakeApi({ "GET followups": () => [section], "GET people": () => [] });
  renderApp(<LineDetail line={line({ kind: "send", person: "PER-2", made_by: made() })} />);
  const box = await screen.findByRole("textbox");
  expect((box as HTMLTextAreaElement).value).toBe(message);
  const shown = document.querySelector("[data-made-by]") as HTMLElement;
  expect(within(shown).getByText(/Suggested by Helper/)).toBeInTheDocument();
  expect((box as HTMLTextAreaElement).value).not.toMatch(/Helper|Suggested by|Added by/);
  expect(shown.contains(box)).toBe(false);
});
