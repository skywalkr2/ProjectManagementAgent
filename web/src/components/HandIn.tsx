// Handing something in (design 7.6): one box, and a required choice of whose words are in it. "Someone else's" (the
// default) sends the box as pasted content (untrusted: material, never instructions) with an optional line saying what
// to do with it, which is the PM's own note (trusted). "Mine" sends the box as the PM's note. Either way the assistant
// always knows which words are the PM's.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Label, Radio, RadioGroup, Text } from "react-aria-components";
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

type Whose = "others" | "mine";

export function HandIn(props: { onClose: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const own = useContext(OwnContext);
  const [text, setText] = useState("");
  const [whose, setWhose] = useState<Whose>("others");
  const [todo, setTodo] = useState("");
  const [dropProblem, setDropProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const first = useRef<HTMLTextAreaElement>(null);
  useEffect(() => first.current?.focus(), []);

  const submit = async () => {
    setBusy(true);
    // Someone else's words are always material (pasted); only the PM's own words are ever sent as the note.
    const body = whose === "mine" ? { note: text, pasted: "" } : { note: todo, pasted: text };
    const handed = await act(
      () => api.handIn(body),
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
    if (texts.length) setText((prev) => [prev, ...texts].filter(Boolean).join("\n\n"));
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
          <label htmlFor="handin-box">{t("handin.box")}</label>
          <textarea
            id="handin-box"
            className="drop big"
            ref={first}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => void onDrop(e)}
            placeholder={t("handin.box_placeholder")}
          />
          {dropProblem && (
            <p className="hint" role="status">
              {dropProblem}
            </p>
          )}
        </div>
        <RadioGroup
          className="field choice"
          value={whose}
          onChange={(v) => setWhose(v as Whose)}
          isRequired
          orientation="vertical"
        >
          <Label>{t("handin.whose")}</Label>
          <Radio value="others" className="radio">
            <span className="radio-dot" aria-hidden="true" />
            <span>{t("handin.whose.others")}</span>
          </Radio>
          <Radio value="mine" className="radio">
            <span className="radio-dot" aria-hidden="true" />
            <span>{t("handin.whose.mine")}</span>
          </Radio>
          <Text slot="description" className="hint">
            {t(whose === "mine" ? "handin.whose_hint.mine" : "handin.whose_hint.others")}
          </Text>
        </RadioGroup>
        {whose === "others" && (
          <div className="field">
            <label htmlFor="handin-todo">{t("handin.todo")}</label>
            <input
              id="handin-todo"
              type="text"
              value={todo}
              onChange={(e) => setTodo(e.target.value)}
              placeholder={t("handin.todo_placeholder")}
            />
          </div>
        )}
        <div className="row-end">
          <button type="button" className="btn quiet" onClick={props.onClose}>
            {t("action.cancel")}
          </button>
          <button type="submit" className="btn primary" disabled={busy || !text.trim()}>
            {t("handin.go")}
          </button>
        </div>
      </form>
    </section>
  );
}
