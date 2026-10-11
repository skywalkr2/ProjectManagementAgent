// Which screen is showing. The core's screens have fixed names; a plugin's panel is "panel:<name>" and any record's
// page is "record:<kind>:<id>". The address's #fragment carries it, each part encoded, so a refresh keeps the screen.
export type CoreView = "home" | "stages" | "files" | "sources" | "setup" | "welcome" | "settings" | "addons";
export type View = CoreView | `panel:${string}` | `record:${string}:${string}`;

const CORE: readonly string[] = ["home", "stages", "files", "sources", "setup", "welcome", "settings", "addons"];

export const panelView = (name: string): View => `panel:${name}`;
export const recordView = (kind: string, id: string): View => `record:${kind}:${id}`;

export type ParsedView =
  | { type: "core"; view: CoreView }
  | { type: "panel"; name: string }
  | { type: "record"; kind: string; id: string };

export function parseView(view: View): ParsedView {
  if (view.startsWith("panel:")) return { type: "panel", name: view.slice("panel:".length) };
  if (view.startsWith("record:")) {
    const rest = view.slice("record:".length);
    const at = rest.indexOf(":");
    return { type: "record", kind: rest.slice(0, at), id: rest.slice(at + 1) };
  }
  return { type: "core", view: view as CoreView };
}

/** The #fragment for a view (without the "#"). Home has none. */
export function toHash(view: View): string {
  const parsed = parseView(view);
  if (parsed.type === "panel") return `panel:${encodeURIComponent(parsed.name)}`;
  if (parsed.type === "record") return `record:${encodeURIComponent(parsed.kind)}:${encodeURIComponent(parsed.id)}`;
  return parsed.view === "home" ? "" : parsed.view;
}

/** The view an address's #fragment names; anything unknown is home. */
export function fromHash(hash: string): View {
  const text = hash.replace(/^#/, "");
  try {
    if (text.startsWith("panel:")) {
      const name = decodeURIComponent(text.slice("panel:".length));
      return name ? panelView(name) : "home";
    }
    if (text.startsWith("record:")) {
      const [kind, ...rest] = text.slice("record:".length).split(":");
      const id = decodeURIComponent(rest.join(":"));
      const decoded = decodeURIComponent(kind);
      return decoded && id ? recordView(decoded, id) : "home";
    }
  } catch {
    return "home";
  }
  return CORE.includes(text) ? (text as CoreView) : "home";
}
