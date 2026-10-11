import "@testing-library/jest-dom/vitest";
import { useState } from "react";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { RestartNotice, RestartProvider } from "../lib/restart";
import { Settings } from "./Settings";

function item(key: string, extra: Partial<S["SettingItem"]> = {}): S["SettingItem"] {
  const [file, ...rest] = key.split(".");
  return {
    key,
    file,
    group: rest.length > 1 ? `${file}.${rest[0]}` : file,
    description: `What ${key} does`,
    type: "text",
    options: [],
    value: "",
    default: "",
    source: "default",
    locked: false,
    basic: true,
    editable: true,
    ...extra,
  };
}

const ITEMS: S["SettingItem"][] = [
  item("demo.title", { value: "Lantern", default: "Workspace", source: "file", description: "The display name." }),
  item("demo.limit", { type: "number", value: 2, default: 2 }),
  item("demo.count", { type: "integer", value: 4, default: 4 }),
  item("demo.on", { type: "yes_no", value: true, default: true }),
  item("demo.mode", { type: "choice", options: ["person", "rule"], value: "person", default: "person" }),
  item("demo.names", { type: "list", value: ["a", "b"], default: [] }),
  item("demo.fixed", { value: "from env", source: "env", locked: true }),
  item("demo.flagged", { value: "from flag", source: "flag", locked: true }),
  item("demo.table", { type: "other", value: { x: 1 }, editable: false }),
  item("demo.server", { value: "local", editable: false }),
  item("demo.advanced", { value: "deep", basic: false, description: "A rarely needed thing." }),
];

function api(items = ITEMS, extra: Record<string, (body: unknown) => unknown> = {}) {
  let fingerprint = "fp-1";
  return fakeApi({
    "GET settings": () => ({ fingerprint, items }),
    ...extra,
    "POST settings": (body) => {
      const handler = extra["POST settings"];
      const out = handler ? handler(body) : { changes: [], fingerprint, restarts: false };
      if (!(out instanceof Refuse)) fingerprint = (out as S["SettingsSaved"]).fingerprint;
      return out;
    },
  });
}

const open = () => renderApp(<Settings onOpenGuide={() => undefined} />);
const posted = (calls: ReturnType<typeof fakeApi>) => calls.filter((c) => c.route === "POST settings").map((c) => c.body);

test("basic settings show first and More settings reveals the rest", async () => {
  const user = userEvent.setup();
  api();
  open();
  expect(await screen.findByLabelText("The display name.")).toBeInTheDocument();
  expect(screen.queryByLabelText("A rarely needed thing.")).toBeNull();
  await user.click(screen.getByRole("button", { name: "More settings" }));
  expect(screen.getByLabelText("A rarely needed thing.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Fewer settings" })).toHaveAttribute("aria-expanded", "true");
});

test("the search looks at every setting by its key and description, advanced ones included", async () => {
  const user = userEvent.setup();
  api();
  open();
  await screen.findByLabelText("The display name.");
  await user.type(screen.getByRole("searchbox", { name: "Search settings" }), "rarely");
  expect(screen.getByLabelText("A rarely needed thing.")).toBeInTheDocument();
  expect(screen.queryByLabelText("The display name.")).toBeNull();
  expect(screen.getByText("1 setting shown.")).toBeInTheDocument();
  await user.clear(screen.getByRole("searchbox", { name: "Search settings" }));
  await user.type(screen.getByRole("searchbox", { name: "Search settings" }), "demo.advanced");
  expect(screen.getByLabelText("A rarely needed thing.")).toBeInTheDocument();
  await user.clear(screen.getByRole("searchbox", { name: "Search settings" }));
  await user.type(screen.getByRole("searchbox", { name: "Search settings" }), "zzz");
  expect(screen.getByText("No settings match.")).toBeInTheDocument();
});

test("each type has its own control, with its default shown", async () => {
  api();
  open();
  expect(await screen.findByLabelText("The display name.")).toHaveValue("Lantern");
  expect(screen.getByLabelText("What demo.limit does")).toHaveValue("2");
  expect(screen.getByLabelText("What demo.on does")).toBeChecked();
  expect(screen.getByLabelText("What demo.mode does")).toHaveValue("person");
  expect(screen.getByLabelText("What demo.names does")).toHaveValue("a\nb");
  expect(screen.getByText("Default: Workspace")).toBeInTheDocument();
  expect(screen.getByText("Default: Yes")).toBeInTheDocument();
});

test("locked settings are disabled and say where they come from; others the screen can't change say which file", async () => {
  api();
  open();
  const env = await screen.findByLabelText("What demo.fixed does");
  expect(env).toBeDisabled();
  expect(screen.getByText("Set by an environment variable")).toBeInTheDocument();
  expect(screen.getByLabelText("What demo.flagged does")).toBeDisabled();
  expect(screen.getByText("Set by a flag")).toBeInTheDocument();
  const table = screen.getByText("What demo.table does").closest(".setting") as HTMLElement;
  expect(within(table).getByText("Changed in demo.yaml")).toBeInTheDocument();
  expect(within(table).queryByRole("textbox")).toBeNull();
  const server = screen.getByText("What demo.server does").closest(".setting") as HTMLElement;
  expect(within(server).getByText("local")).toBeInTheDocument();
  expect(within(server).getByText("Changed in demo.yaml")).toBeInTheDocument();
});

