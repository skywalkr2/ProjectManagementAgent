import type { S } from "./api";
import { changedFields, editableFields, initialDraft } from "./record-edit";

const f = (name: string, extra: Partial<S["FieldView"]> = {}): S["FieldView"] => ({
  name,
  description: "",
  type: "text",
  required: false,
  editable: true,
  options: [],
  ...extra,
});

const fields = [
  f("id", { editable: false }),
  f("title", { required: true }),
  f("pages", { type: "number" }),
  f("done", { type: "yes_no" }),
  f("due", { type: "date" }),
  f("state", { type: "choice", options: ["open", "closed"] }),
  f("owner", { type: "reference", refers_to: "person" }),
  f("parent", { type: "reference", refers_to: "demo/other" }),
  f("tags", { type: "list" }),
  f("body", { type: "long_text" }),
  f("blob", { type: "other" }),
];

test("the form offers editable fields of a shape it can show, and references it can pick from", () => {
  expect(editableFields(fields).map((x) => x.name)).toEqual(["title", "pages", "done", "due", "state", "owner", "tags"]);
});

test("only changed fields are sent, and an emptied field is cleared", () => {
  const offered = editableFields(fields);
  const values = { title: "Old", pages: 12, done: false, due: "2026-11-01", state: "open", owner: "P-1", tags: ["a", "b"] };
  const draft = initialDraft(offered, values);
  expect(draft.tags).toBe("a\nb");
  expect(changedFields(offered, values, draft)).toEqual({});
  expect(changedFields(offered, values, { ...draft, title: "New", pages: "", due: "", owner: "", done: true, tags: "a\n\n c " })).toEqual({
    title: "New",
    pages: null,
    due: null,
    owner: null,
    done: true,
    tags: ["a", "c"],
  });
});

test("a field the record has no value for is unchanged until something is entered", () => {
  const offered = editableFields(fields);
  const draft = initialDraft(offered, {});
  expect(changedFields(offered, {}, draft)).toEqual({});
  expect(changedFields(offered, {}, { ...draft, pages: "3", state: "closed" })).toEqual({ pages: 3, state: "closed" });
});
