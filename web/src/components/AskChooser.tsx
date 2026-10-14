// A question the assistant asks the PM before an item can go ahead: who a name is, or who owns an action.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useWords } from "../lib/wording";
import { NoteBox, useNoted } from "./NoteBox";
import { PersonPicker } from "./PersonPicker";
import { RowMenu } from "./RowMenu";

export function AskChooser(props: { ask: S["Ask"] | { id: string; about: string; name?: string | null; options: S["Option"][] } }) {
  const { t } = useWords();
  const act = useAct();
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const [person, setPerson] = useState("");
  const ask = props.ask;
  const label = ask.about === "owner" ? t("ask.owner") : t("ask.who_is", { name: ask.name ?? "" });
  const chosen = people.data?.find((p) => p.id === person)?.name ?? "";
  const noted = useNoted();
  const [noting, setNoting] = useState(false);
  const word = ask.about === "owner" ? t("ask.add_owner") : t("ask.use_person");
  // The note goes with the choice, on the same route; with no note the body is only the person.
  const choose = (note?: string) =>
    act(
      () => api.answer(ask.id, note ? { person, text: note } : { person }),
      (done) => ({ message: noted(t(ask.about === "owner" ? "toast.owner_set" : "toast.person_set", { name: chosen }), done.request) }),
    );
  return (
    <div className="ask-chooser">
      <PersonPicker
        label={label}
        value={person}
        onChange={setPerson}
        suggested={ask.options}
        people={people.data ?? []}
      />
      <div className="row-end">
        <button type="button" className="btn primary" data-key="primary" disabled={!person} onClick={() => void choose()}>
          {word}
        </button>
        <RowMenu
          label={label}
          actions={[
            { id: "note", label: t("note.add"), run: () => setNoting(true), disabled: !person, reason: t("ask.note_needs_person") },
          ]}
        />
      </div>
      {noting && person && <NoteBox sends={[{ label: word, run: choose }]} onClose={() => setNoting(false)} />}
    </div>
  );
}
