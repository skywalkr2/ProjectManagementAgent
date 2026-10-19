import "@testing-library/jest-dom/vitest";
import { useState } from "react";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp, type Routes } from "../test-utils";
import { ValueSelect } from "./ValueSelect";

const LIST = "demo-state";

function list(extra: Partial<S["ValueListView"]> = {}): S["ValueListView"] {
  return { id: "L-1", name: LIST, label: "Demo state", values: ["Open", "Waiting"], retired: ["Closed"], used_by: [], ...extra };
}

/** The select inside a form, as the screens use it; the form records whether it was sent. */
function Harness(props: { start?: string; required?: boolean; onSubmit?: () => void }) {
  const [value, setValue] = useState(props.start ?? "");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        props.onSubmit?.();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") document.body.dataset.closed = "yes";
      }}
    >
      <ValueSelect list={LIST} label="State" value={value} onChange={setValue} required={props.required} />
      <output aria-label="chosen">{value}</output>
    </form>
  );
}

function routes(extra: Routes = {}): Routes {
  return { "GET lists": () => [list()], ...extra };
}

const options = (box: HTMLElement) => within(box).getAllByRole("option").map((o) => o.textContent);

afterEach(() => {
  delete document.body.dataset.closed;
});

test("it offers the list's values in order, with Not set first and the add choice last", async () => {
  fakeApi(routes());
  renderApp(<Harness start="Waiting" />);
  const select = await screen.findByRole("combobox", { name: "State" });
  await waitFor(() => expect(options(select)).toEqual(["Not set", "Open", "Waiting", "Add to the list…"]));
  expect(select).toHaveValue("Waiting");
});

test("a value the record holds but the list dropped stays, marked as no longer offered", async () => {
  fakeApi(routes());
  renderApp(<Harness start="Closed" />);
  const select = await screen.findByRole("combobox", { name: "State" });
  await waitFor(() => expect(options(select)).toContain("Closed (no longer offered)"));
  expect(select).toHaveValue("Closed");
  expect(options(select)).toEqual(["Not set", "Open", "Waiting", "Closed (no longer offered)", "Add to the list…"]);
});

test("a held value is shown plainly while the lists load, and when they don't load there is no way to add", async () => {
  fakeApi({ "GET lists": () => new Refuse(500, "") });
  renderApp(<Harness start="Closed" />);
  const select = await screen.findByRole("combobox", { name: "State" });
  await waitFor(() => expect(options(select)).toEqual(["Not set", "Closed"]));
  expect(select).toHaveValue("Closed");
});

test("choosing Not set clears the value", async () => {
  const user = userEvent.setup();
  fakeApi(routes());
  renderApp(<Harness start="Open" />);
  const select = await screen.findByRole("combobox", { name: "State" });
  await user.selectOptions(select, "Not set");
  expect(screen.getByLabelText("chosen")).toHaveTextContent("");
});

test("Add to the list opens a field; Add sends the value, selects it and offers Undo", async () => {
  const user = userEvent.setup();
  let values = ["Open", "Waiting"];
  const calls = fakeApi(
    routes({
      "GET lists": () => [list({ values })],
      "POST lists/demo-state/add": (body) => {
        values = [...values, (body as { value: string }).value];
        return { changeset: "CS-1" };
      },
      "POST changesets/CS-1/undo": () => ({ restored: [{ kind: "value_list", id: "L-1" }], skipped: [] }),
    }),
  );
  renderApp(<Harness />);
  const select = await screen.findByRole("combobox", { name: "State" });
  await waitFor(() => expect(options(select)).toContain("Add to the list…"));
  await user.selectOptions(select, "Add to the list…");
  const field = screen.getByRole("textbox", { name: "Add a choice to Demo state" });
  expect(field).toHaveFocus();
  expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
  await user.type(field, "  Parked ");
  await user.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(screen.getByLabelText("chosen")).toHaveTextContent("Parked"));
  expect(calls.find((c) => c.route === "POST lists/demo-state/add")?.body).toEqual({ value: "Parked" });
  expect(screen.queryByRole("textbox", { name: "Add a choice to Demo state" })).toBeNull();
  await waitFor(() => expect(options(screen.getByRole("combobox", { name: "State" }))).toContain("Parked"));
  expect(screen.getByRole("combobox", { name: "State" })).toHaveValue("Parked");
  expect(await screen.findByText("Added Parked to Demo state.")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.map((c) => c.route)).toContain("POST changesets/CS-1/undo"));
});

