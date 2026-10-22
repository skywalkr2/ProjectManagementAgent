// Made-up acts for tests: a message to one person, with each part of the view a screen reads.
import type { Act, ActRecipient } from "./acts";

export function recipient(over: Partial<ActRecipient> = {}): ActRecipient {
  return { key: "PER-2", person: "PER-2", name: "Ana Example", address: "ana@example.com", role: "to", reasons: [], ...over };
}

export function actFixture(over: Partial<Act> = {}): Act {
  return {
    id: "XACT-1",
    version: 1,
    channel: "fake",
    channel_label: "Test channel",
    kind: "message",
    status: "draft",
    parts: { subject: "The proofs", body: "The proofs ship on Monday.\n\nThanks." },
    recipients: [recipient()],
    fingerprint: "fp-1",
    withheld: null,
    failure: null,
    why: [],
    made_by: "assistant",
    sensitivity: "internal",
    ...over,
  };
}
