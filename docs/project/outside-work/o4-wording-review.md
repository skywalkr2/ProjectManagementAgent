# O4: Plain-language review of the app's on-screen wording

**Why:** the app is for anyone juggling work, not only technical people. Every word on screen comes from one file, so
it can be reviewed in one place.

**Read:** `web/src/wording/en.json` (about 3,900 entries, each a key and the words shown) and, for the tone,
`CLAUDE.md`'s "UI rules" and "Product rules that shape every feature" sections.

**Look for:**
1. Internal or technical words a person shouldn't meet (record, op, changeset, payload, config, token, endpoint, ids).
2. The same thing called by different names in different places (one word each, everywhere).
3. Lines that start with something other than the verb where the person is asked to act ("Today shows only what the
   person does, each line starting with the verb").
4. Wording that blames the person, scolds, or says "simply" or "just".
5. Entries over about 20 words that could be shorter without losing anything.
6. Buttons whose words don't say what happens.

**Produce:** `docs/project/wording-review-2026-10.md`: a table with the key, the current words, the suggested words and
the reason (1 to 6 above). Suggest; don't edit `en.json`. Keep `{placeholders}` exactly as they are.

**How it is checked:** the main session reads the table and applies the accepted rows through the wording test
(`npm --prefix web test -- --run src/wording/wording.test.ts`).
