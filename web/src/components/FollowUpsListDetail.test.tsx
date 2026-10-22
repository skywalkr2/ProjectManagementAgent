// Follow-ups as list | detail (design 7.13): one line per person with who, how many and the one primary; the chosen person's
// message and asks in the detail beside the list (a drawer below 1024px); the first person is chosen as the list opens; Up and
// Down move the choice, Enter moves the cursor into the detail and Escape closes it; on a phone the messages to send are gone
// through one person at a time.
import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { S } from "../lib/api";
import { useShortcuts } from "../lib/keys";
import { besidePane, fakeApi, renderApp } from "../test-utils";
import { FollowUps } from "./FollowUps";

afterEach(() => vi.unstubAllGlobals());

const question = (id: string, title: string, extra: Partial<S["FollowupQuestion"]> = {}): S["FollowupQuestion"] => ({
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
  ...extra,
});

const person = (id: string, name: string, extra: Partial<S["FollowupSection"]> = {}): S["FollowupSection"] => ({
  person: id,
  name,
  is_pm: false,
  questions: [question(`Q-${id}`, `Question for ${name}`)],
  actions: [],
  message: `Hi ${name},\n\nQuestion for ${name}\n\nThanks!`,
  to_send: 1,
  ...extra,
});

const sections = [person("PER-1", "Ana Person"), person("PER-2", "Robin Sample"), person("PER-3", "Casey Moor")];

const routes = (list: () => S["FollowupSection"][] = () => sections, extra: Record<string, (b: unknown) => unknown> = {}) => ({
  "GET followups": list,
  "GET people": () => [],
  "POST followups/PER-1/mark-sent": () => ({ questions: 1, actions: 0, question_ids: ["Q-PER-1"], action_ids: [] }),
  ...extra,
});

function WithShortcuts() {
  useShortcuts({ next: "j", previous: "k", primary: "a" }, { undo: () => undefined, hand_in: () => undefined, ask: () => undefined, help: () => undefined });
  return <FollowUps />;
}

const line = (name: string) => screen.findByRole("listitem", { name });
const chosenId = () => document.querySelector("[aria-current]")?.getAttribute("data-choice");

describe("beside the list", () => {
  beforeEach(() => besidePane());

  test("a person is one line, and the first person is chosen as the list opens, with their message and asks in the detail", async () => {
    fakeApi(routes());
    renderApp(<FollowUps />);
    const pane = await screen.findByRole("complementary", { name: "Ana Person" });
    expect(chosenId()).toBe("PER-1");
    expect(within(pane).getByRole("textbox", { name: /Message to Ana Person/ })).toHaveValue(sections[0].message);
    expect(within(pane).getByText("Question for Ana Person")).toBeInTheDocument();
    // The line says who, how many and holds Copy; nothing of the message.
    const robin = await line("Robin Sample");
    expect(robin).toHaveTextContent("1 to send");
    expect(within(robin).getAllByRole("button").map((b) => b.textContent)).toEqual([expect.stringMatching(/^Robin Sample/), "Copy 1"]);
    expect(within(robin).queryByRole("textbox")).toBeNull();
    expect(screen.queryByText("Question for Robin Sample")).toBeNull();
  });

  test("a click on a line chooses that person, and Copy on the chosen line copies the message in the detail, after which both say Mark sent", async () => {
    const user = userEvent.setup();
    fakeApi(routes());
    renderApp(<FollowUps />);
    await screen.findByRole("complementary", { name: "Ana Person" });
    await user.click(await line("Robin Sample"));
    const pane = await screen.findByRole("complementary", { name: "Robin Sample" });
    expect(within(pane).getByText("Question for Robin Sample")).toBeInTheDocument();
    expect(chosenId()).toBe("PER-2");
    await user.click(within(await line("Robin Sample")).getByRole("button", { name: "Copy 1" }));
    expect(await navigator.clipboard.readText()).toBe(sections[1].message);
    expect(within(await line("Robin Sample")).getByRole("button", { name: "Mark sent" })).toBeInTheDocument();
    expect(within(pane).getAllByRole("button", { name: "Mark sent" }).length).toBeGreaterThan(0);
    // Another person's line is not touched.
    expect(within(await line("Casey Moor")).getByRole("button", { name: "Copy 1" })).toBeInTheDocument();
  });

  test("Copy on a line whose detail is not shown shows the message first, with the cursor in it, and copies nothing", async () => {
    const user = userEvent.setup();
    fakeApi(routes());
    renderApp(<FollowUps />);
    await screen.findByRole("complementary", { name: "Ana Person" });
    await user.click(within(await line("Casey Moor")).getByRole("button", { name: "Copy 1" }));
    const pane = await screen.findByRole("complementary", { name: "Casey Moor" });
    const box = within(pane).getByRole("textbox", { name: /Message to Casey Moor/ });
    await waitFor(() => expect(box).toHaveFocus());
    expect(await navigator.clipboard.readText()).toBe("");
  });

  test("Mark sent, from the detail, records the message and the person leaves the list, so the next is chosen", async () => {
    const user = userEvent.setup();
    let list = sections;
    const calls = fakeApi(
      routes(() => list, {
        "POST followups/PER-1/mark-sent": () => {
          list = sections.slice(1);
          return { questions: 1, actions: 0, question_ids: ["Q-PER-1"], action_ids: [] };
        },
        "POST followups/PER-1/unmark-sent": () => ({ ok: "PER-1" }),
      }),
    );
    renderApp(<FollowUps />);
    const pane = await screen.findByRole("complementary", { name: "Ana Person" });
    await user.click(within(pane).getByRole("button", { name: "More actions for Ana Person" }));
    await user.click(await screen.findByRole("menuitem", { name: "Mark sent" }));
    await waitFor(() => expect(calls.find((c) => c.route === "POST followups/PER-1/mark-sent")?.body).toEqual({ text: sections[0].message }));
    expect(await screen.findByRole("complementary", { name: "Robin Sample" })).toBeInTheDocument();
    expect(chosenId()).toBe("PER-2");
  });

  test("Down and Up move the choice with the cursor, Enter moves the cursor into the detail, Escape closes it and returns to the line", async () => {
    const user = userEvent.setup();
    fakeApi(routes());
    renderApp(<WithShortcuts />);
    await screen.findByRole("complementary", { name: "Ana Person" });
    (await line("Ana Person")).focus();
    await user.keyboard("{ArrowDown}");
    expect(await screen.findByRole("complementary", { name: "Robin Sample" })).toBeInTheDocument();
    expect(await line("Robin Sample")).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(await screen.findByRole("complementary", { name: "Casey Moor" })).toBeInTheDocument();
    await user.keyboard("{ArrowUp}");
    expect(await screen.findByRole("complementary", { name: "Robin Sample" })).toBeInTheDocument();
    await user.keyboard("{Enter}");
    const pane = screen.getByRole("complementary", { name: "Robin Sample" });
    await waitFor(() => expect(pane.contains(document.activeElement)).toBe(true));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("complementary")).toBeNull());
    await waitFor(async () => expect(await line("Robin Sample")).toHaveFocus());
  });

  test("Waiting on them: a line says who, how many and the longest wait; the detail has each ask with its own button and menu", async () => {
    const user = userEvent.setup();
    const waiting = person("PER-2", "Robin Sample", {
      to_send: 0,
      questions: [question("Q-7", "Is the index final?", { status: "sent", sent: "2026-10-10", waiting_days: 6, chase_due: true })],
      actions: [{ id: "ACT-1", text: "Send the index", due: null, project_name: "Book", told: "2026-10-12", told_days: 2, followed_up: null, chase_due: false, chases: 0 }],
    });
    fakeApi(routes(() => [waiting]));
    renderApp(<FollowUps />);
    await user.click(await screen.findByRole("button", { name: "Waiting on them" }));
    const row = await line("Robin Sample");
    expect(row).toHaveTextContent("2 waiting");
    expect(within(row).getByText("waiting 6 days · follow up")).toBeInTheDocument();
    const pane = await screen.findByRole("complementary", { name: "Robin Sample" });
    expect(within(pane).getByRole("button", { name: "Record reply" })).toBeInTheDocument();
    expect(within(pane).getByRole("button", { name: "Mark their work done" })).toBeInTheDocument();
    expect(within(pane).getByRole("button", { name: "More actions for Is the index final?" })).toBeInTheDocument();
    expect(within(pane).getByRole("button", { name: "More actions for Send the index" })).toBeInTheDocument();
  });
});

