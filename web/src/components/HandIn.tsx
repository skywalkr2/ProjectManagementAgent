// Handing something in (design 7.6): one box, and a required choice of whose words are in it. "Someone else's" (the
// default) sends the box as pasted content (untrusted: material, never instructions) with an optional line saying what
// to do with it, which is the PM's own note (trusted). "Mine" sends the box as the PM's note. Either way the assistant
// always knows which words are the PM's. It opens as a drawer from the right (a full-screen sheet on a phone), so the screen
// it was opened from stays in view; closing it with words in the box asks first.
import { useQuery } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { projectChoices } from "../lib/project-choices";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Drawer } from "../ui/Drawer";
import { SegmentedControl } from "../ui/SegmentedControl";

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
/** How sensitive the person says it is: the usual sends nothing, so the workspace's own rules decide. */
type Sensitivity = "" | "internal" | "restricted";

export function HandIn(props: { onClose: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const own = useContext(OwnContext);
  const [text, setText] = useState("");
  const [whose, setWhose] = useState<Whose>("others");
  const [todo, setTodo] = useState("");
  const [sensitivity, setSensitivity] = useState<Sensitivity>("");
  const [project, setProject] = useState("");
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const choices = projectChoices(projects.data ?? [], (parent, name) => t("handin.project.path", { parent, name }));
  const [dropProblem, setDropProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const first = useRef<HTMLTextAreaElement>(null);
  useEffect(() => first.current?.focus(), []);

  const submit = async () => {
    setBusy(true);
    // Someone else's words are always material (pasted); only the PM's own words are ever sent as the note.
    const words = whose === "mine" ? { note: text, pasted: "" } : { note: todo, pasted: text };
    const body: S["HandIn"] = { ...words };
    if (sensitivity) body.data_level = sensitivity;
    if (project) body.project = project;
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

  // A picture on the clipboard can't be read (the assistant reads words): say so, and keep what is in the box. A paste that
  // carries its words as well is an ordinary paste of text.
  const onPaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const data = event.clipboardData;
    const pictures = Array.from(data?.files ?? []).filter((f) => f.type.startsWith("image/"));
    if (pictures.length === 0 || data.getData("text")) return;
    event.preventDefault();
    setDropProblem(t("handin.picture_not_read"));
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
    <Drawer
      open
      wide
      title={t("handin.title")}
      onClose={props.onClose}
      dirty={text.trim() !== "" || todo.trim() !== ""}
      footer={
        <>
          <Button variant="ghost" onClick={props.onClose}>
            {t("action.cancel")}
          </Button>
          <Button variant="primary" type="submit" form="handin-form" disabled={busy || !text.trim()}>
            {t("handin.go")}
          </Button>
        </>
      }
    >
      <form
        id="handin-form"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="field">
          <label htmlFor="handin-box">{t("handin.box")}</label>
          <textarea
            id="handin-box"
            className="drop big"
            ref={first}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setDropProblem("");
            }}
            onPaste={onPaste}
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
        <div className="field choice">
          <span aria-hidden="true">{t("handin.whose")}</span>
          <SegmentedControl
            label={t("handin.whose")}
            options={[
              { value: "others", label: t("handin.whose.others") },
              { value: "mine", label: t("handin.whose.mine") },
            ]}
            value={whose}
            onChange={setWhose}
          />
          <p className="hint">{t(whose === "mine" ? "handin.whose_hint.mine" : "handin.whose_hint.others")}</p>
        </div>
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
        <div className="field">
          <label htmlFor="handin-sensitivity">{t("handin.sensitivity")}</label>
          <select
            id="handin-sensitivity"
            value={sensitivity}
            aria-describedby="handin-sensitivity-hint"
            onChange={(e) => setSensitivity(e.target.value as Sensitivity)}
          >
            <option value="">{t("handin.sensitivity.usual")}</option>
            <option value="internal">{t("handin.sensitivity.internal")}</option>
            <option value="restricted">{t("handin.sensitivity.restricted")}</option>
          </select>
          <span id="handin-sensitivity-hint" className="hint">
            {t("handin.sensitivity_hint")}
          </span>
        </div>
        <div className="field">
          <label htmlFor="handin-project">{t("handin.project")}</label>
          <select
            id="handin-project"
            value={project}
            aria-describedby="handin-project-hint"
            onChange={(e) => setProject(e.target.value)}
          >
            <option value="">{t("handin.project.none")}</option>
            {choices.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
          <span id="handin-project-hint" className="hint">
            {t("handin.project_hint")}
          </span>
        </div>
      </form>
    </Drawer>
  );
}
