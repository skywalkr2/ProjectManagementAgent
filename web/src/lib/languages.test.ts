import { languageChoices, languageLabel } from "./languages";

test("a tag is named in the given language, and a tag the browser can't name stays as it is", () => {
  expect(languageLabel("en-US", "en")).toBe("English (United States)");
  expect(languageLabel("fr-CA", "en")).toBe("French (Canada)");
  expect(languageLabel("fr-CA", "fr")).toMatch(/^français/);
  expect(languageLabel("not a tag!", "en")).toBe("not a tag!");
});

test("choices are sorted by their labels, with a repeated tag shown once", () => {
  const choices = languageChoices(["fr-FR", "en-US", "de-DE", "en-US", "en-GB"], "en");
  expect(choices.map((c) => c.tag)).toEqual(["en-GB", "en-US", "fr-FR", "de-DE"]);
  expect(choices[0].label).toBe("English (United Kingdom)");
});
