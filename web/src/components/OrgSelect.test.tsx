import "@testing-library/jest-dom/vitest";
import { useState } from "react";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { OrgSelect } from "./OrgSelect";

const org = (id: string, name: string): S["OrganizationView"] => ({ id, name, aliases: [], notes: null, people: 0 });
const one = org("ORG-1", "Org one");
const two = org("ORG-2", "Org two");

function Harness(props: { start?: string }) {
  const [value, setValue] = useState(props.start ?? "");
  return (
    <form>
      <OrgSelect label="Organization" value={value} onChange={setValue} />
      <output aria-label="chosen">{value}</output>
    </form>
  );
}

const names = (box: HTMLElement) => within(box).getAllByRole("option").map((o) => o.textContent);

test("it lists organizations by name, with Not set first and the add choice last, and selects the held one", async () => {
  fakeApi({ "GET organizations": () => [two, one] });
  renderApp(<Harness start="ORG-2" />);
  const select = await screen.findByRole("combobox", { name: "Organization" });
  await waitFor(() => expect(names(select)).toEqual(["Not set", "Org one", "Org two", "Add an organization…"]));
  expect(select).toHaveValue("ORG-2");
});

test("adding an organization posts its name, then selects it", async () => {
  const user = userEvent.setup();
  let made = false;
  const calls = fakeApi({
    "GET organizations": () => (made ? [one, org("ORG-9", "Org nine")] : [one]),
    "POST organizations": () => {
      made = true;
      return { id: "ORG-9" };
    },
  });
  renderApp(<Harness />);
  const select = await screen.findByRole("combobox", { name: "Organization" });
  await waitFor(() => expect(names(select)).toContain("Org one"));
  await user.selectOptions(select, "Add an organization…");
  await user.type(screen.getByRole("textbox", { name: "Name of the new organization" }), "Org nine");
  await user.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(screen.getByLabelText("chosen")).toHaveTextContent("ORG-9"));
  expect(calls.find((c) => c.route === "POST organizations")!.body).toEqual({ name: "Org nine" });
  expect(screen.getByRole("combobox", { name: "Organization" })).toHaveValue("ORG-9");
});

test("a name already on file selects that organization instead of adding another", async () => {
  const user = userEvent.setup();
  const calls = fakeApi({ "GET organizations": () => [one] });
  renderApp(<Harness />);
  const select = await screen.findByRole("combobox", { name: "Organization" });
  await waitFor(() => expect(names(select)).toContain("Org one"));
  await user.selectOptions(select, "Add an organization…");
  await user.type(screen.getByRole("textbox", { name: "Name of the new organization" }), "org ONE{Enter}");
  await waitFor(() => expect(screen.getByLabelText("chosen")).toHaveTextContent("ORG-1"));
  expect(calls.some((c) => c.route === "POST organizations")).toBe(false);
});

test("a refused add keeps the field open and selects nothing", async () => {
  const user = userEvent.setup();
  fakeApi({ "GET organizations": () => [one], "POST organizations": () => new Refuse(409, "That name is taken.") });
  renderApp(<Harness />);
  const select = await screen.findByRole("combobox", { name: "Organization" });
  await waitFor(() => expect(names(select)).toContain("Org one"));
  await user.selectOptions(select, "Add an organization…");
  await user.type(screen.getByRole("textbox", { name: "Name of the new organization" }), "Taken{Enter}");
  expect(await screen.findByText(/That name is taken\./)).toBeInTheDocument();
  expect(screen.getByLabelText("chosen")).toHaveTextContent("");
  expect(screen.getByRole("textbox", { name: "Name of the new organization" })).toBeInTheDocument();
});
