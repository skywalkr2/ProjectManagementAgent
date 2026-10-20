import { afterEach, expect, test, vi } from "vitest";
import { copyMessage, copyPlain, escapeHtml, messageHtml } from "./copy";

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Made-up addresses are built from this, so no address is written out whole. */
const WEB = "https" + "://";
const PLAIN_WEB = "http" + "://";

const HOSTILE = `<img src=x onerror="alert(1)"> & "quoted" 'single' <script>steal()</script>`;

test("the formatted version escapes every piece of text", () => {
  expect(escapeHtml(HOSTILE)).toBe(
    "&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; &quot;quoted&quot; &#39;single&#39; &lt;script&gt;steal()&lt;/script&gt;",
  );
  const html = messageHtml(`Hi <b>Ana</b>,\n\n${HOSTILE}\nSecond line & more.`);
  expect(html).not.toMatch(/<(img|script|b)[\s>]/);
  expect(html).toContain("Hi &lt;b&gt;Ana&lt;/b&gt;,");
  expect(html).toContain("&lt;script&gt;steal()&lt;/script&gt;");
  // Only the tags the formatting itself makes are there.
  const tags = [...html.matchAll(/<\/?([a-z0-9]+)/g)].map((m) => m[1]);
  expect(new Set(tags)).toEqual(new Set(["p", "br"]));
});

test("paragraphs are blank-line separated and a line break inside one is kept", () => {
  expect(messageHtml("One\ntwo\n\nThree")).toBe("<p>One<br>two</p><p>Three</p>");
  expect(messageHtml("")).toBe("");
});

test("a web address becomes a link whose address and words are escaped, and other schemes stay plain text", () => {
  const docs = `${PLAIN_WEB}docs.example.com`;
  const html = messageHtml(`See ${docs}/a?x=1&y=2, then "${docs}/q"x and javascript:alert(1) and <${PLAIN_WEB}evil.example/>.`);
  expect(html).toContain(`<a href="${docs}/a?x=1&amp;y=2">${docs}/a?x=1&amp;y=2</a>,`);
  // A quote ends the address; it can never end the attribute early.
  expect(html).toContain(`&quot;<a href="${docs}/q">${docs}/q</a>&quot;x`);
  expect(html).not.toContain('href="javascript');
  expect(html).toContain("javascript:alert(1)");
  expect(html).not.toContain(`<${PLAIN_WEB}`);
  expect(messageHtml(`${WEB}secure.example.com/x`)).toContain(`<a href="${WEB}secure.example.com/x">`);
});

/** A blob's text (the test browser's blobs have no `text()`). */
const read = (blob: Blob) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });

class FakeItem {
  constructor(public parts: Record<string, Blob>) {}
}

function stubClipboard(write?: (items: FakeItem[]) => Promise<void>, writeText?: (text: string) => Promise<void>) {
  const clip = { write, writeText: writeText ?? (async () => undefined) };
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: clip });
  return clip;
}

test("a message is put on the clipboard formatted and plain together", async () => {
  vi.stubGlobal("ClipboardItem", FakeItem);
  const written: FakeItem[] = [];
  stubClipboard(async (items) => void written.push(...items));
  expect(await copyMessage("Hi <Ana>,\n\nThanks.")).toBe("formatted");
  expect(written).toHaveLength(1);
  const parts = written[0].parts;
  expect(Object.keys(parts).sort()).toEqual(["text/html", "text/plain"]);
  expect(await read(parts["text/plain"])).toBe("Hi <Ana>,\n\nThanks.");
  expect(await read(parts["text/html"])).toBe("<p>Hi &lt;Ana&gt;,</p><p>Thanks.</p>");
});

test("a browser with no rich clipboard gets the plain text, and says so", async () => {
  vi.stubGlobal("ClipboardItem", undefined);
  const seen: string[] = [];
  stubClipboard(undefined, async (text) => void seen.push(text));
  expect(await copyMessage("Hi,\n\nThanks.")).toBe("plain");
  expect(seen).toEqual(["Hi,\n\nThanks."]);
});

test("copy as plain text puts only the text on the clipboard, even where formatting could go", async () => {
  vi.stubGlobal("ClipboardItem", FakeItem);
  const written: FakeItem[] = [];
  const seen: string[] = [];
  stubClipboard(async (items) => void written.push(...items), async (text) => void seen.push(text));
  expect(await copyPlain("Hi,\n\nThanks.")).toBe("plain");
  expect(written).toHaveLength(0);
  expect(seen).toEqual(["Hi,\n\nThanks."]);
});

test("a rich copy the browser refuses falls back to plain text, and a refused plain copy is blocked", async () => {
  vi.stubGlobal("ClipboardItem", FakeItem);
  const seen: string[] = [];
  stubClipboard(
    async () => {
      throw new Error("refused");
    },
    async (text) => void seen.push(text),
  );
  expect(await copyMessage("Hi")).toBe("plain");
  expect(seen).toEqual(["Hi"]);
  stubClipboard(undefined, async () => {
    throw new Error("blocked");
  });
  expect(await copyMessage("Hi")).toBe("blocked");
  expect(await copyPlain("Hi")).toBe("blocked");
});
