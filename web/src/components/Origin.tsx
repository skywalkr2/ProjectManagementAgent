// "Where it came from" on an action, a question or a decision (design 7.5). The server decides what exists, in this
// order: the original page (shown with its real domain), the saved text of the input, or the change that made the item
// with the request behind it in What changed. An item with no origin shows no link.
import { useQuery } from "@tanstack/react-query";
import { useId, useRef, useState } from "react";
import { api, type S } from "../lib/api";
import { dayAndTime } from "../lib/dates";
import { revealOrKeep } from "../lib/reveal";
import { toHash } from "../lib/views";
import { useWords } from "../lib/wording";
import { ModalPanel, restoreFocus } from "./ModalPanel";
import { SafeLink } from "./SafeText";
import { SourceLimit } from "./SourceLimit";

/** Whether an origin has a link to show: a line that holds it must not leave a dot beside nothing when it has none. */
export function hasOrigin(origin?: S["Origin"] | null): boolean {
  if (!origin) return false;
  return (origin.kind === "link" && !!origin.url) || (origin.kind === "source" && !!origin.source) || (origin.kind === "change" && !!origin.changeset);
}

export function OriginLink(props: { origin?: S["Origin"] | null; /** The link's words, when they are more than "Where it came from". */ label?: string }) {
  const { t } = useWords();
  const origin = props.origin;
  if (!origin) return null;
  if (origin.kind === "link" && origin.url) {
    return (
      <div className="origin">
        <SafeLink label={props.label ?? t("origin.link")} url={origin.url} />
      </div>
    );
  }
  if (origin.kind === "source" && origin.source) return <SourceLink source={origin.source} label={props.label} />;
  if (origin.kind === "change" && origin.changeset) return <ChangeLink changeset={origin.changeset} label={props.label} />;
  return null;
}

/** Opens the saved text of the input in a dialog. */
function SourceLink(props: { source: string; label?: string }) {
  const { t } = useWords();
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const close = () => {
    setOpen(false);
    restoreFocus(() => button.current);
  };
  return (
    <div className="origin">
      <button ref={button} type="button" className="link-button" aria-haspopup="dialog" onClick={() => setOpen(true)}>
        {props.label ?? t("origin.link")}
      </button>
      {open && <SourceDialog source={props.source} onClose={close} />}
    </div>
  );
}

function SourceDialog(props: { source: string; onClose: () => void }) {
  const { t } = useWords();
  const titleId = useId();
  const source = useQuery({ queryKey: ["source", props.source], queryFn: () => api.source(props.source) });
  const s = source.data;
  return (
    <ModalPanel titleId={titleId} onClose={props.onClose} dismissable>
      <h2 id={titleId}>{t("origin.title")}</h2>
      {source.isPending ? (
        <p>{t("loading")}</p>
      ) : source.isError || !s ? (
        <p className="hint">{t("source.missing")}</p>
      ) : (
        <div className="source">
          <div className="src">
            {s.title} · {dayAndTime(s.received_at)}
            {s.trust === "untrusted" && <span className="tag">{t("source.outside")}</span>}
          </div>
          {s.limit && <SourceLimit source={props.source} limit={s.limit} />}
          {s.text ? <div className="source-text">{s.text}</div> : <p className="hint">{t("source.not_kept")}</p>}
        </div>
      )}
      <div className="row-end">
        <button type="button" className="btn primary" autoFocus onClick={props.onClose}>
          {t("origin.close")}
        </button>
      </div>
    </ModalPanel>
  );
}

/** Opens the change in What changed: on this screen when the list is here, else on that screen. */
function ChangeLink(props: { changeset: string; label?: string }) {
  const { t } = useWords();
  return (
    <div className="origin">
      <button
        type="button"
        className="link-button"
        onClick={() => {
          if (!revealOrKeep("changeset", props.changeset)) window.location.hash = toHash("work/changed");
        }}
      >
        {props.label ?? t("origin.link")}
      </button>
    </div>
  );
}
