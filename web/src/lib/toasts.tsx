// Undo toasts: reversible actions happen at once and offer Undo here instead of asking first. The last undo is also
// reachable from the keyboard, and F6 moves the cursor to the toasts, where Escape puts one away. A toast stays until
// dismissed when the configured time is 0, and waits while the pointer or the cursor is on it. The same message pushed
// again is one toast with a count, so a run of identical actions never grows the stack.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Icon } from "../ui/Icon";
import { useWords } from "./wording";
import styles from "./toasts.module.css";

export interface ToastInput {
  message: string;
  undo?: () => Promise<unknown> | void;
  action?: { label: string; run: () => Promise<unknown> | void };
  /** More choices beside `action`, each a button of its own. */
  more?: Array<{ label: string; run: () => Promise<unknown> | void }>;
  /** What the message says when the same one has been pushed `n` times in a row; without it the count follows the message. */
  many?: (n: number) => string;
}

interface Toast extends ToastInput {
  id: number;
  /** How many times this message was pushed while it showed. */
  count: number;
  /** The undo of each of those pushes that had one, the newest last. */
  undoTokens: number[];
}

interface ToastApi {
  push: (toast: ToastInput) => void;
  undoLast: () => void;
  /** Takes every toast off the screen, for a screen that replaces the one they were about. */
  dismissAll: () => void;
}

const ToastContext = createContext<ToastApi>({ push: () => undefined, undoLast: () => undefined, dismissAll: () => undefined });

export function useToasts(): ToastApi {
  return useContext(ToastContext);
}

const CountContext = createContext(0);

/** How many toasts show now, for a screen that keeps its own buttons clear of them. */
export function useToastCount(): number {
  return useContext(CountContext);
}

const MAX_SHOWN = 3;

export function ToastProvider(props: { seconds: number; children: ReactNode }) {
  const { t } = useWords();
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);
  const undos = useRef<Array<{ token: number; run: () => Promise<unknown> | void }>>([]);
  const nextToken = useRef(1);
  const stack = useRef<HTMLDivElement>(null);

  const dismiss = useCallback((id: number) => setToasts((all) => all.filter((x) => x.id !== id)), []);

  const dismissAll = useCallback(() => {
    setToasts([]);
  }, []);

  // How many toasts show is told to the page, so a full-window screen can keep its own buttons clear of them.
  useEffect(() => {
    const root = document.documentElement;
    if (toasts.length === 0) return;
    root.style.setProperty("--toasts", String(toasts.length));
    root.setAttribute("data-toasts", "");
    return () => {
      root.style.removeProperty("--toasts");
      root.removeAttribute("data-toasts");
    };
  }, [toasts.length]);

  const push = useCallback((toast: ToastInput) => {
    const token = toast.undo ? nextToken.current++ : 0;
    if (toast.undo) undos.current.push({ token, run: toast.undo });
    setToasts((all) => {
      const last = all[all.length - 1];
      if (last && last.message === toast.message && !toast.action && !last.action) {
        const merged: Toast = { ...last, many: toast.many ?? last.many, count: last.count + 1, undoTokens: token ? [...last.undoTokens, token] : last.undoTokens };
        return [...all.slice(0, -1), merged];
      }
      return [...all, { ...toast, id: next.current++, count: 1, undoTokens: token ? [token] : [] }].slice(-MAX_SHOWN);
    });
  }, []);

  // Takes one undo out of the toast that holds it: the toast shows a count one lower, or goes when it was the last.
  const spend = useCallback((token: number) => {
    undos.current = undos.current.filter((u) => u.token !== token);
    setToasts((all) =>
      all.flatMap((x) => {
        if (!x.undoTokens.includes(token)) return [x];
        if (x.count <= 1) return [];
        return [{ ...x, count: x.count - 1, undoTokens: x.undoTokens.filter((k) => k !== token) }];
      }),
    );
  }, []);

  const runUndo = useCallback(
    async (token: number, run: () => Promise<unknown> | void) => {
      spend(token);
      try {
        await run();
        push({ message: t("toast.undone") });
      } catch {
        push({ message: t("toast.undo_failed") });
      }
    },
    [spend, push, t],
  );

  const undoLast = useCallback(() => {
    const last = undos.current.pop();
    if (!last) {
      push({ message: t("toast.nothing_to_undo") });
      return;
    }
    void runUndo(last.token, last.run);
  }, [push, runUndo, t]);

  // The stack's height is told to the page, so the content keeps room under its last row and a row the cursor reaches
  // scrolls clear of the toasts (design 7.6).
  useEffect(() => {
    const root = document.documentElement;
    const el = stack.current;
    if (toasts.length === 0 || !el) return;
    const measure = () => root.style.setProperty("--toast-h", `${Math.ceil(el.getBoundingClientRect().height)}px`);
    measure();
    if (typeof ResizeObserver === "undefined") return () => root.style.removeProperty("--toast-h");
    const watch = new ResizeObserver(measure);
    watch.observe(el);
    return () => {
      watch.disconnect();
      root.style.removeProperty("--toast-h");
    };
  }, [toasts.length]);

  // F6 reaches the toasts, and Escape on one puts it away and gives the cursor back to where it was.
  const came = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "F6" || event.defaultPrevented) return;
      const region = stack.current;
      const target = region?.querySelector<HTMLElement>("[data-toast]:last-child button");
      if (!region || !target) return;
      event.preventDefault();
      if (region.contains(document.activeElement)) {
        came.current?.focus();
        return;
      }
      came.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      target.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  const away = useCallback(
    (id: number) => {
      const inside = stack.current?.contains(document.activeElement);
      dismiss(id);
      if (inside) {
        const back = came.current;
        came.current = null;
        if (back && document.contains(back)) back.focus();
        else (document.querySelector<HTMLElement>("main") ?? document.body).focus();
      }
    },
    [dismiss],
  );

  const value = useMemo(() => ({ push, undoLast, dismissAll }), [push, undoLast, dismissAll]);

  return (
    <ToastContext.Provider value={value}>
      <CountContext.Provider value={toasts.length}>{props.children}</CountContext.Provider>
      {/* Marked as a top layer so a dialog that is open keeps these messages in the page's reading order for screen readers. */}
      <section className={styles.region} aria-label={t("toast.region")} data-react-aria-top-layer="" data-toast-region="">
        <div ref={stack} aria-live="polite" className={styles.stack}>
          {toasts.map((toast) => (
            <ToastView
              key={toast.id}
              toast={toast}
              seconds={props.seconds}
              onDismiss={() => dismiss(toast.id)}
              onEscape={() => away(toast.id)}
              onUndo={toast.undoTokens.length > 0 ? () => { const token = toast.undoTokens[toast.undoTokens.length - 1]; const run = undos.current.find((u) => u.token === token)?.run; if (run) void runUndo(token, run); } : undefined}
            />
          ))}
        </div>
      </section>
    </ToastContext.Provider>
  );
}

