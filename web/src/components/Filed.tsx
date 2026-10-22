// Why the assistant filed an item under a project when words or the sender's mail domain did it (design 6.32), said in
// words, and the one step that moves it to the other side as the person: an edit of the item's own project with Undo,
// which the server records as a correction like any other change of a field the assistant set.
import { api, type S } from "../lib/api";
import { useAct } from "../lib/act";
import { useWords } from "../lib/wording";

type T = (key: string, vars?: Record<string, string | number>) => string;
type Filed = S["FiledView"];

/** "Filed under <project>: it names <word>", or "it's from <domain>" when the sender's domain placed it. */
export function filedWords(filed: Filed, t: T): string {
  const vars = { project: filed.project_name, word: filed.word ?? "" };
  return filed.by === "domain" ? t("filed.from", vars) : t("filed.names", vars);
}

/** Moves an item to the top project of the other side; the toast says so and has Undo. */
export function useMoveFiled() {
  const act = useAct();
  const { t } = useWords();
  return (kind: string, id: string, filed: Filed) => {
    const to = filed.move_to;
    if (!to) return Promise.resolve(undefined);
    return act(
      () => api.editRecord({ kind, id, fields: { [filed.field]: filed.field === "projects" ? [to] : to }, read_version: filed.version }),
      (done) => ({
        message: t("filed.moved", { project: filed.move_to_name ?? "" }),
        undo: async () => {
          const report = await api.undo(done.changeset);
          if (!report.restored.length) throw new Error("not undone");
        },
      }),
    );
  };
}

/** The line on an item's page: why it is where it is, and the button that moves it to the other side. */
export function FiledLine(props: { kind: string; id: string; filed: Filed }) {
  const { t } = useWords();
  const move = useMoveFiled();
  const { filed } = props;
  return (
    <p className="filed-line" data-filed-by={filed.by}>
      <span>{filedWords(filed, t)}</span>
      {filed.move_to && (
        <>
          {" "}
          <button type="button" className="btn small" onClick={() => void move(props.kind, props.id, filed)}>
            {t("filed.move", { project: filed.move_to_name ?? "" })}
          </button>
        </>
      )}
    </p>
  );
}
