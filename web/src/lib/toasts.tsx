// Undo toasts: reversible actions happen at once and offer Undo here instead of asking first. The last undo is also
// reachable from the keyboard. Toasts stay until dismissed when the configured time is 0 or motion is reduced.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Icon } from "../ui/Icon";
import { useWords } from "./wording";
import styles from "./toasts.module.css";

export interface ToastInput {
  message: string;
  undo?: () => Promise<unknown> | void;
  action?: { label: string; run: () => Promise<unknown> | void };
}

interface Toast extends ToastInput {
  id: number;
}

interface ToastApi {
  push: (toast: ToastInput) => void;
  undoLast: () => void;
}

const ToastContext = createContext<ToastApi>({ push: () => undefined, undoLast: () => undefined });

export function useToasts(): ToastApi {
  return useContext(ToastContext);
}

const MAX_SHOWN = 3;

export function ToastProvider(props: { seconds: number; children: ReactNode }) {
  const { t } = useWords();
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);
  const undos = useRef<Array<{ id: number; run: () => Promise<unknown> | void }>>([]);

  const dismiss = useCallback((id: number) => setToasts((all) => all.filter((x) => x.id !== id)), []);

  const push = useCallback((toast: ToastInput) => {
    const id = next.current++;
    if (toast.undo) undos.current.push({ id, run: toast.undo });
    setToasts((all) => [...all, { ...toast, id }].slice(-MAX_SHOWN));
  }, []);

  const runUndo = useCallback(
    async (id: number, run: () => Promise<unknown> | void) => {
      undos.current = undos.current.filter((u) => u.id !== id);
      dismiss(id);
      try {
        await run();
        push({ message: t("toast.undone") });
      } catch {
        push({ message: t("toast.undo_failed") });
      }
    },
    [dismiss, push, t],
  );

  const undoLast = useCallback(() => {
    const last = undos.current.pop();
    if (!last) {
      push({ message: t("toast.nothing_to_undo") });
      return;
    }
    void runUndo(last.id, last.run);
  }, [push, runUndo, t]);

  const value = useMemo(() => ({ push, undoLast }), [push, undoLast]);

  return (
    <ToastContext.Provider value={value}>
      {props.children}
      {/* Marked as a top layer so a dialog that is open keeps these messages in the page's reading order for screen readers. */}
      <section className={styles.region} aria-label={t("toast.region")} data-react-aria-top-layer="">
        <div aria-live="polite" className={styles.stack}>
          {toasts.map((toast) => (
            <ToastView
              key={toast.id}
              toast={toast}
              seconds={props.seconds}
              onDismiss={() => dismiss(toast.id)}
              onUndo={toast.undo ? () => void runUndo(toast.id, toast.undo!) : undefined}
            />
          ))}
        </div>
      </section>
    </ToastContext.Provider>
  );
}

function ToastView(props: { toast: Toast; seconds: number; onDismiss: () => void; onUndo?: () => void }) {
  const { t } = useWords();
  const [held, setHeld] = useState(false);
  const { seconds, onDismiss } = props;
  useEffect(() => {
    const reduce = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (held || seconds <= 0 || reduce) return;
    const timer = window.setTimeout(onDismiss, seconds * 1000);
    return () => window.clearTimeout(timer);
  }, [held, seconds, onDismiss]);
  const action = props.toast.action;
  return (
    <div className={styles.toast} onMouseEnter={() => setHeld(true)} onFocus={() => setHeld(true)}>
      <span className={styles.message}>{props.toast.message}</span>
      {action && (
        <button
          type="button"
          className={styles.action}
          onClick={() => {
            props.onDismiss();
            void action.run();
          }}
        >
          {action.label}
        </button>
      )}
      {props.onUndo && (
        <button type="button" className={styles.action} onClick={props.onUndo}>
          {t("toast.undo")}
        </button>
      )}
      <button type="button" className={styles.dismiss} aria-label={t("toast.dismiss")} onClick={props.onDismiss}>
        <Icon name="close" size={16} />
      </button>
    </div>
  );
}
