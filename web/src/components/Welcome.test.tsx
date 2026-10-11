import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { RestartNotice, RestartProvider } from "../lib/restart";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { Welcome } from "./Welcome";

const step = (id: string, extra: Partial<S["SetupStepView"]> = {}): S["SetupStepView"] => ({
  id,
  done: false,
  skipped: false,
  label: "",
  explanation: "",
  action: null,
  plugin: null,
  ...extra,
});

const setting = (key: string, value: unknown, extra: Partial<S["SettingItem"]> = {}): S["SettingItem"] => ({
  key,
  file: "workspace",
  group: "workspace",
  description: key,
  type: "text",
  options: [],
  value,
  default: value,
  source: "default",
  locked: false,
  basic: true,
  editable: true,
  ...extra,
});

const ITEMS = [
  setting("workspace.name", "Workspace"),
  setting("workspace.user.full_name", ""),
  setting("workspace.user.timezone", "UTC"),
];

const CORE = ["workspace", "template", "ai", "backup", "people", "first_note"];

function api(steps: S["SetupStepView"][], extra: Record<string, (body: unknown) => unknown> = {}) {
  return fakeApi({
    "GET setup": () => ({ steps, finished: false, local: true }),
    "GET settings": () => ({ fingerprint: "fp-1", items: ITEMS }),
    "GET templates": () => [
      { id: "tpl-a", name: "Book project", description: "Chapters and drafts." },
      { id: "tpl-b", name: "Event", description: "Dates and tasks." },
    ],
    "GET ai/endpoints": () => [],
    ...extra,
  });
}

const open = (props: Partial<Parameters<typeof Welcome>[0]> = {}) => {
  const onOpenPeople = vi.fn();
  const onHandIn = vi.fn();
  const view = renderApp(<Welcome focusStep={null} onOpenPeople={onOpenPeople} onHandIn={onHandIn} {...props} />);
  return { onOpenPeople, onHandIn, ...view };
};

const section = (id: string) => document.querySelector(`[data-step="${id}"]`) as HTMLElement;

test("one section per step, in the server's order, each saying in words where it stands", async () => {
  api([
    step("workspace", { done: true }),
    step("template", { skipped: true }),
    step("ai"),
    step("plugin/tidy", { label: "Connect the tidy-up tool", explanation: "It files things away.", plugin: "plugin" }),
  ]);
  open();
  await screen.findByRole("heading", { name: "Add an AI account and test it" });
  const sections = Array.from(document.querySelectorAll("[data-step]"));
  expect(sections.map((s) => s.getAttribute("data-step"))).toEqual(["workspace", "template", "ai", "plugin/tidy"]);
  expect(within(section("workspace")).getByRole("heading", { name: "Name the workspace and say who you are" })).toBeInTheDocument();
  expect(section("workspace")).toHaveTextContent("Done");
  expect(section("template")).toHaveTextContent("Skipped");
  expect(section("ai")).toHaveTextContent("Not done yet");
  expect(section("plugin/tidy")).toHaveTextContent("Connect the tidy-up tool");
  expect(section("plugin/tidy")).toHaveTextContent("It files things away.");
});

test("Skip posts the step and turns into a way back; Reopen undoes it", async () => {
  const user = userEvent.setup();
  let skipped = false;
  const calls = fakeApi({
    "GET setup": () => ({ steps: [step("backup", { skipped })], finished: false, local: true }),
    "GET settings": () => ({ fingerprint: "fp-1", items: ITEMS }),
    "POST setup/backup/skip": () => {
      skipped = true;
      return { ok: "backup" };
    },
    "POST setup/backup/reopen": () => {
      skipped = false;
      return { ok: "backup" };
    },
  });
  open();
  const button = await screen.findByRole("button", { name: "Skip: Choose a backup folder" });
  await user.click(button);
  await waitFor(() => expect(calls.some((c) => c.route === "POST setup/backup/skip")).toBe(true));
  const back = await screen.findByRole("button", { name: "Do it now: Choose a backup folder" });
  // The same button stays in place, so keyboard focus is not lost.
  expect(back).toBe(button);
  expect(back).toHaveFocus();
  expect(section("backup")).toHaveTextContent("Skipped");
  expect(await screen.findByText(/Skipped: Choose a backup folder/)).toBeInTheDocument();
  await user.click(back);
  await waitFor(() => expect(calls.some((c) => c.route === "POST setup/backup/reopen")).toBe(true));
  expect(await screen.findByRole("button", { name: "Skip: Choose a backup folder" })).toBeInTheDocument();
});

