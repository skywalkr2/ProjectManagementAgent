import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { RestartProvider } from "../lib/restart";
import { fakeApi, renderApp, setupStep, setupView, statusFixture } from "../test-utils";
import { FirstPromises } from "./FirstPromises";
import { MissedOneProvider } from "./MissedOne";
import { Walkthrough } from "./Walkthrough";

// The walkthrough's first result (design 7.8): once a mailbox is connected and an AI account is chosen it offers the look
// back over the person's own mail with its estimate first; after their Go it lists a handful of the open promises found
// with one follow-up ready to copy; with none found it says so and offers "Missed one".

const view = (over: Partial<S["FirstPromisesView"]> = {}): S["FirstPromisesView"] => ({
  stage: "ready",
  sources: ["Your inbox"],
  days: 14,
  count: 0,
  finished: 0,
  unpriced: 0,
  promises: [],
  more: 0,
  ...over,
});

const promise = (id: string, over: Partial<S["FirstPromise"]> = {}): S["FirstPromise"] => ({
  action: id,
  text: `Promise ${id}`,
  owner: "Ana Example",
  mine: false,
  promised_to: [],
  ...over,
});

const noop = () => undefined;

function show(first: S["FirstPromisesView"], routes: Parameters<typeof fakeApi>[0] = {}, go: (screen: S["WalkthroughView"]["step"]) => void = noop) {
  const calls = fakeApi({ "GET setup/first-promises": () => first, ...routes });
  renderApp(
    <MissedOneProvider>
      <FirstPromises go={go} />
    </MissedOneProvider>,
  );
  return calls;
}

