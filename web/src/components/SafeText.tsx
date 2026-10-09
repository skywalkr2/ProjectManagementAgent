// Rendering text that may come from outside content. Never raw HTML: everything is a text node. "- " lines become a
// list, "Label: url" lines become a named link, and every link shows its real domain so a label can't disguise it.
import type { ReactNode } from "react";
import { useWords } from "../lib/wording";

const LABELLED_LINK = /^(.{1,120}?):\s+(https?:\/\/\S+)$/;
const BARE_LINK = /^(https?:\/\/\S+)$/;

export function domainOf(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.host : null;
  } catch {
    return null;
  }
}

export function SafeLink(props: { label: string; url: string }) {
  const { t } = useWords();
  const host = domainOf(props.url);
  if (!host) return <>{props.label}</>;
  return (
    <span className="link">
      <a href={props.url} target="_blank" rel="noopener noreferrer">
        {props.label}
      </a>{" "}
      <span className="domain">{t("link.domain", { domain: host })}</span>
    </span>
  );
}

function line(text: string): ReactNode {
  const labelled = LABELLED_LINK.exec(text);
  if (labelled) return <SafeLink label={labelled[1]} url={labelled[2]} />;
  const bare = BARE_LINK.exec(text);
  if (bare) return <SafeLink label={domainOf(bare[1]) ?? bare[1]} url={bare[1]} />;
  return text;
}

export function SafeText(props: { text: string; className?: string }) {
  const blocks: ReactNode[] = [];
  let items: string[] = [];
  const flush = () => {
    if (items.length) {
      blocks.push(
        <ul key={`l${blocks.length}`}>
          {items.map((item, i) => (
            <li key={i}>{line(item)}</li>
          ))}
        </ul>,
      );
      items = [];
    }
  };
  for (const raw of props.text.split("\n")) {
    const text = raw.trimEnd();
    if (/^\s*-\s+/.test(text)) {
      items.push(text.replace(/^\s*-\s+/, ""));
      continue;
    }
    flush();
    if (text.trim()) blocks.push(<p key={`p${blocks.length}`}>{line(text)}</p>);
  }
  flush();
  return <div className={props.className ?? "safe-text"}>{blocks}</div>;
}

/** Find a quote in a text the way the server checks evidence: ignoring case, spacing and quote styles. */
export function findQuote(text: string, quote: string): [number, number] | null {
  const fold = (c: string) => c.replace(/[‘’]/g, "'").replace(/[“”]/g, '"').toLowerCase();
  const chars: string[] = [];
  const at: number[] = [];
  let space = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (/\s/.test(c)) {
      if (!space && chars.length) {
        chars.push(" ");
        at.push(i);
      }
      space = true;
      continue;
    }
    space = false;
    chars.push(fold(c));
    at.push(i);
  }
  const needle = fold(quote).replace(/\s+/g, " ").trim();
  if (!needle) return null;
  const start = chars.join("").indexOf(needle);
  if (start < 0) return null;
  return [at[start], at[start + needle.length - 1] + 1];
}

export function Highlighted(props: { text: string; quote: string }) {
  const { t } = useWords();
  const found = findQuote(props.text, props.quote);
  if (!found) return <div className="source-text">{props.text}</div>;
  const [start, end] = found;
  return (
    <div className="source-text">
      {props.text.slice(0, start)}
      <mark>
        <span className="sr">{t("source.quote_start")}</span>
        {props.text.slice(start, end)}
        <span className="sr">{t("source.quote_end")}</span>
      </mark>
      {props.text.slice(end)}
    </div>
  );
}
