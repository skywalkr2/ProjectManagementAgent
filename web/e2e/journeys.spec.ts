// Journey tests: a real person's path through the screens, from a workspace made by the init command with no template,
// started by the serve command, with fakes only at the outside services (tests/fake_services.py). The point is the joins
// between steps that a test of one step misses. Each journey is a numbered test saying what the person does.
// Names come from the fictional workspace the fake services serve, never written out here.
// The first journey goes through the walkthrough and finishes it, as a person's first visit does; the later ones run on
// that same workspace afterwards, so they start from Today with the walkthrough finished, as a person's later days do.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { collectProblems, connectedAgain, fakeAddress, openView, visit, type Info, type Requests } from "./journey-helpers";

const FAKE = fakeAddress("JOURNEY_FAKE_PORT", 8790);

let info: Info;
const problems: string[] = [];

const requests = async (): Promise<Requests> => (await fetch(`${FAKE}/__e2e/ai-requests`)).json();

test.describe.serial("journeys", () => {
  test.beforeAll(async () => {
    info = await (await fetch(`${FAKE}/__e2e/info`)).json();
  });

  test.afterAll(() => {
    expect(problems.filter((p) => !p.includes("Failed to load resource"))).toEqual([]);
  });

  test("J1. A new workspace: I name myself, add an AI account, hand in a note, press Go and see the result on Today", async ({
    page,
  }) => {
    collectProblems(page, problems);

    // I open the link the start command printed. The walkthrough opens by itself, full screen, and says nothing is
    // spent until I press Go at the end. Nothing else is on the page: no header, no sidebar.
    await page.goto(`?token=${info.token}`);
    await expect(page.getByRole("heading", { level: 1, name: "Set up your workspace" })).toBeVisible();
    await expect(page.getByText("About 10–20 minutes. You can stop and come back.")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Views" })).toHaveCount(0);
    await visit(page);

    // You: my name and the workspace's name. Saving makes my own person record.
    const main = page.locator("main#main");
    await expect(main.getByRole("heading", { level: 2, name: "You" })).toBeVisible();
    await main.getByLabel("Workspace name").fill("Offsite team");
    await main.getByLabel("Your full name").fill(info.people[0]);
    await main.getByRole("button", { name: "Continue" }).click();
    await expect(page.locator('[data-screen="you"][data-state]')).toContainText("Done");
    // Continue on the first screen saves it and goes on to the next one (the same primary button on every screen).
    await visit(page);

    // Your AI account: a service of my own that speaks the common chat format, at the address the fake service
    // answers on. The screen also says what it may spend.
    await expect(main.getByRole("heading", { level: 2, name: "Your AI account" })).toBeVisible();
    await expect(main.getByText(/It asks you before anything over/)).toBeVisible();
    await main.getByRole("radio", { name: /Something else/ }).check();
    await main.getByText("More options").click();
    await main.getByLabel(/^Another service that speaks/).check();
    await main.locator("#ai-key").fill("a-made-up-key");
    await main.getByRole("textbox", { name: "Service address" }).fill(info.ai_base_url);
    await main.getByRole("textbox", { name: "Service address" }).blur();
    // The check runs by itself, for every kind of work, before anything is saved.
    await expect(main.getByText("Works. Ready to use.")).toBeVisible();
    await main.getByText("Advanced", { exact: true }).click();
    await main.getByLabel("AI model for everyday work").selectOption("fake-small");
    await expect(main.getByText("Works. Ready to use.")).toBeVisible();
    // One explicit yes lets this account read my mail and notes (the usual hand-in is internal material).
    await main.getByRole("radio", { name: /^Allow/ }).check();
    await main.getByRole("button", { name: "Continue" }).click();
    // Continue saved the account, tested it and went on to the next screen.
    await expect(main.getByRole("heading", { level: 2, name: "Mail and calendar" })).toBeVisible();
    await expect(page.locator('[data-screen="ai"][data-state]')).toContainText("Done");
    // Changing an account needs no restart, and nothing on the page is waiting for one.
    await expect(main.getByText(/Restart/)).toHaveCount(0);
    await visit(page);
    const afterTest = await requests();
    expect(afterTest.work).toBe(0);
    expect(afterTest.smoke).toBeGreaterThan(0);

    // Mail and calendar: no add-on is listed here, so the core's own forms are offered. I skip it.
    await expect(main.getByRole("heading", { level: 2, name: "Mail and calendar" })).toBeVisible();
    await expect(main.getByRole("button", { name: "Connect one" })).toBeVisible();
    await visit(page);
    await main.getByRole("button", { name: "I'll do this later" }).click();

    // Your promises comes right after mail: with no mail connected it says so and offers nothing to read.
    await expect(main.getByRole("heading", { level: 2, name: "Your promises" })).toBeVisible();
    await expect(main.getByText(/Connect your mail first/)).toBeVisible();
    await expect(main.getByRole("button", { name: "Start", exact: true })).toHaveCount(0);
    await visit(page);
    await main.getByRole("button", { name: "Continue" }).click();

    // Backups: a folder outside the workspace, which is checked before it is saved.
    await expect(main.getByRole("heading", { level: 2, name: "Backups" })).toBeVisible();
    await main.getByLabel("Folder", { exact: true }).fill(info.backup_folder);
    await main.getByRole("button", { name: "Back up now and continue" }).click();
    await expect(page.locator('[data-screen="backup"][data-state]')).toContainText("Done");
    await expect(main.getByRole("heading", { level: 2, name: "People" })).toBeVisible();
    await visit(page);

    // People: skipping is fine.
    await expect(main.getByRole("heading", { level: 2, name: "People" })).toBeVisible();
    await visit(page);
    await main.getByRole("button", { name: "I'll do this later" }).click();

    // Done: what was set up and what was skipped, then Today.
    await expect(main.getByRole("heading", { level: 2, name: "Done" })).toBeVisible();
    const recap = main.getByRole("list", { name: "What was set up" });
    await expect(recap.locator('[data-step="ai"]')).toContainText("Done");
    await expect(recap.locator('[data-step="mail"]')).toContainText("Skipped");
    await expect(recap.locator('[data-step="people"]')).toContainText("Skipped");
    await visit(page);
    await main.getByRole("button", { name: "Go to Today" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
    // It is finished for good: a reload doesn't open it again.
    await page.reload();
    await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Set up your workspace" })).toHaveCount(0);
    await visit(page);

    // I hand in a short note of my own.
    await page.getByRole("button", { name: "Hand something in" }).first().click();
    await page.getByLabel("Paste or type it here").fill(
      "I will send the venue list by 2026-11-02.\nDecided: the offsite is on a Friday.\nWe need a catering quote.",
    );
    await visit(page);
    await page.getByRole("button", { name: "Hand in", exact: true }).click();

    // Today shows one line asking for my go, with a count and what it would cost. Nothing has been sent to the service.
    await page.getByRole("link", { name: /^Today/ }).first().click();
    const go = page.locator('[data-queue-line="first_go"]');
    await expect(go).toHaveCount(1);
    await expect(go).toContainText(/Start the assistant: 1 item, (about \$\d+\.\d\d|less than a cent)/);
    await expect(go).toContainText("Nothing is spent until you press Start.");
    await visit(page);
    expect(await requests()).toEqual(afterTest);

    // Go starts it, and the result is on Today: my action in To do, and the assistant's work to look over.
    await go.getByRole("button", { name: "Start", exact: true }).click();
    await expect(page.getByText("Send the venue list by 2026-11-02.").first()).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('[data-queue-line="first_go"]')).toHaveCount(0);
    // The assistant's work waits behind "N new · Show" while the cursor is in the queue, so the list doesn't move under it.
    const review = page.locator('[data-queue-line="review"]');
    const showNew = page.getByRole("button", { name: /^Show \d+ new items?$/ });
    await expect(review.first().or(showNew).first()).toBeVisible({ timeout: 20_000 });
    if (await showNew.count()) await showNew.click();
    await expect(review).toHaveCount(1);
    await expect(review).toContainText(/Look over 3 things your assistant did/);
    expect((await requests()).work).toBe(1);
    await visit(page);

    // Opened, the review lists what the assistant did, with my name on the action it filed from my own words; the one
    // with no owner asks who it belongs to, and the hand-in did not stop anywhere.
    await review.getByRole("button", { name: /More actions for/ }).click();
    await page.getByRole("menuitem", { name: "Look closer" }).click();
    await expect(review.getByText("Added a to-do").first()).toBeVisible();
    // My name and the due day show on the item's own line, and again in the line that says why it is here (each part editable there).
    await expect(review.getByText(new RegExp(`^${info.people[0]} · due [^·]+$`))).toBeVisible();
    await expect(review.locator("[data-promise-line]").first()).toContainText(new RegExp(`${info.people[0]} · due`));
    await expect(review.getByText("Who owns this?")).toBeVisible();
    await visit(page);
    await expect(page.getByText(/stopped, see why below/)).toHaveCount(0);
  });

  test("J3. A folder I add on screen is read, a new file in it is handed in, and the assistant's result is on Today", async ({
    page,
  }) => {
    collectProblems(page, problems);
    await page.goto(`?token=${info.token}`);
    await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();

    // Sources: add a folder, pointing at the folder the test put the file in.
    await page.getByRole("navigation", { name: "Views" }).getByRole("link", { name: /^Sources/ }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Sources" })).toBeVisible();
    await page.getByRole("button", { name: /Add a source/ }).first().click();
    await page.getByLabel("A folder", { exact: true }).check();
    await page.getByLabel(/^The folder/).fill(info.source_folder);
    await visit(page);
    await page.getByRole("button", { name: "Add source", exact: true }).click();
    await expect(page.getByRole("listitem", { name: "A folder" })).toBeVisible();
    await visit(page);

    // Came in has Check now. The first read only notes what is there, so nothing is handed in yet.
    await page.getByRole("link", { name: /^Today/ }).first().click();
    const before = await requests();
    await page.getByRole("button", { name: "Check now" }).click();
    await expect(page.getByText(/^Checked /).last()).toBeVisible();
    await visit(page);
    expect(await requests()).toEqual(before);

    // A new file lands in the folder. Check now reads it, hands it in, and the assistant's result appears.
    const put = await fetch(`${FAKE}/__e2e/source-file`, {
      method: "POST",
      body: JSON.stringify({ text: "I will book the venue by 2026-11-05.\nWe need a printed agenda.\n" }),
    });
    expect(put.ok).toBe(true);
    await page.getByRole("button", { name: "Check now" }).click();
    await expect(page.getByText("Book the venue by 2026-11-05.").first()).toBeVisible({ timeout: 20_000 });
    expect((await requests()).work).toBe(before.work + 1);
    // The item that arrived is on What changed, named for the file.
    await page.getByRole("navigation", { name: "Views" }).getByRole("link", { name: /^What changed/ }).click();
    await expect(page.getByRole("heading", { level: 1, name: "What changed" })).toBeVisible();
    await expect(page.getByText(/folder-note\.txt/).first()).toBeVisible();
    await visit(page);
  });

  test("J7. The obvious next steps from what came in: each button makes its record, and Undo takes it back", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    collectProblems(page, problems);
    await page.goto(`?token=${info.token}`);
    await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();
    const toasts = page.getByRole("region", { name: "Notifications" });
    const undo = () => toasts.getByRole("button", { name: "Undo" }).last().click();
    const json = async <T>(path: string): Promise<T> => {
      const response = await page.request.get(path);
      expect(response.status(), path).toBe(200);
      return (await response.json()) as T;
    };
    // What the fake AI service answers with when no stand-in rule makes the thing being tried: the next request that
    // holds these words.
    const script = async (when: string, ops: object[]) => {
      const sent = await fetch(`${FAKE}/__e2e/script`, {
        method: "POST",
        body: JSON.stringify({ when, answer: { summary: "Read by the journey's script.", ops } }),
      });
      expect(sent.ok).toBe(true);
    };
    // I hand in someone else's words; the result is a line on Today, and its card is read on What changed.
    const handIn = async (text: string) => {
      await page.getByRole("link", { name: /^Today/ }).first().click();
      const lines = page.locator('[data-queue-line="review"], [data-queue-line="who_is"]');
      // A new line, not a higher count: a line whose work was all undone leaves Today at the same time.
      const before = await lines.allInnerTexts();
      await page.getByRole("button", { name: "Hand something in" }).first().click();
      await page.getByLabel("Paste or type it here").fill(text);
      await page.getByRole("button", { name: "Hand in", exact: true }).click();
      await expect
        .poll(async () => (await lines.allInnerTexts()).some((line) => !before.includes(line)), { timeout: 30_000 })
        .toBe(true);
      await page.getByRole("link", { name: /^What changed/ }).first().click();
      // What changed is newest first and titles a change as Today does, so the change just handed in is the top row.
      const row = page.getByRole("main").locator("li.line").first();
      await expect(row.locator(".kind").first()).toHaveText(/Review/i, { timeout: 30_000 });
      const expander = row.locator(".expander").first();
      if ((await expander.getAttribute("aria-expanded")) !== "true") await expander.click();
      return row;
    };
    type Person = { id: string; name: string };
    const people = async () => (await json<Person[]>("api/people")).map((p) => p.name);
    const actionsOf = async () =>
      (await json<{ person: string; actions: { id: string; text: string; project_name: string | null }[] }[]>("api/followups")).flatMap(
        (s) => s.actions.map((a) => ({ ...a, person: s.person })),
      );
    const me = info.people[0];
    const [, first, newcomer] = info.people;
    const [base] = info.projects;
    const [festival, party, tour, retreat] = ["festival", "party", "tour", "retreat"].map((w) => `${base} ${w}`);

    // 1. Add a new person. A name nobody has on file is one question; the form starts from the name as written, with
    // the cursor in its first field. Adding sends the waiting action to them. Undo takes the person and the action
    // back (the question stays answered), so it is tried on one newcomer and the other is kept.
    let row = page.locator("li.line");
    const addNewcomer = async (name: string, keep: boolean) => {
      const sentence = `${name} will confirm the catering menu by 2026-11-20.`;
      row = await handIn(sentence);
      await expect(row.getByRole("combobox", { name: `Who is “${name}”?` })).toBeVisible();
      // The last choice in the list opens the form in a drawer over the screen; nobody leaves it to add someone.
      await row.getByRole("combobox", { name: `Who is “${name}”?` }).selectOption({ label: "Add a person…" });
      const form = page.getByRole("dialog", { name: "New person" }).getByRole("form", { name: "New person" });
      await expect(form.getByLabel("Full name", { exact: true })).toBeFocused();
      await expect(form.getByLabel("Full name", { exact: true })).toHaveValue(name);
      await visit(page);
      await form.getByRole("button", { name: "Add and use" }).click();
      await expect(toasts).toContainText(`Added ${name}. Related work has resumed.`);
      expect(await people()).toContain(name);
      const waiting = async () => (await actionsOf()).filter((a) => a.text.startsWith("Confirm the catering menu"));
      const owned = async () => (await json<Person[]>("api/people")).find((p) => p.name === name)?.id;
      expect((await waiting()).map((a) => a.person)).toContain(await owned());
      if (keep) return;
      const before = (await waiting()).length;
      await undo();
      await expect.poll(async () => (await people()).includes(name)).toBe(false);
      expect((await waiting()).length).toBe(before - 1);
    };
    await addNewcomer(first, false);
    await addNewcomer(newcomer, true);
    const added = (await json<Person[]>("api/people")).find((p) => p.name === newcomer)!;

    // 2. A contact detail found in what came in always waits; confirming it sets it on the person, and Undo takes it away.
    const reach = "555 0142";
    const direct = `Note from ${newcomer}: my direct line is ${reach}.`;
    await script("my direct line is", [
      { op: "person.contact", person: added.id, kind: "phone", value: reach, evidence: { quote: `my direct line is ${reach}` } },
    ]);
    row = await handIn(direct);
    const reached = async () => JSON.stringify((await json<{ details: object }>(`api/record-pages/${added.id}?kind=person`)).details);
    expect(await reached()).not.toContain(reach);
    await row.getByRole("button", { name: "Do it anyway" }).click();
    await expect(toasts).toContainText("Done.");
    expect(await reached()).toContain(reach);
    await undo();
    await expect.poll(reached).not.toContain(reach);

    // 3. A project it hasn't heard of. Add makes the project and files what the same input made with no project under it;
    // Undo takes both back.
    const plans = `The ${festival} and the ${retreat} need plans. Remember to review each plan.`;
    await script("need plans", [
      { op: "note", text: "The plans are due soon." },
      { op: "action.add", text: "Review each plan", owners: [me], evidence: { quote: "Remember to review each plan" } },
      { op: "project.add", name: retreat, evidence: { quote: `the ${retreat} need plans` } },
      { op: "project.add", name: festival, evidence: { quote: `The ${festival}` } },
    ]);
    row = await handIn(plans);
    const projectNamed = async (name: string) => (await json<{ id: string; name: string }[]>("api/projects")).find((p) => p.name === name);
    const filed = async () => ({
      note: (await json<{ text: string; project_name: string | null }[]>("api/notes")).find((n) => n.text === "The plans are due soon.")?.project_name || null,
      action: (await actionsOf()).find((a) => a.text.startsWith("Review each plan"))?.project_name || null,
    });
    expect(await filed()).toEqual({ note: null, action: null });
    const proposal = (name: string) => row.locator("li.child", { hasText: `Add a project “${name}”?` });
    await proposal(retreat).getByRole("button", { name: "Add", exact: true }).click();
    await expect(toasts).toContainText(`Added the project ${retreat}.`);
    expect(await filed()).toEqual({ note: retreat, action: retreat });
    await undo();
    await expect.poll(async () => await projectNamed(retreat)).toBeUndefined();
    expect(await filed()).toEqual({ note: null, action: null });
    await proposal(festival).getByRole("button", { name: "Add", exact: true }).click();
    await expect(toasts).toContainText(`Added the project ${festival}.`);
    expect(await filed()).toEqual({ note: festival, action: festival });
    await visit(page);

    // 4. It's part of: the work of that input goes under the project I pick, the words are kept as a name for it, and Undo
    // brings the proposal back.
    const meeting = `Plans for the ${party} are due by Friday.`;
    await script("are due by Friday", [
      { op: "note", text: "The party plans are due Friday." },
      { op: "project.add", name: party, evidence: { quote: `Plans for the ${party}` } },
    ]);
    row = await handIn(meeting);
    const partyNote = async () =>
      (await json<{ text: string; project_name: string | null }[]>("api/notes")).find((n) => n.text === "The party plans are due Friday.")?.project_name || null;
    for (const keep of [false, true]) {
      await row.locator("li.child", { hasText: `Add a project “${party}”?` }).getByRole("button", { name: `More actions for ${party}` }).click();
      await page.getByRole("menuitem", { name: "It's part of…" }).click();
      await row.getByLabel(`“${party}” is part of`).selectOption({ label: festival });
      await row.getByRole("button", { name: "File it there" }).click();
      await expect(toasts).toContainText(`Filed under ${festival}. “${party}” is kept as a name for it.`);
      expect(await partyNote()).toBe(festival);
      expect(await projectNamed(party)).toBeUndefined();
      if (keep) break;
      await undo();
      await expect.poll(partyNote).toBeNull();
      await expect(row.locator("li.child", { hasText: `Add a project “${party}”?` })).toBeVisible();
    }

    // 5. Not a project: nothing is filed anywhere and no project is made; the words are kept as not one; Undo brings it back.
    const trip = `Everyone is looking forward to the ${tour}.`;
    await script("is looking forward", [
      { op: "note", text: "Looking forward to it." },
      { op: "project.add", name: tour, evidence: { quote: `looking forward to the ${tour}` } },
    ]);
    row = await handIn(trip);
    const tourProposal = row.locator("li.child", { hasText: `Add a project “${tour}”?` });
    for (const keep of [false, true]) {
      await tourProposal.getByRole("button", { name: `More actions for ${tour}` }).click();
      await page.getByRole("menuitem", { name: "Not a project" }).click();
      await expect(toasts).toContainText(`“${tour}” is kept as not a project.`);
      expect(await projectNamed(tour)).toBeUndefined();
      if (keep) break;
      await undo();
      await expect(tourProposal).toBeVisible();
    }

    // 6. Drop, on an action that is no longer needed: it asks why, leaves the list at once, and Undo puts it back.
    const agenda = "I will print the agenda.";
    row = await handIn(agenda);
    // The to-do is in the rail of Today, beside the queue.
    await page.getByRole("link", { name: /^Today/ }).first().click();
    const todo = page.locator("li", { has: page.getByRole("checkbox", { name: "Mark done: Print the agenda." }) });
    await expect(todo).toHaveCount(1, { timeout: 20_000 });
    await todo.getByRole("button", { name: "More actions for Print the agenda." }).click();
    await page.getByRole("menuitem", { name: "Drop" }).click();
    await page.getByLabel("Why isn't it needed?").fill("The printer sends it.");
    await page.getByRole("button", { name: "Drop it" }).click();
    await expect(toasts).toContainText("Dropped.");
    expect((await actionsOf()).filter((a) => a.text === "Print the agenda.")).toHaveLength(0);
    await undo();
    await expect.poll(async () => (await actionsOf()).filter((a) => a.text === "Print the agenda.").length).toBe(1);

    // 7. Add to the nearest action: a new action with no owner that nearly repeats one I have is added to that one, and Undo
    // gives it back as a question about who owns it.
    const again = "Somebody should print the agenda.";
    await script("Somebody should print", [{ op: "action.add", text: "Print the agenda.", owners: [], evidence: { quote: again } }]);
    row = await handIn(again);
    await expect(row.getByText("Who owns this?")).toBeVisible();
    await row.getByRole("button", { name: "Add to “Print the agenda.”" }).click();
    await expect(toasts).toContainText("Added to Print the agenda.");
    expect((await actionsOf()).filter((a) => a.text === "Print the agenda.")).toHaveLength(1);
    await undo();
    await expect(row.getByText("Who owns this?")).toBeVisible();
    await visit(page);
  });

  test("J4. An add-on from the list: I install it, restart, turn it on, restart, open its screen, then turn it off and remove it", async ({
    page,
  }) => {
    test.setTimeout(240_000);
    collectProblems(page, problems);
    await page.goto(`?token=${info.token}`);
    await expect(page.getByRole("heading", { level: 1, name: "Today" })).toBeVisible();

    // The app runs in a throwaway environment of its own, so an install from the screen can't reach the project's.
    expect(info.install_target).toBeTruthy();
    expect(info.install_target).not.toBe(info.project_site);

    // Add-ons lists what the catalog offers: what it adds and reaches, and an Install button.
    await openView(page, "Add-ons");
    await expect(page.getByRole("heading", { name: "Add-ons", exact: true })).toBeVisible();
    const row = page.locator("li.line", { hasText: "Example panel" });
    await expect(row).toHaveCount(1);
    await expect(row).toContainText("1 screen");
    await expect(row).toContainText("Free");
    await visit(page);
    expect(existsSync(join(String(info.install_target), "journey_panel"))).toBe(false);

    // Install puts it in place and says a restart is needed; it does not turn it on.
    await row.getByRole("button", { name: "Install Example panel" }).click();
    await expect(row.getByText(/is installed\. Restart, then turn it on/)).toBeVisible();
    expect(existsSync(join(String(info.install_target), "journey_panel"))).toBe(true);
    await visit(page);

    // Restart now: the app comes back on the same address, and the notice says so.
    await row.getByRole("button", { name: "Restart now" }).click();
    await expect(page.getByText("Restarted with the new settings.")).toBeVisible({ timeout: 90_000 });
    await connectedAgain(page);
    await visit(page);

    // After the restart the row says it is installed and off; turning it on waits for another restart.
    await expect(row).toContainText("Installed (version 0.1.0) and off");
    await row.getByRole("button", { name: "Turn on Example panel" }).click();
    // The row still carries the install note ("ready after a restart"), so that text proves nothing about Turn on. Wait
    // for the row to say what was saved: a restart asked for before then can reach the app ahead of the request.
    await expect(row).toContainText("Installed (version 0.1.0) and on after a restart");
    await expect(page.getByRole("link", { name: /Example overview/ })).toHaveCount(0);
    await row.getByRole("button", { name: "Restart now" }).first().click();
    await expect(page.getByText("Restarted with the new settings.")).toBeVisible({ timeout: 90_000 });
    await connectedAgain(page);

    // Its screen is in the sidebar (once the app has told the page about it) and opens. The page learns of it when it
    // reloads its data after reconnecting, which a busy machine can take longer than the default wait to do.
    await expect(page.getByRole("navigation", { name: "Views" }).getByRole("link", { name: "Example overview" })).toBeVisible({
      timeout: 30_000,
    });
    await openView(page, "Example overview");
    await expect(page.getByRole("heading", { level: 1, name: "Example overview" })).toBeVisible();
    await expect(page.getByText("This page comes from the example add-on.")).toBeVisible();
    await visit(page);

    // Turn it off, restart, and remove it from the row's menu; after another restart it is gone.
    await openView(page, "Add-ons");
    await page.getByRole("tab", { name: "Installed" }).click();
    const installed = page.locator("li.line", { hasText: "journey-panel" });
    await installed.getByRole("button", { name: "Turn off journey-panel" }).click();
    await expect(installed).toContainText("Off after a restart");

    // The menu offers Remove as soon as it is off, and Remove works then: it still runs until the restart, so new work
    // waits for that restart, which the header offers.
    await installed.getByRole("button", { name: "More actions for journey-panel" }).click();
    const removed = page.waitForResponse((r) => r.url().endsWith("/uninstall") && r.request().method() === "POST");
    await page.getByRole("menuitem", { name: "Remove" }).click();
    // The restart below must come after the removal has been answered, not race it.
    expect((await removed).ok()).toBe(true);
    await expect(installed.getByRole("alert")).toHaveCount(0);
    await page.getByRole("button", { name: /^App status: / }).click();
    await page.getByRole("dialog", { name: "Status" }).getByRole("button", { name: "Restart now" }).click();
    await expect(page.getByText("Restarted with the new settings.").first()).toBeVisible({ timeout: 90_000 });
    // Close the status popover with Escape before using the sidebar.
    await page.getByRole("dialog", { name: "Status" }).press("Escape");
    await expect(page.getByRole("dialog", { name: "Status" })).toHaveCount(0);
    await connectedAgain(page);
    await expect(page.getByRole("navigation", { name: "Views" }).getByRole("link", { name: "Example overview" })).toHaveCount(0);
    await openView(page, "Add-ons");
    await page.getByRole("tab", { name: "Installed" }).click();

    // Removed: the row is gone from Installed, the files are gone from the place the app installs into, and the
    // catalog offers it again.
    await expect(page.locator("li.line", { hasText: "journey-panel" })).toHaveCount(0);
    expect(existsSync(join(String(info.install_target), "journey_panel"))).toBe(false);
    await page.reload();
    await page.getByRole("tab", { name: "Installed" }).click();
    await expect(page.locator("li.line", { hasText: "journey-panel" })).toHaveCount(0);
    await page.getByRole("tab", { name: "Available" }).click();
    await expect(
      page.locator("li.line", { hasText: "Example panel" }).getByRole("button", { name: "Install Example panel" }),
    ).toBeVisible();
    await visit(page);

    // The project's own environment never held the add-on: nothing in it was installed from the screen.
    const site = String(info.project_site);
    const marked = readdirSync(site).filter(
      (name) =>
        name.endsWith(".dist-info") &&
        existsSync(join(site, name, "INSTALLER")) &&
        readFileSync(join(site, name, "INSTALLER"), "utf8").trim() === "pm-cockpit",
    );
    expect(marked).toEqual([]);
    expect(existsSync(join(site, "journey_panel"))).toBe(false);
  });
});
