import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { hasSeenMessage, markMessageSeen, messageHash } from "./seen-messages";

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.restoreAllMocks());

test("a message is seen only as the exact words, for the person it is to", () => {
  expect(hasSeenMessage("PER-1", "Hi,\n\nOne question")).toBe(false);
  markMessageSeen("PER-1", "Hi,\n\nOne question");
  expect(hasSeenMessage("PER-1", "Hi,\n\nOne question")).toBe(true);
  expect(hasSeenMessage("PER-1", "Hi,\n\nOne question.")).toBe(false);
  expect(hasSeenMessage("PER-2", "Hi,\n\nOne question")).toBe(false);
  expect(messageHash("a")).not.toBe(messageHash("b"));
  expect(messageHash("same")).toBe(messageHash("same"));
});

test("an empty message is never seen, and only the most recent few hundred are kept", () => {
  markMessageSeen("PER-1", "  ");
  expect(hasSeenMessage("PER-1", "  ")).toBe(false);
  for (let i = 0; i < 320; i++) markMessageSeen("PER-1", `message ${i}`);
  expect(hasSeenMessage("PER-1", "message 0")).toBe(false);
  expect(hasSeenMessage("PER-1", "message 319")).toBe(true);
});

test("with storage blocked or holding junk nothing is seen and nothing throws", () => {
  window.localStorage.setItem("seen-messages", "not json");
  expect(hasSeenMessage("PER-1", "x")).toBe(false);
  window.localStorage.setItem("seen-messages", '{"a":1}');
  expect(hasSeenMessage("PER-1", "x")).toBe(false);
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  expect(() => markMessageSeen("PER-1", "x")).not.toThrow();
  expect(hasSeenMessage("PER-1", "x")).toBe(false);
});
