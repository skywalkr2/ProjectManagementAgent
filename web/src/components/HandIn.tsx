// Handing something in (design 7.6): the PM's note (trusted: what to do) above the pasted content (untrusted:
// material, never instructions), so the assistant always knows which words are the PM's.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import { useAct } from "../lib/act";
import { useWords } from "../lib/wording";

const OwnContext = createContext<{ ids: Set<string>; add: (id: string) => void }>({
  ids: new Set(),
  add: () => undefined,
});

/** Requests the PM handed in from this screen: they show at once instead of waiting behind "N new". */
export function OwnRequestsProvider(props: { children: ReactNode }) {
  const [ids, setIds] = useState<Set<string>>(new Set());
  const add = useCallback((id: string) => setIds((prev) => new Set([...prev, id])), []);
  return <OwnContext.Provider value={{ ids, add }}>{props.children}</OwnContext.Provider>;
}

export function useOwnRequests(): Set<string> {
  return useContext(OwnContext).ids;
}

/** Mark a request the PM just handed in from anywhere on the screen, so it shows at once. */
export function useAddOwnRequest(): (id: string) => void {
  return useContext(OwnContext).add;
}

const TEXT_FILE = /^text\/|\/(json|xml)$|message\/rfc822/;

export function HandIn(props: { onClose: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const own = useContext(OwnContext);
  const [note, setNote] = useState("");
  const [pasted, setPasted] = useState("");
  const [dropProblem, setDropProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const first = useRef<HTMLTextAreaElement>(null);
  useEffect(() => first.current?.focus(), []);

  const submit = async () => {
    setBusy(true);
    const handed = await act(
      () => api.handIn({ note, pasted }),
      () => ({ message: t("toast.handed_in") }),
    );
    setBusy(false);
    if (handed) {
      own.add(handed.request);
      props.onClose();
    }
  };

  const onDrop = async (event: React.DragEvent<HTMLTextAreaElement>) => {
    const files = Array.from(event.dataTransfer.files);
    if (!files.length) return;
    event.preventDefault();
    const readable = files.filter((f) => TEXT_FILE.test(f.type) || /\.(txt|md|eml|csv)$/i.test(f.name));
    setDropProblem(readable.length < files.length ? t("handin.drop_text_only") : "");
    const texts = await Promise.all(readable.map((f) => f.text()));
    if (texts.length) setPasted((prev) => [prev, ...texts].filter(Boolean).join("\n\n"));
  };

  return (
    <section className="panel" aria-labelledby="handin-title">
      <h2 id="handin-title">{t("handin.title")}</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") props.onClose();
        }}
      >
        <div className="field">
          <label htmlFor="handin-note">
            {t("handin.note")} <span className="hint">{t("handin.note_hint")}</span>
          </label>
          <textarea
            id="handin-note"
            className="short"
            ref={first}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder={t("handin.note_placeholder")}
          />
        </div>
        <div className="field">
          <label htmlFor="handin-pasted">
            {t("handin.pasted")} <span className="hint">{t("handin.pasted_hint")}</span>
          </label>
          <textarea
            id="handin-pasted"
            className="drop"
            value={pasted}
            onChange={(e) => setPasted(e.target.value)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => void onDrop(e)}
            placeholder={t("handin.pasted_placeholder")}
          />
          {dropProblem && (
            <p className="hint" role="status">
              {dropProblem}
            </p>
          )}
        </div>
        <div className="row-end">
          <button type="button" className="btn quiet" onClick={props.onClose}>
            {t("action.cancel")}
          </button>
          <button type="submit" className="btn primary" disabled={busy || !(note.trim() || pasted.trim())}>
            {t("handin.go")}
          </button>
        </div>
      </form>
    </section>
  );
}
