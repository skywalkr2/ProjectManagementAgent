// Which screen is showing (design 7.1). Every view has a real link in the address's #fragment, so one build works at any
// base path with no server routes, and a view can be bookmarked and opened in a new tab:
//   #today  #work/changed  #work/followups  #work/outgoing  #work/stages  #work/panel/<name>
//   #records/projects  #records/people  #records/files  #records/panel/<name>  #records/<kind>/<id>
//   #sources  #addons  #settings  #setup (the guide)  #styleguide
// A `View` is that fragment, written without the "#" and with each name or id encoded, so two views compare with ===.
export type CoreView =
  | "today"
  | "work/changed"
  | "work/followups"
  | "work/outgoing"
  | "work/stages"
  | "records/projects"
  | "records/people"
  | "records/files"
  | "sources"
  | "addons"
  | "settings"
  | "setup"
  | "styleguide";
export type PanelGroup = "work" | "records";
export type View = CoreView | `${PanelGroup}/panel/${string}` | `records/${string}/${string}`;

export const CORE_VIEWS: readonly CoreView[] = [
  "today",
  "work/changed",
  "work/followups",
  "work/outgoing",
  "work/stages",
  "records/projects",
  "records/people",
  "records/files",
  "sources",
  "addons",
  "settings",
  "setup",
  "styleguide",
];

/** Fragments earlier versions used, and the view each still opens. */
const LEGACY: Record<string, CoreView> = {
  home: "today",
  stages: "work/stages",
  files: "records/files",
  sources: "sources",
  setup: "setup",
  welcome: "setup",
  settings: "settings",
  addons: "addons",
};

const enc = encodeURIComponent;

export const panelView = (name: string, group: PanelGroup = "work"): View => `${group}/panel/${enc(name)}`;
export const recordView = (kind: string, id: string): View => `records/${enc(kind)}/${enc(id)}`;

export type ParsedView =
  | { type: "core"; view: CoreView }
  | { type: "panel"; group: PanelGroup; name: string }
  | { type: "record"; kind: string; id: string };

export function parseView(view: View): ParsedView {
  if (view.startsWith("work/panel/") || view.startsWith("records/panel/")) {
    const group = view.startsWith("work/") ? "work" : "records";
    return { type: "panel", group, name: decodeURIComponent(view.slice(`${group}/panel/`.length)) };
  }
  if ((CORE_VIEWS as readonly string[]).includes(view)) return { type: "core", view: view as CoreView };
  const [, kind, id] = view.split("/");
  return { type: "record", kind: decodeURIComponent(kind), id: decodeURIComponent(id) };
}

/** The #fragment for a view (without the "#"). */
export const toHash = (view: View): string => view;

/** The view an address's #fragment names; anything unknown is Today. */
export function fromHash(hash: string): View {
  const text = hash.replace(/^#/, "");
  if (!text) return "today";
  if ((CORE_VIEWS as readonly string[]).includes(text)) return text as CoreView;
  try {
    // Fragments from earlier versions.
    if (text.startsWith("panel:")) {
      const name = decodeURIComponent(text.slice("panel:".length));
      return name ? panelView(name) : "today";
    }
    if (text.startsWith("record:")) {
      const [kind, ...rest] = text.slice("record:".length).split(":");
      const id = decodeURIComponent(rest.join(":"));
      const decoded = decodeURIComponent(kind);
      return decoded && id ? recordView(decoded, id) : "today";
    }
    if (text in LEGACY) return LEGACY[text];
    const parts = text.split("/");
    if (parts[0] === "work" && parts[1] === "panel" && parts.length > 2) {
      const name = decodeURIComponent(parts.slice(2).join("/"));
      return name ? panelView(name, "work") : "today";
    }
    if (parts[0] === "records" && parts.length > 2) {
      if (parts[1] === "panel") {
        const name = decodeURIComponent(parts.slice(2).join("/"));
        return name ? panelView(name, "records") : "today";
      }
      const kind = decodeURIComponent(parts[1]);
      const id = decodeURIComponent(parts.slice(2).join("/"));
      return kind && id ? recordView(kind, id) : "today";
    }
  } catch {
    return "today";
  }
  return "today";
}

/** An address for a view that works in a new tab and under any base path: this page's path and query, then the fragment. */
export function viewHref(view: View): string {
  return `${window.location.pathname}${window.location.search}#${toHash(view)}`;
}
