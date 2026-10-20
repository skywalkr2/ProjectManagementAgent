// Where a fact came from (design 7.14, answer 29): one label in the meta line that is itself the "Where it came from" link,
// and for what the assistant only worked out, a dashed "Inferred" tag and "Confirm it". No italics (they mean a quote here),
// and the label is never part of copied or published text: it is marked `data-copy="never"` and can't be selected, so
// what is copied from beside it is the fact alone. In a row's meta line it is drawn inline.
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { monthDay } from "../lib/dates";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Pill } from "../ui/Pill";
import { OriginLink } from "./Origin";
import styles from "./FactSource.module.css";

/** The label's words, from who the fact rests on: the person and the kind of input ("from <person>'s email, <day>"), never
 * the input's own title. */
export function useFactLabel(): (source: S["FactSource"]) => string {
  const { t, has } = useWords();
  return (source) => {
    const date = source.on ? monthDay(source.on) : "";
    const kind = source.kind && has(`fact.src.kind.${source.kind}`) ? source.kind : null;
    // "<person>'s email", "an email", or "something that came in" when the kind was never kept.
    const input = (name: string | null | undefined) =>
      kind ? (name ? t("fact.src.of", { name, kind: t(`fact.src.kind.${kind}`) }) : t(`fact.src.kind_a.${kind}`)) : t("fact.src.an_input");
    switch (source.basis) {
      case "person":
        return t("fact.src.person", { date });
      case "inferred":
        return t("fact.src.inferred", { input: input(source.sender), date });
      case "said":
        if (source.by && source.reported_by) return t("fact.src.reported", { name: source.by, input: input(source.reported_by), date });
        if (source.by) return t("fact.src.said", { input: input(source.by), date });
        return t("fact.src.said_unknown", { input: input(source.sender), date });
      default:
        return t("fact.src.old", { date });
    }
  };
}

export function FactSource(props: { source: S["FactSource"]; fact: string; version: number; /** Drawn in a line of text (a row's meta) instead of as a paragraph. */ inline?: boolean }) {
  const { t } = useWords();
  const act = useAct();
  const label = useFactLabel()(props.source);
  const inferred = props.source.basis === "inferred";
  const confirm = () =>
    act(
      () => api.editRecord({ kind: "fact", id: props.fact, fields: { basis: "person" }, read_version: props.version }),
      (done) => ({
        message: t("fact.confirmed"),
        undo: async () => {
          const report = await api.undo(done.changeset);
          if (!report.restored.length) throw new Error("not undone");
        },
      }),
    );
  const Tag = props.inline ? "span" : "p";
  return (
    <Tag className={styles.line} data-fact-source="" data-copy="never">
      {inferred && (
        <Pill inferred describedAs={t("fact.src.inferred_sr")}>
          {t("fact.inferred")}
        </Pill>
      )}
      {props.source.origin ? <OriginLink origin={props.source.origin} label={label} /> : <span>{label}</span>}
      {inferred && (
        <Button size="sm" variant="primary" onClick={() => void confirm()}>
          {t("fact.confirm")}
        </Button>
      )}
    </Tag>
  );
}