describe("below 1024px", () => {
  test("nothing is chosen as the list opens; a line opens its detail as a drawer, and closing it puts the cursor back on the line", async () => {
    const user = userEvent.setup();
    fakeApi(routes());
    renderApp(<FollowUps />);
    const row = await line("Robin Sample");
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(within(row).getByRole("button", { name: /^Robin Sample/ }));
    const drawer = await screen.findByRole("dialog", { name: "Robin Sample" });
    expect(within(drawer).getByRole("textbox", { name: /Message to Robin Sample/ })).toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(async () => expect(await line("Robin Sample")).toHaveFocus());
  });
});

describe("review mode on a phone", () => {
  beforeEach(() => document.documentElement.setAttribute("data-narrow", ""));
  afterEach(() => document.documentElement.removeAttribute("data-narrow"));

  test("goes through the messages to send one person at a time, with Copy and Mark sent on the message and Next at the bottom", async () => {
    const user = userEvent.setup();
    const calls = fakeApi(routes());
    renderApp(<FollowUps />);
    await user.click(await screen.findByRole("button", { name: "Send one at a time" }));
    expect(await screen.findByRole("heading", { name: "1 of 3 to send" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Message to Ana Person/ })).toHaveValue(sections[0].message);
    expect(screen.queryByRole("textbox", { name: /Message to Robin Sample/ })).toBeNull();
    // The bar has Next only: nothing here is looked at and approved or sent back.
    const bar = screen.getByRole("group", { name: "What to do with this one" });
    expect(within(bar).getAllByRole("button").map((b) => b.textContent)).toEqual(["Next"]);
    await user.click(screen.getByRole("button", { name: "Copy message" }));
    expect(await navigator.clipboard.readText()).toBe(sections[0].message);
    expect(calls.some((c) => c.route.startsWith("POST"))).toBe(false);
    await user.click(within(bar).getByRole("button", { name: "Next" }));
    expect(await screen.findByRole("heading", { name: "2 of 3 to send" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /Message to Robin Sample/ })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to the list" }));
    expect(await screen.findByRole("heading", { name: "Follow-ups" })).toBeInTheDocument();
  });

  test("is offered only on a phone, and only on the list of messages to send", async () => {
    const user = userEvent.setup();
    fakeApi(routes());
    renderApp(<FollowUps />);
    await screen.findByRole("button", { name: "Send one at a time" });
    await user.click(screen.getByRole("button", { name: "Later" }));
    expect(screen.queryByRole("button", { name: "Send one at a time" })).toBeNull();
  });

  test("on a wide window there is no review mode", async () => {
    document.documentElement.removeAttribute("data-narrow");
    fakeApi(routes());
    renderApp(<FollowUps />);
    await line("Ana Person");
    expect(screen.queryByRole("button", { name: "Send one at a time" })).toBeNull();
  });
});
