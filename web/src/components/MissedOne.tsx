// Missed one (design 6.32): the person says in a plain sentence what the assistant missed. One small form with one field,
// reachable from the header on every screen, the phone's More sheet, and Today's and the changes list's empty states.
// The cursor starts in the field, Enter sends, Escape closes. After sending, a toast thanks them and points at the work
// it made; the request's own changes have their own Undo, so there is none here.
import { useQuery } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { Heading } from "react-aria-components";
import { api } from "../lib/api";
import { useAct } from "../lib/act";
import { toHash } from "../lib/views";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { useAddOwnRequest } from "./HandIn";
import { ModalPanel, restoreFocus } from "./ModalPanel";

/** Whether there is anything the assistant could have missed yet: something has been handed in or read, so a change exists.
 * On a new workspace, before any input has been read, the header offers no "Missed one". */
export function useAnythingToMiss(): boolean {
  const changes = useQuery({ queryKey: ["changes"], queryFn: api.changes });
  return (changes.data?.length ?? 0) > 0;
}

/** Marks every control that opens the form, so focus can go back to one when it closes. */
export const MISSED_BUTTON = "data-missed-button";

const OpenContext = createContext<() => void>(() => undefined);

/** Opens the form from wherever the person is. */
export function useMissedOne(): () => void {
  return useContext(OpenContext);
}

/** Holds the form for the whole app, so any screen can open it and it keeps what was typed while it is open. */
export function MissedOneProvider(props: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLElement | null>(null);
  const show = useCallback(() => {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setOpen(true);
  }, []);
  const value = useMemo(() => show, [show]);
  return (
    <OpenContext.Provider value={value}>
      {props.children}
      {open && (
        <MissedOne
          onClose={() => {
            setOpen(false);
            restoreFocus(() => (opener.current?.isConnected ? opener.current : document.querySelector<HTMLElement>(`[${MISSED_BUTTON}]`)));
          }}
        />
      )}
    </OpenContext.Provider>
  );
}

export function MissedOne(props: { onClose: () => void }) {
  const { t } = useWords();
  const act = useAct();
  const own = useAddOwnRequest();
  const base = useId();
  const field = useRef<HTMLTextAreaElement>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => field.current?.focus(), []);

  const submit = async () => {
    const words = text.trim();
    if (!words || busy) return;
    setBusy(true);
    const sent = await act(
      () => api.missed(words),
      () => ({
        message: t("missed.toast"),
        action: {
          label: t("missed.see"),
          run: () => {
            window.location.hash = toHash("work/changed");
          },
        },
      }),
    );
    setBusy(false);
    if (sent) {
      own(sent.request);
      props.onClose();
    }
  };

  const titleId = `${base}-title`;
  return (
    <ModalPanel titleId={titleId} onClose={props.onClose}>
      <Heading slot="title" id={titleId}>
        {t("missed.title")}
      </Heading>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="field">
          <label htmlFor={`${base}-text`}>{t("missed.label")}</label>
          <textarea
            id={`${base}-text`}
            ref={field}
            className="short"
            value={text}
            aria-describedby={`${base}-hint`}
            placeholder={t("missed.placeholder")}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              // Enter sends; Shift+Enter starts a new line.
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void submit();
              }
            }}
          />
          <span id={`${base}-hint`} className="hint">
            {t("missed.hint")}
          </span>
        </div>
        <div className="row-end">
          <button type="button" className="btn quiet" onClick={props.onClose}>
            {t("action.cancel")}
          </button>
          <button type="submit" className="btn primary" disabled={busy || !text.trim()}>
            {t(busy ? "missed.sending" : "missed.go")}
          </button>
        </div>
      </form>
    </ModalPanel>
  );
}

/** The button that opens the form, for an empty state or a menu. */
export function MissedOneButton(props: { size?: "md" | "sm" }) {
  const { t } = useWords();
  const open = useMissedOne();
  return (
    <Button size={props.size} {...{ [MISSED_BUTTON]: "" }} onClick={open}>
      {t("missed.open")}
    </Button>
  );
}

/** A line for a quiet screen: the question and the button that opens the form. */
export function MissedOneLine(props: { className?: string }) {
  const { t } = useWords();
  return (
    <p className={props.className} data-missed-line="">
      {t("missed.prompt")} <MissedOneButton size="sm" />
    </p>
  );
}
