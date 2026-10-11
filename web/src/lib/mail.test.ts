import { MAIL_LINK_MAX, mailText, mailtoLink, tooLongForLink } from "./mail";

const TO = "feedback@example.com";

test("the subject and body are encoded, with line breaks the way mail links write them", () => {
  const link = mailtoLink(TO, "Feedback & more?", "Line one\nLine two #1 100%");
  expect(link).toBe(
    `mailto:${TO}?subject=${encodeURIComponent("Feedback & more?")}&body=${encodeURIComponent("Line one\r\nLine two #1 100%")}`,
  );
  const url = new URL(link!);
  expect(url.searchParams.get("subject")).toBe("Feedback & more?");
  expect(url.searchParams.get("body")).toBe("Line one\r\nLine two #1 100%");
});

test("there is no link without an address", () => {
  expect(mailtoLink(null, "S", "B")).toBeNull();
  expect(mailtoLink(undefined, "S", "B")).toBeNull();
  expect(mailtoLink("  ", "S", "B")).toBeNull();
  expect(tooLongForLink(null, "S", "B")).toBe(false);
});

test("a link longer than the limit is not offered", () => {
  const fits = "a".repeat(MAIL_LINK_MAX - `mailto:${TO}?subject=S&body=`.length);
  expect(mailtoLink(TO, "S", fits)!.length).toBe(MAIL_LINK_MAX);
  expect(tooLongForLink(TO, "S", fits)).toBe(false);
  expect(mailtoLink(TO, "S", `${fits}a`)).toBeNull();
  expect(tooLongForLink(TO, "S", `${fits}a`)).toBe(true);
});

test("the length counts the encoded text", () => {
  // Each line break is six characters once encoded.
  const body = "\n".repeat(Math.ceil(MAIL_LINK_MAX / 6));
  expect(mailtoLink(TO, "S", body)).toBeNull();
});

test("the copied text is the subject, a blank line and the body", () => {
  expect(mailText("Subject", "Body\nmore")).toBe("Subject\n\nBody\nmore");
});
