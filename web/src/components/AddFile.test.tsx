import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { S } from "../lib/api";
import { Refuse, fakeApi, renderApp } from "../test-utils";
import { AddFile } from "./AddFile";

const attachment: S["FileKindView"] = {
  name: "attachment",
  label: "Attachment",
  accept: ["text/plain", "application/pdf", "image/png"],
  max_mb: 1,
  details_schema: {
    type: "object",
    properties: { description: { type: "string", title: "Description", default: "" } },
  },
};

const report: S["FileKindView"] = {
  name: "demo/report",
  label: "Report",
  accept: ["text/plain"],
  max_mb: 2.5,
  details_schema: {
    type: "object",
    required: ["title"],
    $defs: { Status: { enum: ["draft", "final"], type: "string", title: "Status" } },
    properties: {
      title: { type: "string", title: "Title", maxLength: 20, description: "A short name." },
      pages: { type: "integer", title: "Pages", minimum: 1, maximum: 99 },
      score: { type: "number", title: "Score" },
      final: { type: "boolean", title: "Final copy", default: false },
      status: { $ref: "#/$defs/Status", default: "draft" },
      tag: { anyOf: [{ type: "string" }, { type: "null" }], title: "Tag", default: null },
      colour: { enum: ["red", "blue"], title: "Colour" },
    },
  },
};

const odd: S["FileKindView"] = {
  name: "demo/odd",
  label: "Odd",
  accept: ["text/plain"],
  max_mb: 1,
  details_schema: { type: "object", properties: { items: { type: "array", items: { type: "string" } } } },
};

const project = { id: "P-1", name: "Harbor project" } as S["ProjectView"];

function routes(extra: Record<string, (body: unknown) => unknown> = {}) {
  return { "GET file-kinds": () => [attachment, report, odd], "GET projects": () => [project], ...extra };
}

const text = (name = "hello.txt", body = "hello") => new File([body], name, { type: "text/plain" });
const fileInput = () => screen.getByLabelText("File") as HTMLInputElement;

test("the kind defaults to attachment, says what it accepts in words, and narrows the file picker", async () => {
  fakeApi(routes());
  renderApp(<AddFile onClose={() => undefined} />);
  const kind = (await screen.findByRole("combobox", { name: "What it's for" })) as HTMLSelectElement;
  expect(kind).toHaveValue("attachment");
  expect(within(kind).getAllByRole("option").map((o) => o.textContent)).toEqual(["Attachment", "Report", "Odd"]);
  expect(kind).toHaveAccessibleDescription("Accepts plain text, PDF documents and PNG images. Up to 1 MB.");
  expect(fileInput()).toHaveAttribute("accept", "text/plain,application/pdf,image/png");
  const user = userEvent.setup();
  await user.selectOptions(kind, "demo/report");
  expect(kind).toHaveAccessibleDescription("Accepts plain text. Up to 2.5 MB.");
  expect(fileInput()).toHaveAttribute("accept", "text/plain");
});

