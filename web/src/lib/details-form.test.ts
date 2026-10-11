import { buildDetails, detailFields, initialValue } from "./details-form";

test("a schema with no properties asks for nothing", () => {
  expect(detailFields({ type: "object" })).toEqual([]);
});

test("references, single-item allOf and optional unions are followed to the field's own shape", () => {
  const fields = detailFields({
    type: "object",
    $defs: { Mode: { enum: [1, 2], type: "integer" } },
    properties: {
      a: { $ref: "#/$defs/Mode", default: 2 },
      b: { allOf: [{ $ref: "#/$defs/Mode" }], title: "B pick" },
      c: { anyOf: [{ type: "integer" }, { type: "null" }] },
      d: { type: ["boolean", "null"] },
    },
  })!;
  expect(fields.map((f) => [f.key, f.type, f.label])).toEqual([
    ["a", "choice", "A"],
    ["b", "choice", "B pick"],
    ["c", "integer", "C"],
    ["d", "boolean", "D"],
  ]);
  expect(initialValue(fields[0])).toBe("2");
  expect(buildDetails(fields, { a: "1", c: "7" })).toEqual({ meta: { a: 1, c: 7 } });
});

test("shapes the form can't ask for make the whole kind unsupported", () => {
  expect(detailFields({ type: "object", properties: { x: { type: "array", items: { type: "string" } } } })).toBeNull();
  expect(detailFields({ type: "object", properties: { x: { anyOf: [{ type: "string" }, { type: "integer" }] } } })).toBeNull();
  expect(detailFields({ type: "object", properties: { x: { $ref: "#/$defs/Missing" } } })).toBeNull();
  expect(detailFields({ type: "string" })).toBeNull();
});

test("empty optional fields are left out, required ones are named, and numbers must be numbers", () => {
  const fields = detailFields({
    type: "object",
    required: ["name", "count"],
    properties: { name: { type: "string" }, count: { type: "integer" }, note: { type: "string" } },
  })!;
  expect(buildDetails(fields, { count: "3" })).toEqual({ missing: "Name" });
  expect(buildDetails(fields, { name: "x", count: "3.5" })).toEqual({ missing: "Count" });
  expect(buildDetails(fields, { name: "x", count: "3" })).toEqual({ meta: { name: "x", count: 3 } });
  expect(buildDetails(fields, { name: "x", count: "3", note: "y" })).toEqual({ meta: { name: "x", count: 3, note: "y" } });
});
