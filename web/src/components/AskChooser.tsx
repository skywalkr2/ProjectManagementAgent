// A question the assistant asks the PM before an item can go ahead: who a name is, or who owns an action.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useWords } from "../lib/wording";
import { PersonPicker } from "./PersonPicker";

export function AskChooser(props: { ask: S["Ask"] | { id: string; about: string; name?: string | null; options: S["Option"][] } }) {
  const { t } = useWords();
  const act = useAct();
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const [person, setPerson] = useState("");
  const ask = props.ask;
  const label = ask.about === "owner" ? t("ask.owner") : t("ask.who_is", { name: ask.name ?? "" });
  const chosen = people.data?.find((p) => p.id === person)?.name ?? "";
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
        <button
          type="button"
          className="btn primary"
          data-key="primary"
          disabled={!person}
          onClick={() =>
            void act(
              () => api.answer(ask.id, { person }),
              () => ({ message: t(ask.about === "owner" ? "toast.owner_set" : "toast.person_set", { name: chosen }) }),
            )
          }
        >
          {ask.about === "owner" ? t("ask.add_owner") : t("ask.use_person")}
        </button>
      </div>
    </div>
  );
}
