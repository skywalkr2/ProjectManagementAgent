import type { S } from "./api";
import { narrowedWithout, reachChoices } from "./reach";

const narrow: S["Scope"] = { task_kinds: ["notes"], projects: ["PRJ-1"], scope: "projects" };

test("the narrowest reach comes first and each wider one is a pick, never a duplicate", () => {
  const found = reachChoices({ ...narrow });
  expect(found.map((c) => c.id)).toEqual(["proposed", "all-projects", "all-work", "everywhere"]);
  expect(found[0].scope).toEqual(narrow);
  expect(found[1].scope).toMatchObject({ task_kinds: ["notes"], scope: "workspace", projects: [] });
  expect(found[2].scope).toMatchObject({ task_kinds: [], scope: "projects", projects: ["PRJ-1"] });
  expect(found[3].scope).toMatchObject({ task_kinds: [], scope: "workspace", projects: [] });
});

test("a target that is already everywhere has nothing wider to offer", () => {
  expect(reachChoices({ scope: "workspace" }).map((c) => c.id)).toEqual(["proposed"]);
  expect(reachChoices({ scope: "workspace", task_kinds: ["notes"] }).map((c) => c.id)).toEqual(["proposed", "all-work"]);
});

test("widening keeps the people a target is about", () => {
  const found = reachChoices({ ...narrow, people: ["PER-1"] });
  expect(found.every((c) => c.scope.people?.[0] === "PER-1")).toBe(true);
});

test("leaving a project out of a list of projects removes it, and of the workspace adds an exception", () => {
  expect(narrowedWithout({ scope: "projects", projects: ["PRJ-1", "PRJ-2"] }, "PRJ-1")).toEqual({ scope: "projects", projects: ["PRJ-2"] });
  expect(narrowedWithout({ scope: "workspace" }, "PRJ-1")).toEqual({ scope: "workspace", except: ["PRJ-1"] });
});

test("a leave-out that changes nothing or leaves no project is refused", () => {
  expect(narrowedWithout({ scope: "projects", projects: ["PRJ-1"] }, "PRJ-1")).toBeNull();
  expect(narrowedWithout({ scope: "projects", projects: ["PRJ-1", "PRJ-2"] }, "PRJ-9")).toBeNull();
  expect(narrowedWithout({ scope: "workspace", except: ["PRJ-1"] }, "PRJ-1")).toBeNull();
});