describe("the offer", () => {
  const offer = view({ stage: "offer", count: 12, days: 14, estimate_usd: 0.3 });

  test("it names the days of mail and the items, says about what it costs, and reads nothing before Start", async () => {
    const calls = show(offer);
    expect(await screen.findByRole("heading", { level: 3, name: "Look back over the last 14 days of your own mail" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("12 items to look over. About $0.30 in all. Nothing is read by the assistant until you press Start.");
    expect(calls.filter((c) => c.route === "POST setup/first-promises/go")).toHaveLength(0);
  });

  test("the cost says less than a cent for nothing priced, and the plan's allowance when it has no price", async () => {
    show(view({ ...offer, estimate_usd: 0 }));
    expect(await screen.findByText(/Less than a cent in all\./i)).toBeInTheDocument();
  });

  test("with no price it says it uses the plan's allowance", async () => {
    show(view({ ...offer, estimate_usd: null, unpriced: 12 }));
    expect(await screen.findByText(/It uses your plan's allowance\./)).toBeInTheDocument();
  });

  test("Start starts it once, and the screen then says how far it is", async () => {
    const user = userEvent.setup();
    let stage: S["FirstPromisesView"] = offer;
    const calls = show(offer, {
      "GET setup/first-promises": () => stage,
      "POST setup/first-promises/go": () => {
        stage = view({ stage: "working", count: 12, finished: 3 });
        return { started: 12 };
      },
    });
    await user.click(await screen.findByRole("button", { name: "Start" }));
    expect(await screen.findByText("Looking over your mail: 3 of 12 done.")).toBeInTheDocument();
    expect(calls.filter((c) => c.route === "POST setup/first-promises/go")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Start" })).toBeNull();
  });

  test("a single day of mail and a source with no mail read plainly", async () => {
    show(view({ ...offer, days: 1, count: 1 }));
    expect(await screen.findByRole("heading", { level: 3, name: "Look back over the last day of your own mail" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("1 item to look over.");
  });
});

describe("before the offer", () => {
  test("with no AI account it points back to the account screen", async () => {
    const user = userEvent.setup();
    const go = vi.fn();
    show(view({ stage: "no_ai" }), {}, go);
    expect(await screen.findByText(/Choose an AI account first/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Go to your AI account" }));
    expect(go).toHaveBeenCalledWith("ai");
  });

  test("with no mail it points back to mail and calendar", async () => {
    const user = userEvent.setup();
    const go = vi.fn();
    show(view({ stage: "no_mail" }), {}, go);
    expect(await screen.findByText(/Connect your mail first/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Go to mail and calendar" }));
    expect(go).toHaveBeenCalledWith("mail");
  });

  test("before the first read it says it is reading", async () => {
    show(view({ stage: "reading" }));
    expect(await screen.findByText("Reading your mail. This takes a few seconds.")).toBeInTheDocument();
  });
});

describe("what was found", () => {
  const found = view({
    promises: [
      promise("ACT-1", { text: "Send the floor plan", owner: "Ana Example", promised_to: ["Casey Example"], due: "2026-11-02", quote: "I'll send the floor plan" }),
      promise("ACT-2", { text: "Book the room", mine: true }),
    ],
    more: 2,
    follow_up: { person: "PER-2", name: "Ana Example", message: "Hi Ana,\n\nSend the floor plan.\n\nThanks!", to_send: 1 },
  });

  test("it lists the promises, each with who owes it, to whom, its day and the words it came from", async () => {
    show(found);
    const list = await screen.findByRole("list", { name: "Promises found" });
    const first = within(list).getByText("Send the floor plan").closest("li") as HTMLElement;
    expect(first).toHaveTextContent("Owed by Ana Example");
    expect(first).toHaveTextContent("Promised to Casey Example");
    expect(first).toHaveTextContent("Due");
    expect(first).toHaveTextContent("From: “I'll send the floor plan”");
    const second = within(list).getByText("Book the room").closest("li") as HTMLElement;
    expect(second).toHaveTextContent("You owe this");
    expect(second).not.toHaveTextContent("Owed by");
    expect(screen.getByText("2 more promises are kept. They show on Today when they need you.")).toBeInTheDocument();
  });

  test("one follow-up is ready: Copy puts the message on the clipboard, then Mark sent keeps it as copied", async () => {
    const user = userEvent.setup();
    const calls = show(found, { "POST followups/PER-2/mark-sent": () => ({ questions: 0, actions: 1, question_ids: [], action_ids: ["ACT-1"] }) });
    const section = await screen.findByRole("region", { name: "One follow-up is ready" });
    expect(within(section).getByLabelText("Message to Ana Example")).toHaveValue("Hi Ana,\n\nSend the floor plan.\n\nThanks!");
    await user.click(within(section).getByRole("button", { name: "Copy message" }));
    expect(await navigator.clipboard.readText()).toBe("Hi Ana,\n\nSend the floor plan.\n\nThanks!");
    // Copying alone keeps nothing on the server.
    expect(calls.filter((c) => c.route === "POST followups/PER-2/mark-sent")).toHaveLength(0);
    await user.click(within(section).getByRole("button", { name: "Mark sent" }));
    await waitFor(() => expect(calls.find((c) => c.route === "POST followups/PER-2/mark-sent")?.body).toEqual({ text: "Hi Ana,\n\nSend the floor plan.\n\nThanks!" }));
    expect(await screen.findByText("Marked as sent to Ana Example")).toBeInTheDocument();
  });

  test("the message can be edited first, and the edited words are the ones copied", async () => {
    const user = userEvent.setup();
    show(found);
    const box = await screen.findByLabelText("Message to Ana Example");
    await user.type(box, " PS");
    await user.click(screen.getByRole("button", { name: "Copy message" }));
    expect(await navigator.clipboard.readText()).toBe("Hi Ana,\n\nSend the floor plan.\n\nThanks! PS");
  });

  test("when the browser blocks the copy nothing is marked and Copy stays", async () => {
    const user = userEvent.setup();
    const calls = show(found);
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("blocked"));
    await user.click(await screen.findByRole("button", { name: "Copy message" }));
    expect(await screen.findByText(/Your browser blocked copying/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy message" })).toBeInTheDocument();
    expect(calls.filter((c) => c.route.startsWith("POST"))).toHaveLength(0);
  });

  test("with promises but nobody to follow up with, the list shows and no follow-up is offered", async () => {
    show(view({ promises: [promise("ACT-2", { mine: true })] }));
    expect(await screen.findByRole("list", { name: "Promises found" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "One follow-up is ready" })).toBeNull();
    expect(screen.queryByText(/more promise/)).toBeNull();
  });

  test("with none found it says so plainly and offers Missed one, which opens its form", async () => {
    const user = userEvent.setup();
    show(view());
    expect(await screen.findByText("No open promises found in the mail it looked over.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Promises found" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Missed one" }));
    expect(await screen.findByRole("dialog", { name: "Missed one" })).toBeInTheDocument();
  });
});

describe("in the walkthrough", () => {
  const CORE = ["workspace", "ai", "mail", "backup", "people", "template", "first_note", "addons"];
  const shell = (step: S["WalkthroughView"]["step"]) => {
    const calls = fakeApi({
      "GET setup": () => setupView(CORE.map((id) => setupStep(id, { done: id === "mail" })), { walkthrough: { open: true, step } }),
      "GET setup/first-promises": () => view({ stage: "offer", count: 4, days: 14, estimate_usd: 0.12 }),
      "GET settings": () => ({ fingerprint: "fp", items: [] }),
      "GET me": () => ({ person: null, full_name: "" }),
      "GET ai/endpoints": () => [],
      "GET ai/accounts": () => [],
      "GET ai/local": () => [],
      "GET packs": () => ({ enabled: true, feeds: [], available: [], installed: [] }),
      "GET sign-ins": () => [],
      "GET watch": () => [],
      "GET status": () => statusFixture(),
      "GET templates": () => [],
      "POST setup/walkthrough": (body: unknown) => ({ open: true, step: "you", closed: false, finished: false, ...(body as object) }),
    });
    renderApp(
      <RestartProvider hellos={1} pollSeconds={0.05} doneSeconds={0.05}>
        <Walkthrough at={null} onOpenPeople={noop} onOpenAddons={noop} onHandIn={noop} onChooseSource={noop} onFinishLater={noop} onDone={noop} />
      </RestartProvider>,
    );
    return calls;
  };

  test("the first result is the screen right after mail and before backups, and nothing else comes first", async () => {
    const user = userEvent.setup();
    shell("mail");
    const nav = await screen.findByRole("navigation", { name: "Setup steps" });
    expect(within(nav).getAllByRole("button").map((b) => b.getAttribute("data-screen"))).toEqual(["you", "ai", "mail", "promises", "backup", "people", "done"]);
    await user.click(await screen.findByRole("button", { name: "Next" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Your promises" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 3, name: "Look back over the last 14 days of your own mail" })).toBeInTheDocument();
    // The offer is on screen with its estimate before anything about projects, areas, packs or more accounts.
    expect(screen.queryByText(/Optional extras/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Backups" })).toBeInTheDocument();
  });

  test("it resumes at the first result", async () => {
    shell("promises");
    expect(await screen.findByRole("heading", { level: 2, name: "Your promises" })).toBeInTheDocument();
  });
});
