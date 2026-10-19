import "@testing-library/jest-dom/vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { person, project } from "../lib/records-fixtures";
import { fakeApi, renderApp, type Routes } from "../test-utils";
import { RecordPage } from "./RecordPage";

// Who a person is to the user (design 6.34): a list on the person's page, saved at once as the user's own edit.

const page: S["RecordPageView"] = {
  kind: "person",
  id: "PER-2",
  version: 3,
  name: "Robin Sample",
  details: [],
  open_actions: [],
  open_questions: [],
  completed_actions: [],
  fact_source: null,
  activity: [],
};

const setting = (value: string): S["SettingItem"] =>
  ({ key: "steward.default_stance", file: "steward", group: "steward", description: "", type: "choice", options: ["manage", "alongside", "report_to", "watch"], value, default: "alongside", source: "default", locked: false, basic: false, editable: true }) as S["SettingItem"];

function open(fields: Record<string, unknown>, extra: Routes = {}, defaultStance = "alongside") {
  return fakeApi({
    "GET record?kind=person&id=PER-2": () => ({ kind: "person", id: "PER-2", version: 3, fields: { id: "PER-2", full_name: "Robin Sample", ...fields }, long_text: [] }),
    "GET kinds/person": () => ({ kind: "person", fields: [] }),
    "GET record-pages/PER-2?kind=person": () => page,
    "GET people": () => [person("PER-2", "Robin Sample")],
    "GET projects": () => [project("PRJ-1", "Harbor")],
    "GET settings": () => ({ fingerprint: "fp", items: [setting(defaultStance)] }),
    "GET lists": () => [],
    "GET organizations": () => [],
    "GET plugin-actions?kind=person&id=PER-2": () => [],
    "GET task-kinds?kind=person&id=PER-2": () => [],
    ...extra,
  });
}

test("the person's page has a list of who they are to you, with the default said in words, and no raw value", async () => {
  open({ stance: "report_to" });
  renderApp(<RecordPage kind="person" id="PER-2" onBack={() => {}} />);
  const list = await screen.findByRole("combobox", { name: "Who they are to you" });
  expect(list).toHaveValue("report_to");
  const options = within(list).getAllByRole("option").map((o) => o.textContent);
  expect(options).toEqual(["Use my default (I work alongside them)", "I manage them", "I work alongside them", "I report to them", "I only watch them"]);
  expect(screen.queryByText("report_to")).toBeNull();
});

test("someone with no stance shows the default, and one marked as only tracked shows watching as the default", async () => {
  open({}, {}, "manage");
  const first = renderApp(<RecordPage kind="person" id="PER-2" onBack={() => {}} />);
  const list = await screen.findByRole("combobox", { name: "Who they are to you" });
  expect(list).toHaveValue("");
  await waitFor(() => expect(within(list).getAllByRole("option")[0]).toHaveTextContent("Use my default (I manage them)"));
  first.unmount();
  open({ track_only: true }, {}, "manage");
  renderApp(<RecordPage kind="person" id="PER-2" onBack={() => {}} />);
  const marked = await screen.findByRole("combobox", { name: "Who they are to you" });
  expect(within(marked).getAllByRole("option")[0]).toHaveTextContent("Use my default (I only watch them)");
});

test("picking one saves at once as the person's own edit with Undo, and Use my default clears it", async () => {
  const user = userEvent.setup();
  const calls = open({ stance: "watch" }, { "POST records/edit": () => ({ changeset: "CS-9" }), "POST changesets/CS-9/undo": () => ({ restored: [0], skipped: [] }) });
  renderApp(<RecordPage kind="person" id="PER-2" onBack={() => {}} />);
  const list = await screen.findByRole("combobox", { name: "Who they are to you" });
  await user.selectOptions(list, "I manage them");
  await waitFor(() => expect(calls.find((c) => c.route === "POST records/edit")?.body).toEqual({ kind: "person", id: "PER-2", fields: { stance: "manage" }, read_version: 3 }));
  await user.click(await screen.findByRole("button", { name: "Undo" }));
  await waitFor(() => expect(calls.some((c) => c.route === "POST changesets/CS-9/undo")).toBe(true));
  await user.selectOptions(list, "Use my default (I work alongside them)");
  await waitFor(() => expect(calls.filter((c) => c.route === "POST records/edit").at(-1)?.body).toEqual({ kind: "person", id: "PER-2", fields: { stance: null }, read_version: 3 }));
});

test("a page for anything but a person has no such list", async () => {
  fakeApi({
    "GET record?kind=project&id=PRJ-1": () => ({ kind: "project", id: "PRJ-1", version: 1, fields: { id: "PRJ-1", name: "Harbor" }, long_text: [] }),
    "GET kinds/project": () => ({ kind: "project", fields: [] }),
    "GET record-pages/PRJ-1?kind=project": () => ({ ...page, kind: "project", id: "PRJ-1", name: "Harbor" }),
    "GET people": () => [],
    "GET projects": () => [project("PRJ-1", "Harbor")],
    "GET settings": () => ({ fingerprint: "fp", items: [] }),
    "GET lists": () => [],
    "GET organizations": () => [],
    "GET plugin-actions?kind=project&id=PRJ-1": () => [],
    "GET task-kinds?kind=project&id=PRJ-1": () => [],
  });
  renderApp(<RecordPage kind="project" id="PRJ-1" onBack={() => {}} />);
  await screen.findByRole("heading", { level: 1, name: "Harbor" });
  expect(screen.queryByRole("combobox", { name: "Who they are to you" })).toBeNull();
});
