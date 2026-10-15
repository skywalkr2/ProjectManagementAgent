import { screen, within } from "@testing-library/react";
import type { S } from "../lib/api";
import { fakeApi, renderApp } from "../test-utils";
import { WhatChanged } from "./WhatChanged";

function changeWith(made: S["MadeView"][]): S["ChangeItem"] {
  return {
    id: "REQ-1",
    version: 2,
    dismissed: false,
    stage_task: false,
    first_go: false,
    refused: false,
    state: "review",
    waiting: null,
    created_at: "2026-10-09T14:00:00Z",
    note: null,
    source: null,
    source_title: "Minutes of the call",
    changeset: {
      id: "CS-1",
      summary: "Wrote up the call.",
      status: "applied",
      reviewed: false,
      trust: "trusted",
      ops: [],
      made,
    },
  };
}

test("each draft or file a change made is a Made link on its row, with what it is for", async () => {
  fakeApi({
    "GET changes": () => [
      changeWith([
        { kind: "draft", id: "TXT-3", label: "Call minutes", record: { kind: "minutes", id: "MIN-2" } },
        { kind: "file", id: "FILE-4", label: "call-minutes.pdf", record: { kind: "file", id: "FILE-4" } },
      ]),
    ],
  });
  renderApp(<WhatChanged />);
  const list = await screen.findByRole("list", { name: "Made:" });
  const links = within(list).getAllByRole("link");
  expect(list.closest(".body")).toBeNull();
  expect(links.map((l) => l.textContent)).toEqual(["Call minutes, a draft not yet reviewed", "call-minutes.pdf, a file"]);
  // The links sit on the row itself, outside its details. A draft opens on the record it is for,
  // a file in the files list.
  expect(links[0].getAttribute("href")).toMatch(/#records\/minutes\/MIN-2$/);
  expect(links[1].getAttribute("href")).toMatch(/#records\/files$/);
});

test("a change that made nothing shows no Made line", async () => {
  fakeApi({ "GET changes": () => [changeWith([])] });
  renderApp(<WhatChanged />);
  await screen.findByText("Minutes of the call");
  expect(screen.queryByRole("list", { name: "Made:" })).toBeNull();
});
