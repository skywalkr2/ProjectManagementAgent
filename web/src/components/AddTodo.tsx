// Adding a to-do by hand (design 6.32): the words, the day in plain words (said back under the field), who does it (a
// list of people, the person by default), the project (a list, optional) and how it repeats (said back, as in the edit
// form). It opens as a drawer with the cursor in the words, and acts at once as the person's own, with Undo on the toast.
// Words that aren't clear keep nothing.
import { useQuery } from "@tanstack/react-query";
import { useId, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { useAct } from "../lib/act";
import { day } from "../lib/dates";
import { saidRepeat, useRepeatCheck } from "../lib/repeat";
import { useDayCheck } from "../lib/todo-day";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Drawer } from "../ui/Drawer";
import { PersonPicker } from "./PersonPicker";
import { ProjectPicker } from "./ProjectPicker";

function AddTodoForm(props: { onClose: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const id = useId();
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const [text, setText] = useState("");
  const [when, setWhen] = useState("");
  const [owner, setOwner] = useState<string | null>(null);
  const [project, setProject] = useState("");
  const [repeat, setRepeat] = useState("");
  const active = (people.data ?? []).filter((p) => p.status !== "left");
  // The person is the default owner until another is picked.
  const who = owner ?? active.find((p) => p.is_pm)?.id ?? "";
  const read = useDayCheck(when);
  const dayIso = read?.status === "ok" ? (read.day ?? null) : null;
  const typedRepeat = repeat.trim();
  const readRepeat = useRepeatCheck(typedRepeat, dayIso);
  const dayOk = !when.trim() || read?.status === "ok";
  const repeatOk = !typedRepeat || readRepeat?.status === "ok";
  const words = text.trim();
  const ready = !!words && !!who && dayOk && repeatOk;
  const save = async () => {
    if (!ready) return;
    const body = { text: words, owners: [who], ...(when.trim() ? { when: when.trim() } : {}), ...(project ? { project } : {}), ...(typedRepeat ? { repeat: typedRepeat } : {}) };
    const made = await act(
      () => api.addTodo(body),
      (result) => ({
        message: t("addtodo.saved", { text: words }),
        undo: async () => {
          for (const changeset of [...result.changesets].reverse()) await api.undo(changeset);
        },
      }),
    );
    if (made) props.onClose();
  };
  return (
    <Drawer
      open
      title={t("addtodo.title")}
      onClose={props.onClose}
      dirty={!!words || !!when.trim() || !!typedRepeat}
      footer={
        <>
          <Button variant="ghost" onClick={props.onClose}>
            {t("action.cancel")}
          </Button>
          <Button variant="primary" type="submit" form={`${id}-form`} disabled={!ready}>
            {t("addtodo.save")}
          </Button>
        </>
      }
    >
      <form
        id={`${id}-form`}
        className="answer-form"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <div className="field">
          <label htmlFor={`${id}-text`}>{t("addtodo.text")}</label>
          <input id={`${id}-text`} type="text" autoFocus value={text} onChange={(e) => setText(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor={`${id}-when`}>{t("addtodo.when")}</label>
          <input
            id={`${id}-when`}
            type="text"
            value={when}
            placeholder={t("addtodo.when_placeholder")}
            aria-describedby={`${id}-when-said`}
            onChange={(e) => setWhen(e.target.value)}
          />
          <p className="hint" id={`${id}-when-said`} aria-live="polite">
            {dayIso && t("addtodo.day_said", { date: day(dayIso) })}
            {read?.status === "unclear" && t("addtodo.day_unclear")}
          </p>
        </div>
        <PersonPicker label={t("addtodo.owner")} value={who} suggested={[]} people={active} onChange={setOwner} />
        <ProjectPicker label={t("addtodo.project")} value={project} empty={t("addtodo.no_project")} onChange={setProject} />
        <div className="field">
          <label htmlFor={`${id}-repeat`}>{t("repeat.label")}</label>
          <input
            id={`${id}-repeat`}
            type="text"
            value={repeat}
            placeholder={t("repeat.placeholder")}
            aria-describedby={`${id}-repeat-said`}
            onChange={(e) => setRepeat(e.target.value)}
          />
          <p className="hint" id={`${id}-repeat-said`} aria-live="polite">
            {readRepeat?.status === "ok" && readRepeat.shape && readRepeat.start && saidRepeat(t, readRepeat.shape, readRepeat.start)}
            {readRepeat?.status === "unclear" && t("repeat.unclear")}
            {readRepeat?.status === "off_start" && readRepeat.start && t("repeat.off_start", { date: day(dayIso), first: day(readRepeat.start) })}
          </p>
        </div>
      </form>
    </Drawer>
  );
}

/** Opens the add-a-to-do form: `open` for the button that starts it, `form` to render once beside it. */
export function useAddTodo(): { open: () => void; form: ReactNode } {
  const [shown, setShown] = useState(false);
  return { open: () => setShown(true), form: shown ? <AddTodoForm onClose={() => setShown(false)} /> : null };
}