test("Enter in the field adds without sending the form around it", async () => {
  const user = userEvent.setup();
  const sent = vi.fn();
  const calls = fakeApi(routes({ "POST lists/demo-state/add": () => ({ changeset: "CS-2" }) }));
  renderApp(<Harness onSubmit={sent} />);
  const select = await screen.findByRole("combobox", { name: "State" });
  await waitFor(() => expect(options(select)).toContain("Add to the list…"));
  await user.selectOptions(select, "Add to the list…");
  await user.type(screen.getByRole("textbox", { name: "Add a choice to Demo state" }), "Parked{Enter}");
  await waitFor(() => expect(screen.getByLabelText("chosen")).toHaveTextContent("Parked"));
  expect(calls.some((c) => c.route === "POST lists/demo-state/add")).toBe(true);
  expect(sent).not.toHaveBeenCalled();
});

test("Escape cancels the field and does not reach the form, and nothing is sent", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(routes());
  renderApp(<Harness start="Open" />);
  const select = await screen.findByRole("combobox", { name: "State" });
  await waitFor(() => expect(options(select)).toContain("Add to the list…"));
  await user.selectOptions(select, "Add to the list…");
  await user.type(screen.getByRole("textbox", { name: "Add a choice to Demo state" }), "Parked{Escape}");
  expect(screen.queryByRole("textbox", { name: "Add a choice to Demo state" })).toBeNull();
  expect(document.body.dataset.closed).toBeUndefined();
  expect(screen.getByLabelText("chosen")).toHaveTextContent("Open");
  await waitFor(() => expect(screen.getByRole("combobox", { name: "State" })).toHaveFocus());
  expect(calls.some((c) => c.route.startsWith("POST"))).toBe(false);
});

test("a value the list already offers is selected without asking the server", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(routes());
  renderApp(<Harness />);
  const select = await screen.findByRole("combobox", { name: "State" });
  await waitFor(() => expect(options(select)).toContain("Add to the list…"));
  await user.selectOptions(select, "Add to the list…");
  await user.type(screen.getByRole("textbox", { name: "Add a choice to Demo state" }), "waiting{Enter}");
  await waitFor(() => expect(screen.getByLabelText("chosen")).toHaveTextContent("Waiting"));
  expect(calls.some((c) => c.route.startsWith("POST"))).toBe(false);
});

test("a refusal shows in an alert, keeps the field open with what was typed, and selects nothing", async () => {
  const user = userEvent.setup();
  fakeApi(routes({ "POST lists/demo-state/add": () => new Refuse(422, "That value is not allowed here.") }));
  renderApp(<Harness start="Open" />);
  const select = await screen.findByRole("combobox", { name: "State" });
  await waitFor(() => expect(options(select)).toContain("Add to the list…"));
  await user.selectOptions(select, "Add to the list…");
  await user.type(screen.getByRole("textbox", { name: "Add a choice to Demo state" }), "Bad");
  await user.click(screen.getByRole("button", { name: "Add" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("That value is not allowed here.");
  expect(screen.getByRole("textbox", { name: "Add a choice to Demo state" })).toHaveValue("Bad");
  expect(screen.getByLabelText("chosen")).toHaveTextContent("Open");
});

test("a required choice has no Not set", async () => {
  fakeApi(routes());
  renderApp(<Harness start="Open" required />);
  const select = await screen.findByRole("combobox", { name: "State" });
  await waitFor(() => expect(options(select)).toEqual(["Open", "Waiting", "Add to the list…"]));
  expect(select).toBeRequired();
});
