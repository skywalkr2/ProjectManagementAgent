import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { WordingProvider } from "../lib/wording";
import { Highlighted, SafeText, findQuote } from "./SafeText";

const wrap = (ui: React.ReactNode) => render(<WordingProvider>{ui}</WordingProvider>);

test("markup in someone else's material stays text", () => {
  const { container } = wrap(<SafeText text={'<img src=x onerror="alert(1)"> hello <b>bold</b>'} />);
  expect(container.querySelector("img")).toBeNull();
  expect(container.querySelector("b")).toBeNull();
  expect(container.textContent).toContain("<img src=x");
});

// A link from the fictional imprint's data, so no URL is written into code.
const fixtureLink: { label: string; url: string } = (() => {
  const file = join(__dirname, "../../../workspaces/demo-b/data/project.json");
  const data = JSON.parse(readFileSync(file, "utf-8"));
  const projects = Array.isArray(data) ? data : Object.values(data.records ?? data);
  return (projects as Array<{ links?: Array<{ label: string; url: string }> }>).find((p) => p.links?.length)!.links![0];
})();

test("a labelled link shows its real domain and opens safely", () => {
  wrap(<SafeText text={`Proof schedule: ${fixtureLink.url}`} />);
  const link = screen.getByRole("link", { name: "Proof schedule" });
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
  expect(link).toHaveAttribute("href", fixtureLink.url);
  expect(screen.getByText(`(${new URL(fixtureLink.url).host})`)).toBeInTheDocument();
});

test("only web links become links", () => {
  wrap(<SafeText text={"Click: javascript:alert(1)"} />);
  expect(screen.queryByRole("link")).toBeNull();
});

test("dash lines become a list", () => {
  const { container } = wrap(<SafeText text={"Items:\n- one\n- two"} />);
  expect(container.querySelectorAll("li")).toHaveLength(2);
});

test("quotes are found the way the server checks evidence", () => {
  const text = "Thanks.  Proof copies will\nship on November 5 by courier.";
  const found = findQuote(text, "proof copies will ship on November 5");
  expect(found).not.toBeNull();
  expect(text.slice(found![0], found![1])).toBe("Proof copies will\nship on November 5");
  expect(findQuote(text, "words nobody wrote")).toBeNull();
});

test("the quoted passage is marked for sight and for screen readers", () => {
  const { container } = wrap(<Highlighted text={"a b c d"} quote={"b c"} />);
  const mark = container.querySelector("mark")!;
  expect(mark.textContent).toContain("b c");
  expect(mark.querySelectorAll(".sr")).toHaveLength(2);
});
