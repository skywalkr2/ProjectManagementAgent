// The starting templates for kinds of items of your own (design 3.10): what each adds, and one button to use it. The
// setup guide's template step and Ask's offer to keep track of something of your own both show this list.
import { useQuery } from "@tanstack/react-query";
import { useId, useState } from "react";
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useRestart } from "../lib/restart";
import { useWords } from "../lib/wording";
import { Skeleton } from "../ui/Skeleton";

export function TemplateList() {
  const { t } = useWords();
  const act = useAct();
  const restart = useRestart();
  const templates = useQuery({ queryKey: ["templates"], queryFn: api.templates });
  const [busy, setBusy] = useState(false);
  if (templates.isPending) return <Skeleton />;
  if (templates.isError || !templates.data.length) return <p className="empty">{t("welcome.template.none")}</p>;
  const apply = async (template: S["TemplateView"]) => {
    setBusy(true);
    const done = await act(
      () => api.applyTemplate(template.id),
      () => ({ message: t("welcome.template.applied", { name: template.name }) }),
    );
    setBusy(false);
    if (done?.needs_restart) restart.offer();
  };
  return (
    <ul className="queue">
      {templates.data.map((tpl) => {
        const adds = tpl.adds ?? [];
        const addsId = `template-${tpl.id.replace(/[^A-Za-z0-9_-]/g, "-")}-adds`;
        return (
          <li key={tpl.id} className="line">
            <div className="row pair">
              <div className="text">
                <strong>{tpl.name}</strong>
                {tpl.description && <span className="sub">{tpl.description}</span>}
                {adds.length > 0 && (
                  <div className="template-adds">
                    <span className="what" id={addsId}>
                      {t("welcome.template.adds")}
                    </span>
                    <ul className="plain-list" aria-labelledby={addsId}>
                      {adds.map((add) => (
                        <li key={add.name}>
                          <strong>{add.name}</strong>
                          {(add.fields.length > 0 || add.stages.length > 0) && (
                            <ul className="plain-list">
                              {add.fields.length > 0 && <li>{t("welcome.template.fields", { list: add.fields.join(", ") })}</li>}
                              {add.stages.length > 0 && (
                                <li>{t("welcome.template.steps", { list: add.stages.join(t("welcome.template.step_join")) })}</li>
                              )}
                            </ul>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
              <div className="acts">
                {tpl.set_up ? (
                  <span className="template-set-up">
                    <span aria-hidden="true">✓ </span>
                    {t("welcome.template.set_up")}
                  </span>
                ) : (
                  <button
                    type="button"
                    className="btn"
                    disabled={busy}
                    aria-label={t("welcome.template.apply_named", { name: tpl.name })}
                    onClick={() => void apply(tpl)}
                  >
                    {t("welcome.template.apply")}
                  </button>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** Under Ask's box: a line that opens the starting templates for keeping track of something of your own, so the app's
 * define-your-own kit is offered where it is wanted and not as an add-on to turn on. Nothing is read until it is opened. */
export function OwnKindsOffer() {
  const { t } = useWords();
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className="own-kinds">
      <button type="button" className="link-button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        {t("own_kinds.offer")}
      </button>
      <div id={id} hidden={!open}>
        {open && (
          <>
            <p className="hint">{t("own_kinds.hint")}</p>
            <TemplateList />
          </>
        )}
      </div>
    </div>
  );
}
