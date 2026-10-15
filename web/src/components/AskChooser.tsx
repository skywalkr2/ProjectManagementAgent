// A question the assistant asks the PM before an item can go ahead: who a name is, or who owns an action.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useWords } from "../lib/wording";
import { NoteBox, useNoted } from "./NoteBox";
import { NewPersonForm } from "./NextSteps";
import { PersonPicker } from "./PersonPicker";
import { RowMenu } from "./RowMenu";

/** Where an unowned action came from, so it can be added to another action instead of being given an owner. */
export interface FoldAt {
  changeset: string;
  index: number;
}

export function AskChooser(props: {
  ask: S["Ask"] | { id: string; about: string; name?: string | null; options: S["Option"][]; suggestion?: S["OwnerSuggestionView"] | null };
  fold?: FoldAt;
}) {
  const { t } = useWords();
  const act = useAct();
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const [person, setPerson] = useState("");
  const ask = props.ask;
  const label = ask.about === "owner" ? t("ask.owner") : t("ask.who_is", { name: ask.name ?? "" });
  const chosen = people.data?.find((p) => p.id === person)?.name ?? "";
  const noted = useNoted();
  const [noting, setNoting] = useState(false);
  const [adding, setAdding] = useState(false);
  const word = ask.about === "owner" ? t("ask.add_owner") : t("ask.use_person");
  const near = ask.about === "owner" && props.fold ? ask.suggestion : null;
  const foldInto = near?.fold_into && near.fold_version != null ? { id: near.fold_into, version: near.fold_version, text: near.fold_into_text ?? "" } : null;
  const fold = () => {
    if (!foldInto || !props.fold) return;
    void act(
      () => api.foldAction(props.fold!.changeset, props.fold!.index, foldInto.id, foldInto.version),
      (done) => ({ message: t("toast.folded", { action: foldInto.text }), undo: () => api.undo(done.changeset) }),
    );
  };
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
      {foldInto && <span className="hint">{t("ask.fold_hint")}</span>}
      <div className="row-end">
        <button type="button" className="btn primary" data-key="primary" disabled={!person} onClick={() => void choose()}>
          {word}
        </button>
        {ask.about === "held-op" && (
          <button type="button" className="btn" aria-expanded={adding} onClick={() => setAdding((v) => !v)}>
            {t("ask.add_person")}
          </button>
        )}
        {foldInto && (
          <button type="button" className="btn" onClick={fold}>
            {t("ask.fold", { action: foldInto.text })}
          </button>
        )}
        <RowMenu
          label={label}
          actions={[
            { id: "note", label: t("note.add"), run: () => setNoting(true), disabled: !person, reason: t("ask.note_needs_person") },
          ]}
        />
      </div>
      {adding && <NewPersonForm question={ask.id} onClose={() => setAdding(false)} />}
      {noting && person && <NoteBox sends={[{ label: word, run: choose }]} onClose={() => setNoting(false)} />}
    </div>
  );
}