test("a plugin's step id keeps its slash in the address, and Undo on the toast puts it back", async () => {
  const user = userEvent.setup();
  const calls = api([step("plugin/tidy", { label: "Connect the tidy-up tool" })], {
    "POST setup/plugin/tidy/skip": () => ({ ok: "plugin/tidy" }),
    "POST setup/plugin/tidy/reopen": () => ({ ok: "plugin/tidy" }),
  });
  open();
  await user.click(await screen.findByRole("button", { name: "Skip: Connect the tidy-up tool" }));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST setup/plugin/tidy/reopen")).toBe(true));
});

test("the template step's skip is called Start empty, and a done step has no skip", async () => {
  api([step("workspace", { done: true }), step("template")]);
  open();
  expect(await screen.findByRole("button", { name: "Start empty: Pick a starting template" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Skip: Name the workspace/ })).toBeNull();
});

test("the workspace step starts the time zone from this browser while it is still the default", async () => {
  const user = userEvent.setup();
  vi.spyOn(Intl.DateTimeFormat.prototype, "resolvedOptions").mockReturnValue({ timeZone: "Europe/Paris" } as Intl.ResolvedDateTimeFormatOptions);
  const calls = api([step("workspace")], {
    "POST settings": () => ({ changes: [], fingerprint: "fp-2", restarts: false }),
  });
  open();
  expect(await screen.findByLabelText("Your time zone")).toHaveValue("Europe/Paris");
  await user.type(screen.getByLabelText("Your full name"), "Sam Tester");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST settings")).toBe(true));
  const body = calls.find((c) => c.route === "POST settings")!.body;
  expect(body).toEqual({
    changes: { "workspace.user.full_name": "Sam Tester", "workspace.user.timezone": "Europe/Paris" },
    reset: [],
    fingerprint: "fp-1",
  });
  vi.restoreAllMocks();
});

test("the workspace step shows the server's words when a value is refused, and keeps what was typed", async () => {
  const user = userEvent.setup();
  api([step("workspace")], { "POST settings": () => new Refuse(400, "That time zone isn't one we know.") });
  open();
  const name = await screen.findByLabelText("Workspace name");
  await user.clear(name);
  await user.type(name, "Harbor");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("That time zone isn't one we know.");
  expect(screen.getByLabelText("Workspace name")).toHaveValue("Harbor");
});

test("the template step applies one template and says the app restarts", async () => {
  const user = userEvent.setup();
  const calls = api([step("template")], { "POST templates/apply": () => ({ plugins: [], restarts: true }) });
  renderApp(
    <RestartProvider hellos={1}>
      <RestartNotice />
      <Welcome focusStep={null} onOpenPeople={() => undefined} onHandIn={() => undefined} />
    </RestartProvider>,
  );
  expect(await screen.findByText("Chapters and drafts.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Apply Event" }));
  await waitFor(() => expect(calls.find((c) => c.route === "POST templates/apply")?.body).toEqual({ id: "tpl-b" }));
  expect(await screen.findByText("Applied Event.")).toBeInTheDocument();
  await waitFor(() => expect(document.querySelector(".restart-slot")).toHaveTextContent("Restarting to use the new settings…"));
});

test("People & projects and Hand in are buttons that open those screens", async () => {
  const user = userEvent.setup();
  api(CORE.filter((id) => id === "people" || id === "first_note").map((id) => step(id)));
  const { onOpenPeople, onHandIn } = open();
  await user.click(await screen.findByRole("button", { name: "Open People & projects" }));
  await user.click(screen.getByRole("button", { name: "Hand something in" }));
  expect(onOpenPeople).toHaveBeenCalledTimes(1);
  expect(onHandIn).toHaveBeenCalledTimes(1);
});

test("a plugin's step with an action starts that action for the whole workspace", async () => {
  const user = userEvent.setup();
  const calls = api([step("plugin/tidy", { label: "Connect the tidy-up tool", action: "plugin/connect", plugin: "plugin" })], {
    "POST plugin-actions/plugin/connect/preview": () => ({
      token: "tok-1",
      action: "plugin/connect",
      summary: "Connect it",
      ops: [],
      files: [],
      previews: [],
      choices: [],
      notes: [],
      expires_at: "2026-10-09T15:00:00Z",
    }),
  });
  open();
  await user.click(await screen.findByRole("button", { name: "Connect the tidy-up tool" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST plugin-actions/plugin/connect/preview")).toBe(true));
  expect(calls.find((c) => c.route === "POST plugin-actions/plugin/connect/preview")!.body).toMatchObject({ target: null });
});

test("opening the guide at a step puts focus on that step's heading", async () => {
  api(CORE.map((id) => step(id)));
  open({ focusStep: { id: "backup", n: 1 } });
  const heading = await screen.findByRole("heading", { name: "Choose a backup folder" });
  await waitFor(() => expect(heading).toHaveFocus());
});