test("the details form is made from the kind's schema: each supported field type, optional or required", async () => {
  const user = userEvent.setup();
  fakeApi(routes());
  renderApp(<AddFile onClose={() => undefined} />);
  await user.selectOptions(await screen.findByRole("combobox", { name: "What it's for" }), "demo/report");
  const details = screen.getByRole("group", { name: "About this file" });
  const title = within(details).getByRole("textbox", { name: "Title" });
  expect(title).toHaveAttribute("maxlength", "20");
  expect(title).toBeRequired();
  expect(title).toHaveAccessibleDescription("A short name.");
  const pages = within(details).getByRole("spinbutton", { name: /Pages/ });
  expect(pages).toHaveAttribute("min", "1");
  expect(pages).toHaveAttribute("max", "99");
  expect(pages).toHaveAttribute("step", "1");
  expect(within(details).getByRole("spinbutton", { name: /Score/ })).toHaveAttribute("step", "any");
  expect(within(details).getByRole("checkbox", { name: "Final copy" })).not.toBeChecked();
  const status = within(details).getByRole("combobox", { name: /Status/ });
  expect(status).toHaveValue("draft");
  expect(within(status).getAllByRole("option").map((o) => o.textContent)).toEqual(["Not chosen", "draft", "final"]);
  expect(within(details).getByRole("textbox", { name: /Tag/ })).toBeInTheDocument();
  expect(within(details).getByRole("combobox", { name: /Colour/ })).toHaveValue("");
  expect(screen.queryByText(/can't ask for yet/)).toBeNull();
});

test("what is typed goes with the file as the kind's details", async () => {
  const user = userEvent.setup();
  const onClose = vi.fn();
  const meta = { title: "Harbor notes", pages: 12, score: 4.5, final: true, status: "final" };
  const route = `POST files?${new URLSearchParams({ name: "hello.txt", kind: "demo/report", project: "P-1", meta: JSON.stringify(meta) })}`;
  const calls = fakeApi(routes({ [route]: () => ({ id: "FILE-1", name: "hello.txt" }) }));
  renderApp(<AddFile onClose={onClose} />);
  await user.selectOptions(await screen.findByRole("combobox", { name: "What it's for" }), "demo/report");
  await user.selectOptions(screen.getByRole("combobox", { name: /Project/ }), "P-1");
  await user.upload(fileInput(), text());
  await user.type(screen.getByRole("textbox", { name: "Title" }), "Harbor notes");
  await user.type(screen.getByRole("spinbutton", { name: /Pages/ }), "12");
  await user.type(screen.getByRole("spinbutton", { name: /Score/ }), "4.5");
  await user.click(screen.getByRole("checkbox", { name: "Final copy" }));
  await user.selectOptions(screen.getByRole("combobox", { name: /Status/ }), "final");
  await user.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(onClose).toHaveBeenCalled());
  expect(calls.map((c) => c.route)).toContain(route);
  expect(await screen.findByText("Added hello.txt.")).toBeInTheDocument();
});

test("the file is sent as the body with its own type, so the server can check both", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(routes({ "POST files?name=hello.txt&kind=attachment": () => ({ id: "FILE-1", name: "hello.txt" }) }));
  renderApp(<AddFile onClose={() => undefined} />);
  await screen.findByRole("combobox", { name: "What it's for" });
  const file = text();
  await user.upload(fileInput(), file);
  await user.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(calls.some((c) => c.route.startsWith("POST files"))).toBe(true));
  const sent = calls.find((c) => c.route.startsWith("POST files"))!;
  expect(sent.route).toBe("POST files?name=hello.txt&kind=attachment");
  expect(sent.body).toBe(file);
  expect(sent.headers).toEqual({ "content-type": "text/plain" });
});

test("a kind whose details this screen can't ask for says so, and Add stays off", async () => {
  const user = userEvent.setup();
  fakeApi(routes());
  renderApp(<AddFile onClose={() => undefined} />);
  await user.selectOptions(await screen.findByRole("combobox", { name: "What it's for" }), "demo/odd");
  await user.upload(fileInput(), text());
  expect(screen.getByText("This kind of file needs details this screen can't ask for yet.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
});

test("a file that is too big or the wrong type is turned away before sending, in words", async () => {
  const user = userEvent.setup({ applyAccept: false });
  const calls = fakeApi(routes());
  renderApp(<AddFile onClose={() => undefined} />);
  await screen.findByRole("combobox", { name: "What it's for" });
  await user.upload(fileInput(), new File([new Uint8Array(1024 * 1024 + 1)], "big.txt", { type: "text/plain" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("big.txt is larger than 1 MB.");
  expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
  await user.upload(fileInput(), new File(["x"], "page.html", { type: "text/html" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Files of type text/html can't be added as this kind of file.");
  expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
  expect(calls.some((c) => c.route.startsWith("POST files"))).toBe(false);
});

test("a required detail left empty is named, and nothing is sent", async () => {
  const user = userEvent.setup();
  const calls = fakeApi(routes());
  renderApp(<AddFile onClose={() => undefined} />);
  await user.selectOptions(await screen.findByRole("combobox", { name: "What it's for" }), "demo/report");
  await user.upload(fileInput(), text());
  await user.click(screen.getByRole("button", { name: "Add" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Title is needed.");
  expect(calls.some((c) => c.route.startsWith("POST files"))).toBe(false);
});

test("the server's refusal is shown as it says it, and the dialog stays open", async () => {
  const user = userEvent.setup();
  const onClose = vi.fn();
  fakeApi(routes({ "POST files?name=hello.txt&kind=attachment": () => new Refuse(409, "adding hello.txt would go over the 2000 MB limit for all files") }));
  renderApp(<AddFile onClose={onClose} />);
  await screen.findByRole("combobox", { name: "What it's for" });
  await user.upload(fileInput(), text());
  await user.click(screen.getByRole("button", { name: "Add" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("adding hello.txt would go over the 2000 MB limit for all files");
  expect(onClose).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Add" })).toBeEnabled();
});

test("Escape closes the dialog", async () => {
  const user = userEvent.setup();
  const onClose = vi.fn();
  fakeApi(routes());
  renderApp(<AddFile onClose={onClose} />);
  await screen.findByRole("dialog", { name: "Add a file" });
  await user.keyboard("{Escape}");
  expect(onClose).toHaveBeenCalled();
});
