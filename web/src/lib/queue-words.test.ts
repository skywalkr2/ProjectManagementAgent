import { heldAnswers, heldTitle, titleWords } from "./queue-words";
import sheet from "../wording/en.json";

// A title is "{kind} from {person} · {topic}" (design 7.14): with no topic it says so, and work the app started says what
// the work was, never a cut-off sentence and never just "Work <assistant> started".

const words = sheet as Record<string, string>;
const t = (key: string, vars: Record<string, string | number> = {}) =>
  (words[key] ?? key).replace(/\{(\w+)\}/g, (_, name: string) => String(name === "assistant" ? "Helper" : (vars[name] ?? "")));
const has = (key: string) => key in words;
const base = { person: null, person_name: null, sender: null, topic: "" } as const;

test("a title with a topic reads 'kind from person · topic'", () => {
  expect(titleWords({ ...base, kind: "email", person_name: "Pat Example", topic: "Reading venue" }, t, has)).toBe("Email from Pat Example · Reading venue");
});

test("a title with no topic says the topic is missing instead of using a piece of the input's first sentence", () => {
  expect(titleWords({ ...base, kind: "email", person_name: "Pat Example" }, t, has)).toBe("Email from Pat Example");
  expect(titleWords({ ...base, kind: "pasted" }, t, has)).toBe("Your pasted notes");
});

test("work the app started is named by its kind of task and what it is about", () => {
  expect(titleWords({ ...base, kind: "task", task: "notes", subject: "Launch reading" }, t, has)).toBe("Filing notes · Launch reading");
});

test("the follow-on after a move is titled by what happened to the item, never by the name of the run", () => {
  const title = titleWords({ ...base, kind: "task", task: "follow-on", subject: "Print sync" }, t, has);
  expect(title).toBe("After 'Print sync' moved");
  expect(title).not.toMatch(/checking|follow-on/i);
  // With no subject there is nothing to say moved, so it falls back to the kind of work.
  expect(titleWords({ ...base, kind: "task", task: "follow-on" }, t, has)).toBe("Checking what a move changes");
});

test("a kind of task the sheet doesn't name reads as the assistant's work, with its subject", () => {
  expect(titleWords({ ...base, kind: "task", task: "some-plugin/draft", subject: "Chapter 3" }, t, has)).toBe("Helper's work · Chapter 3");
});

test("work with no known kind or subject still says whose work it is", () => {
  expect(titleWords({ ...base, kind: "task" }, t, has)).toBe("Work Helper started");
  expect(titleWords({ ...base, kind: "task", task: "notes" }, t, has)).toBe("Filing notes");
});

test("a held guess at how long a to-do takes is a question with the length in words and answers that name it", () => {
  const held = { ask: "effort", item: "Write the report", value: "90", from_value: null } as const;
  expect(heldTitle(held, t)).toBe("Keep 'Write the report' as taking about 1 hour 30 minutes?");
  expect(heldAnswers(held, t)).toEqual({ primary: "Keep 1 hour 30 minutes", other: "Keep it as it is" });
  expect(heldAnswers({ ...held, from_value: "45" }, t).other).toBe("Keep it at 45 minutes");
});

test("a held reminder for a dated item is a question naming the day, with answers that name the moment or no reminder", () => {
  const held = { ask: "remind", item: "The plan renews", value: "2026-12-01T09:00:00+00:00", from_value: null, day: "2026-12-15" } as const;
  expect(heldTitle(held, t)).toMatch(/^Remind you about 'The plan renews' before .*15\?$/);
  const answers = heldAnswers(held, t);
  expect(answers.primary).toMatch(/^Remind me .*9:00/);
  expect(answers.other).toBe("No reminder");
  expect(heldAnswers({ ...held, from_value: "2026-12-05T09:00:00+00:00" }, t).other).toMatch(/^Keep the reminder at .*9:00/);
});

test("a voice note waiting to be turned into text is titled by the file it is about", () => {
  expect(titleWords({ ...base, kind: "task", task: "transcribe", subject: "walk.m4a" }, t, has)).toBe("Turn the voice note 'walk.m4a' into text");
  expect(titleWords({ ...base, kind: "task", task: "transcribe" }, t, has)).toBe("Turning a voice note into text");
});
