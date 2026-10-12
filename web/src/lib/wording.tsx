// The wording sheet: every user-facing string comes from here, with overrides from the workspace's config/ui.yaml.
import { createContext, useContext, useMemo, type ReactNode } from "react";
import sheet from "../wording/en.json";

export type Words = Record<string, string>;
export type Vars = Record<string, string | number>;

const WordsContext = createContext<{ words: Words; base: Vars; overrides: Words; unnamed: boolean }>({
  words: sheet,
  base: {},
  overrides: {},
  unnamed: false,
});

/** The suffix of a variant of an entry used while the assistant still has the default name. */
const UNNAMED = ".unnamed";

export function format(words: Words, key: string, vars: Vars = {}): string {
  const template = words[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => (name in vars ? String(vars[name]) : match));
}

export function WordingProvider(props: {
  overrides?: Words;
  base?: Vars;
  /** The assistant still has the default name: an entry with an `.unnamed` variant reads that one. */
  unnamed?: boolean;
  children: ReactNode;
}) {
  const value = useMemo(
    () => ({
      words: { ...sheet, ...(props.overrides ?? {}) },
      base: props.base ?? {},
      overrides: props.overrides ?? {},
      unnamed: !!props.unnamed,
    }),
    [props.overrides, props.base, props.unnamed],
  );
  return <WordsContext.Provider value={value}>{props.children}</WordsContext.Provider>;
}

export function useWords() {
  const { words, base, overrides, unnamed } = useContext(WordsContext);
  return useMemo(() => {
    // A workspace's own wording for an entry wins over the sheet's variant for an unnamed assistant.
    const pick = (key: string) => (unnamed && !(key in overrides) && `${key}${UNNAMED}` in words ? `${key}${UNNAMED}` : key);
    const t = (key: string, vars: Vars = {}) => format(words, pick(key), { ...base, ...vars });
    const tn = (key: string, n: number, vars: Vars = {}) => t(`${key}.${n === 1 ? "one" : "other"}`, { n, ...vars });
    const has = (key: string) => key in words;
    return { t, tn, has };
  }, [words, base, overrides, unnamed]);
}