test("Save sends only what changed, with the fingerprint, then reads it back", async () => {
  const user = userEvent.setup();
  const calls = api(ITEMS, {
    "POST settings": () => ({
      changes: [{ key: "demo.title", before: "Lantern", after: "Harbor", was_default: false, is_default: false }],
      fingerprint: "fp-2",
      restarts: false,
    }),
  });
  open();
  const title = await screen.findByLabelText("The display name.");
  const save = screen.getByRole("button", { name: /Save/ });
  expect(save).toBeDisabled();
  await user.clear(title);
  await user.type(title, "Harbor");
  await user.click(save);
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect(posted(calls)[0]).toEqual({ changes: { "demo.title": "Harbor" }, reset: [], fingerprint: "fp-1" });
  expect(await screen.findByText("Saved. The display name.: Harbor")).toBeInTheDocument();
});

test("a number that isn't one is refused on screen before anything is sent", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  const limit = await screen.findByLabelText("What demo.limit does");
  await user.clear(limit);
  await user.type(limit, "lots");
  expect(screen.getByText("Enter a number.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Save/ })).toBeDisabled();
  expect(posted(calls)).toHaveLength(0);
});

test("Undo sends the old values back, with the fingerprint from the save", async () => {
  const user = userEvent.setup();
  let n = 0;
  const calls = api(ITEMS, {
    "POST settings": () => {
      n += 1;
      return n === 1
        ? {
            changes: [
              { key: "demo.title", before: "Lantern", after: "Harbor", was_default: false, is_default: false },
              { key: "demo.count", before: 4, after: 9, was_default: true, is_default: false },
            ],
            fingerprint: "fp-2",
            restarts: false,
          }
        : { changes: [], fingerprint: "fp-3", restarts: false };
    },
  });
  open();
  await user.type(await screen.findByLabelText("The display name."), "x");
  await user.click(screen.getByRole("button", { name: /Save/ }));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(posted(calls)).toHaveLength(2));
  expect(posted(calls)[1]).toEqual({ changes: { "demo.title": "Lantern" }, reset: ["demo.count"], fingerprint: "fp-2" });
  expect(await screen.findByText("Undone. It's back as it was.")).toBeInTheDocument();
});

test("Back to default is offered where the file sets the value, and sends a reset", async () => {
  const user = userEvent.setup();
  const calls = api(ITEMS, {
    "POST settings": () => ({
      changes: [{ key: "demo.title", before: "Lantern", after: "Workspace", was_default: false, is_default: true }],
      fingerprint: "fp-2",
      restarts: false,
    }),
  });
  open();
  await screen.findByLabelText("The display name.");
  expect(screen.getAllByRole("button", { name: /Back to default/ })).toHaveLength(1);
  await user.click(screen.getByRole("button", { name: "Back to default: The display name." }));
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect(posted(calls)[0]).toEqual({ changes: {}, reset: ["demo.title"], fingerprint: "fp-1" });
  expect(await screen.findByText(/back to the default, Workspace/)).toBeInTheDocument();
});

test("when the files changed since the form loaded, the server's words show and the form loads again", async () => {
  const user = userEvent.setup();
  const calls = api(ITEMS, { "POST settings": () => new Refuse(409, "The settings changed since you opened them. Look again, then save.") });
  open();
  await user.type(await screen.findByLabelText("The display name."), "x");
  const before = calls.filter((c) => c.route === "GET settings").length;
  await user.click(screen.getByRole("button", { name: /Save/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent("The settings changed since you opened them. Look again, then save.");
  await waitFor(() => expect(calls.filter((c) => c.route === "GET settings").length).toBeGreaterThan(before));
});

test("a refused value shows the server's words and keeps what was typed", async () => {
  const user = userEvent.setup();
  api(ITEMS, { "POST settings": () => new Refuse(400, "demo.title can't be empty here") });
  open();
  const title = await screen.findByLabelText("The display name.");
  await user.clear(title);
  await user.type(title, "Nope");
  await user.click(screen.getByRole("button", { name: /Save/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent("demo.title can't be empty here");
  expect(screen.getByLabelText("The display name.")).toHaveValue("Nope");
});

test("a list and a yes/no setting send their own kinds of value", async () => {
  const user = userEvent.setup();
  const calls = api();
  open();
  const names = await screen.findByLabelText("What demo.names does");
  await user.clear(names);
  await user.type(names, "one{Enter}two{Enter}{Enter}three");
  await user.click(screen.getByLabelText("What demo.on does"));
  await user.click(screen.getByRole("button", { name: /Save/ }));
  await waitFor(() => expect(posted(calls)).toHaveLength(1));
  expect(posted(calls)[0]).toMatchObject({ changes: { "demo.names": ["one", "two", "three"], "demo.on": false } });
});

test("a save that restarts the app says so in a live region until it is back", async () => {
  const user = userEvent.setup();
  api(ITEMS, {
    "POST settings": () => ({
      changes: [{ key: "demo.title", before: "Lantern", after: "Harborx", was_default: false, is_default: false }],
      fingerprint: "fp-2",
      restarts: true,
    }),
  });
  function Harness() {
    const [hellos, setHellos] = useState(1);
    return (
      <RestartProvider hellos={hellos}>
        <RestartNotice />
        <button type="button" onClick={() => setHellos(hellos + 1)}>
          reconnect
        </button>
        <Settings onOpenGuide={() => undefined} />
      </RestartProvider>
    );
  }
  renderApp(<Harness />);
  await user.type(await screen.findByLabelText("The display name."), "x");
  await user.click(screen.getByRole("button", { name: /Save/ }));
  const live = screen.getAllByRole("status").find((el) => el.classList.contains("restart-slot"))!;
  await waitFor(() => expect(live).toHaveTextContent("Restarting to use the new settings…"));
  await user.click(screen.getByRole("button", { name: "reconnect" }));
  await waitFor(() => expect(live).toBeEmptyDOMElement());
});
