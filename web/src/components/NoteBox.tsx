// The note box on an action button (design 7.5): the button acts at once, as it always did; its menu's "Add a note"
// opens this short box, and sending the note does the same act with the note on it. The cursor starts in the box,
// Enter sends, Escape closes. A note that couldn't be sent stays in the box.
import { useEffect, useId, useRef, useState } from "react";
import { useWords } from "../lib/wording";
import { useAddOwnRequest } from "./HandIn";

export interface NoteSend {
  label: string;
  /** Does the act with the note; an act that didn't go through returns nothing, so the box stays open. */
  run: (note: string) => Promise<unknown> | void;
}

/** One or more acts a note can go with; the first is the main one, and Enter sends it. */
export function NoteBox(props: { sends: NoteSend[]; onClose: () => void }) {
  const { t } = useWords();
  const id = useId();
  const area = useRef<HTMLTextAreaElement>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => area.current?.focus(), []);
  const text = note.trim();

  const send = async (which: NoteSend) => {
    if (!text || busy) return;
    setBusy(true);
    const result = await which.run(text);
    if (result === undefined) setBusy(false);
    else props.onClose();
  };

  return (
    <form
      className="answer-form note-box"
      onSubmit={(e) => {
        e.preventDefault();
        void send(props.sends[0]);
      }}
    >
      <label className="hint" htmlFor={id}>
        {t("note.label")}
      </label>
      <textarea
        id={id}
        ref={area}
        className="short"
        value={note}
        aria-describedby={`${id}-hint`}
        onChange={(e) => setNote(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.stopPropagation();
            props.onClose();
          } else if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            void send(props.sends[0]);
          }
        }}
      />
      <span id={`${id}-hint`} className="hint">
        {t("note.hint")}
      </span>
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onClose}>
          {t("action.cancel")}
        </button>
        {props.sends.map((s, i) => (
          <button
            key={s.label}
            type={i === 0 ? "submit" : "button"}
            className={i === 0 ? "btn primary" : "btn"}
            disabled={!text || busy}
            onClick={i === 0 ? undefined : () => void send(s)}
          >
            {s.label}
          </button>
        ))}
      </div>
    </form>
  );
}

/** What a toast says after an act that may have carried a note: when the server queued work from the note, the toast
 * says the assistant will read it, and the work shows in What changed at once. */
export function useNoted(): (message: string, request?: string | null) => string {
  const { t } = useWords();
  const addOwn = useAddOwnRequest();
  return (message, request) => {
    if (!request) return message;
    addOwn(request);
    return t("toast.with_note", { message });
  };
}