function ToastView(props: { toast: Toast; seconds: number; onDismiss: () => void; onEscape: () => void; onUndo?: () => void }) {
  const { t } = useWords();
  const [over, setOver] = useState(false);
  const [within, setWithin] = useState(false);
  const { seconds, onDismiss } = props;
  const { count } = props.toast;
  const held = over || within;
  // Reduced motion means no animation, not longer messages: the time is the setting's, and it starts again when the
  // message is pushed once more.
  useEffect(() => {
    if (held || seconds <= 0) return;
    const timer = window.setTimeout(onDismiss, seconds * 1000);
    return () => window.clearTimeout(timer);
  }, [held, seconds, onDismiss, count]);
  const actions = [props.toast.action, ...(props.toast.more ?? [])].filter((a): a is NonNullable<typeof a> => !!a);
  const message =
    count > 1 ? (props.toast.many ? props.toast.many(count) : t("toast.repeated", { message: props.toast.message, n: count })) : props.toast.message;
  return (
    <div
      className={styles.toast}
      data-toast=""
      onMouseEnter={() => setOver(true)}
      onMouseLeave={() => setOver(false)}
      onFocus={() => setWithin(true)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setWithin(false);
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          props.onEscape();
        }
      }}
    >
      <span className={styles.message}>{message}</span>
      {actions.map((action) => (
        <button
          key={action.label}
          type="button"
          className={styles.action}
          onClick={() => {
            props.onDismiss();
            void action.run();
          }}
        >
          {action.label}
        </button>
      ))}
      {props.onUndo && (
        <button type="button" className={styles.action} onClick={props.onUndo}>
          {count > 1 ? t("toast.undo_last") : t("toast.undo")}
        </button>
      )}
      <button type="button" className={styles.dismiss} aria-label={t("toast.dismiss")} onClick={props.onDismiss}>
        <Icon name="close" size={16} />
      </button>
    </div>
  );
}
