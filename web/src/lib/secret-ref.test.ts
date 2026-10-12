import { asReference } from "./secret-ref";

test("a bare name is taken as the name of a variable in the app's environment", () => {
  expect(asReference("  MODEL_KEY ")).toBe("env:MODEL_KEY");
});

test("a reference that already says where it points goes as it is", () => {
  expect(asReference("env:MODEL_KEY")).toBe("env:MODEL_KEY");
  expect(asReference("file:/run/keys/model")).toBe("file:/run/keys/model");
});

test("nothing typed stays empty", () => {
  expect(asReference("   ")).toBe("");
});
