// The API client. Types come from the server's OpenAPI schema (npm run gen:api), so a changed field fails the build.
// Paths are relative: the page's <base> points at the configured base path, so the same build works under any path.
import type { components } from "../api/schema";

export type S = components["schemas"];

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail || `HTTP ${status}`);
  }
}

async function send<T>(method: "GET" | "POST" | "DELETE", path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`api/${path}`, { method, credentials: "same-origin", ...init });
  if (!response.ok) {
    let detail = "";
    try {
      const data = (await response.json()) as { detail?: unknown; error?: unknown };
      detail = typeof data.detail === "string" ? data.detail : typeof data.error === "string" ? data.error : "";
    } catch {
      detail = "";
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

async function call<T>(method: "GET" | "POST" | "DELETE", path: string, body?: unknown): Promise<T> {
  if (body === undefined) return send<T>(method, path, { headers: {} });
  return send<T>(method, path, { headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
}

/** Details of a file being added; they go in the address, and the file's own bytes are the request body. */
export interface FileUpload {
  kind: string;
  project?: string | null;
  meta?: Record<string, unknown>;
  replaces?: string | null;
}

const id = encodeURIComponent;
/** A namespaced name such as "plugin/name" keeps its slash; each part is encoded. */
const named = (name: string) => name.split("/").map(id).join("/");

export const api = {
  runtimeConfig: () => call<S["RuntimeConfig"]>("GET", "runtime-config"),
  status: () => call<S["Status"]>("GET", "status"),
  restart: () => call<S["RestartAsked"]>("POST", "restart"),
  changes: () => call<S["ChangeItem"][]>("GET", "changes"),
  source: (src: string) => call<S["SourceView"]>("GET", `sources/${id(src)}`),
  followups: () => call<S["FollowupSection"][]>("GET", "followups"),

  watchSources: () => call<S["WatchSourceView"][]>("GET", "watch"),
  readSource: (src: string) => call<S["WatchSourceView"]>("POST", `watch/${id(src)}/read`),
  autoClosed: () => call<S["AutoClosedView"][]>("GET", "auto-closed"),
  closerLook: (req: string, readVersion: number) =>
    call<S["Created"]>("POST", `requests/${id(req)}/closer-look`, { read_version: readVersion }),

  ask: (question: string) => call<S["Created"]>("POST", "ask", { question }),
  asks: () => call<S["AskView"][]>("GET", "asks"),
  applyProposal: (proposal: string, body: S["ProposalApply"]) =>
    call<S["SettingsSaved"]>("POST", `setting-proposals/${id(proposal)}/apply`, body),
  dismissProposal: (proposal: string, readVersion: number) =>
    call<S["Created"]>("POST", `setting-proposals/${id(proposal)}/dismiss`, { read_version: readVersion }),
  reportSent: (report: string, readVersion: number) =>
    call<S["Created"]>("POST", `reports/${id(report)}/sent`, { read_version: readVersion }),
  dismissReport: (report: string, readVersion: number) =>
    call<S["Created"]>("POST", `reports/${id(report)}/dismiss`, { read_version: readVersion }),
  people: () => call<S["PersonView"][]>("GET", "people"),

  stageRecords: () => call<S["StageView"][]>("GET", "stages/records"),
  stageReady: () => call<S["StageView"][]>("GET", "stages/ready"),
  stageRequests: () => call<S["StageRequestView"][]>("GET", "stages/requests"),
  stageHistory: (kind: string, record: string) =>
    call<S["StageHistoryEntry"][]>("GET", `records/${id(record)}/stage-history?kind=${id(kind)}`),
  stageMove: (body: S["StageMove"]) => call<S["StageMoved"]>("POST", "stages/move", body),
  stageGo: (request: string, readVersion: number) =>
    call<S["Ok"]>("POST", `requests/${id(request)}/go`, { read_version: readVersion }),

  handIn: (body: S["HandIn"]) => call<S["Handed"]>("POST", "handin", body),
  looksGood: (cs: string) => call<S["Ok"]>("POST", `changesets/${id(cs)}/looks-good`),
  reopen: (cs: string) => call<S["Ok"]>("POST", `changesets/${id(cs)}/reopen`),
  undo: (cs: string, ops?: number[]) => call<S["UndoReport"]>("POST", `changesets/${id(cs)}/undo`, { ops: ops ?? null }),
  sendBack: (cs: string, note: string) => call<S["Requeued"]>("POST", `changesets/${id(cs)}/send-back`, { note }),
  release: (cs: string, index: number, person?: string) =>
    call<S["Ok"]>("POST", `changesets/${id(cs)}/ops/${index}/release`, { person: person ?? null }),
  answer: (q: string, body: S["Answer"]) => call<S["Ok"]>("POST", `questions/${id(q)}/answer`, body),
  actionStatus: (a: string, status: S["ActionState"]["status"]) =>
    call<S["Ok"]>("POST", `actions/${id(a)}/status`, { status }),
  reply: (q: string, text: string) => call<S["Handed"]>("POST", `questions/${id(q)}/reply`, { text }),
  retry: (req: string, use?: string) =>
    call<S["Ok"]>("POST", `requests/${id(req)}/retry`, use ? { use } : undefined),
  requestAccounts: (req: string) => call<S["AccountChoice"][]>("GET", `requests/${id(req)}/accounts`),
  dismiss: (req: string, readVersion: number) =>
    call<S["RequestChanged"]>("POST", `requests/${id(req)}/dismiss`, { read_version: readVersion }),
  undismiss: (req: string, readVersion: number) =>
    call<S["RequestChanged"]>("POST", `requests/${id(req)}/undismiss`, { read_version: readVersion }),
  markSent: (person: string, text: string | null) =>
    call<S["SentCounts"]>("POST", `followups/${id(person)}/mark-sent`, { text }),
  unmarkSent: (person: string, body: S["Unmark"]) =>
    call<S["Ok"]>("POST", `followups/${id(person)}/unmark-sent`, body),
  backup: () => call<S["Status"]>("POST", "backup"),
  projects: () => call<S["ProjectView"][]>("GET", "projects"),
  notes: () => call<S["NoteView"][]>("GET", "notes"),
  addPerson: (body: S["PersonIn"]) => call<S["Created"]>("POST", "people", body),
  editPerson: (p: string, body: S["PersonPatch"]) => call<S["Ok"]>("POST", `people/${id(p)}`, body),
  organizations: () => call<S["OrganizationView"][]>("GET", "organizations"),
  addOrganization: (body: Partial<S["OrganizationIn"]> & { name: string }) => call<S["Created"]>("POST", "organizations", body),
  editOrganization: (o: string, body: S["OrganizationPatch"]) => call<S["Ok"]>("POST", `organizations/${id(o)}`, body),
  removeOrganization: (o: string) => call<S["Ok"]>("POST", `organizations/${id(o)}/remove`),
  restoreOrganization: (o: string) => call<S["Ok"]>("POST", `organizations/${id(o)}/restore`),
  removePerson: (p: string) => call<S["Ok"]>("POST", `people/${id(p)}/remove`),
  restorePerson: (p: string) => call<S["Ok"]>("POST", `people/${id(p)}/restore`),
  addProject: (body: S["ProjectIn"]) => call<S["Created"]>("POST", "projects", body),
  editProject: (p: string, body: S["ProjectPatch"]) => call<S["Ok"]>("POST", `projects/${id(p)}`, body),
  removeProject: (p: string) => call<S["Ok"]>("POST", `projects/${id(p)}/remove`),
  restoreProject: (p: string) => call<S["Ok"]>("POST", `projects/${id(p)}/restore`),

  files: () => call<S["FileView"][]>("GET", "files"),
  fileKinds: () => call<S["FileKindView"][]>("GET", "file-kinds"),
  /** Where a file's bytes are, relative to the page like every other address. */
  fileContent: (file: string) => `api/files/${id(file)}/content`,
  uploadFile: (file: Blob & { name: string }, upload: FileUpload) => {
    const query = new URLSearchParams({ name: file.name, kind: upload.kind });
    if (upload.project) query.set("project", upload.project);
    if (upload.replaces) query.set("replaces", upload.replaces);
    if (upload.meta && Object.keys(upload.meta).length) query.set("meta", JSON.stringify(upload.meta));
    const type = file.type || "application/octet-stream";
    return send<S["FileView"]>("POST", `files?${query.toString()}`, { headers: { "content-type": type }, body: file });
  },

  pluginActions: (kind?: string, record?: string) =>
    call<S["PersonActionView"][]>(
      "GET",
      kind && record ? `plugin-actions?kind=${id(kind)}&id=${id(record)}` : "plugin-actions",
    ),
  actionPreview: (name: string, body: S["ActionRun"]) =>
    call<S["ActionProposalView"]>("POST", `plugin-actions/${named(name)}/preview`, body),
  actionApply: (token: string, kept?: Record<string, boolean>, keptRequests?: Record<string, boolean>) => {
    const body: S["ActionApply"] = { token };
    if (kept) body.kept = kept;
    if (keptRequests) body.kept_requests = keptRequests;
    return call<S["ActionApplied"]>("POST", "plugin-actions/apply", body);
  },

  sync: () => call<S["SyncView"]>("GET", "sync"),
  jobs: () => call<S["JobView"][]>("GET", "jobs"),

  pluginToday: () => call<S["TodayLineView"][]>("GET", "plugin-today"),
  agenda: () => call<S["AgendaItemView"][]>("GET", "today/agenda"),
  todo: () => call<S["TodoView"][]>("GET", "today/todo"),
  arrived: () => call<S["InboxView"]>("GET", "today/arrived"),
  taskKinds: (kind?: string, record?: string) =>
    call<S["TaskKindView"][]>("GET", kind && record ? `task-kinds?kind=${id(kind)}&id=${id(record)}` : "task-kinds"),
  startTask: (name: string, about: S["RecordReference"] | null) =>
    call<S["TaskStarted"]>("POST", `task-kinds/${named(name)}/start`, { about, note: "" }),

  /** The screens plugins add; with a project, only those its add-on shows on that project. */
  panels: (project?: string) => call<S["PanelView"][]>("GET", `panels${project ? `?project=${id(project)}` : ""}`),
  panelRows: (name: string, project?: string) =>
    call<S["PanelRow"][]>("GET", `panels/${named(name)}/rows${project ? `?project=${id(project)}` : ""}`),
  valueLists: () => call<S["ValueListView"][]>("GET", "lists"),
  listAdd: (list: string, value: string) => call<S["Applied"]>("POST", `lists/${named(list)}/add`, { value }),
  listRename: (list: string, value: string, to: string) =>
    call<S["Applied"]>("POST", `lists/${named(list)}/rename`, { value, to }),
  listRetire: (list: string, value: string) => call<S["Applied"]>("POST", `lists/${named(list)}/retire`, { value }),
  editRecord: (body: S["RecordEdit"]) => call<S["Applied"]>("POST", "records/edit", body),
  kindView: (kind: string) => call<S["KindView"]>("GET", `kinds/${named(kind)}`),
  record: (kind: string, record: string) =>
    call<S["GenericRecordView"]>("GET", `record?kind=${id(kind)}&id=${id(record)}`),

  text: (kind: string, record: string, field: string) =>
    call<S["TextFieldView"]>("GET", `texts?kind=${id(kind)}&id=${id(record)}&field=${id(field)}`),
  editText: (body: S["TextEdit"]) => call<S["Applied"]>("POST", "texts/edit", body),
  textReview: (version: string) => call<S["TextReview"]>("GET", `text-versions/${id(version)}/review`),
  acceptText: (version: string, body: S["TextChoices"]) =>
    call<S["Applied"]>("POST", `text-versions/${id(version)}/accept`, body),
  discardText: (version: string, body: S["TextChoices"]) =>
    call<S["Applied"]>("POST", `text-versions/${id(version)}/discard`, body),

  workingCopyFormats: (kind: string, field: string) =>
    call<S["WorkingCopyFormatView"][]>("GET", `working-copies/formats?kind=${id(kind)}&field=${id(field)}`),
  workingCopies: (kind: string, record: string) =>
    call<S["WorkingCopyView"][]>("GET", `working-copies?kind=${id(kind)}&id=${id(record)}`),
  handOut: (body: S["WorkingCopyOut"]) => call<S["WorkingCopyView"]>("POST", "working-copies", body),
  /** The file's own bytes are the request body; its name goes in the address. */
  returnCopy: (copy: string, file: Blob & { name: string }) =>
    send<S["TakenBack"]>("POST", `working-copies/${id(copy)}/return?name=${id(file.name)}`, {
      headers: { "content-type": file.type || "application/octet-stream" },
      body: file,
    }),
  dropCopy: (copy: string) => call<S["Ok"]>("POST", `working-copies/${id(copy)}/drop`),

  packs: () => call<S["PacksView"]>("GET", "packs"),
  refreshPacks: () => call<S["PacksView"]>("POST", "packs/refresh"),
  /** Adds an installed add-on to the ones that run; its code runs after the restart the person chooses. With Undo. */
  packOn: (name: string, fingerprint: string) =>
    call<S["SettingsSaved"]>("POST", `packs/${id(name)}/on`, { fingerprint } satisfies S["FingerprintIn"]),
  packOff: (name: string, fingerprint: string) =>
    call<S["SettingsSaved"]>("POST", `packs/${id(name)}/off`, { fingerprint } satisfies S["FingerprintIn"]),

  signIns: () => call<S["SignInView"][]>("GET", "sign-ins"),
  startSignIn: (name: string) => call<S["SignInStarted"]>("POST", `sign-ins/${named(name)}/start`),
  signOut: (name: string) => call<S["Ok"]>("DELETE", `sign-ins/${named(name)}`),
  saveSignInApp: (name: string, body: S["SignInApp"]) => call<S["SignInView"]>("POST", `sign-ins/${named(name)}/app`, body),
  setAsideSignInApp: (name: string) => call<S["SignInView"]>("POST", `sign-ins/${named(name)}/app/set-aside`),
  bringBackSignInApp: (name: string) => call<S["SignInView"]>("POST", `sign-ins/${named(name)}/app/bring-back`),

  settings: () => call<S["SettingsView"]>("GET", "settings"),
  saveSettings: (body: S["SettingsSave"]) => call<S["SettingsSaved"]>("POST", "settings", body),
  setup: () => call<S["SetupView"]>("GET", "setup"),
  me: () => call<S["MeView"]>("GET", "me"),
  saveMe: (fullName: string) => call<S["MeView"]>("POST", "me", { full_name: fullName }),
  applyStepSettings: (step: string, fingerprint: string) =>
    call<S["SettingsSaved"]>("POST", `setup/${named(step)}/apply-settings`, { fingerprint }),
  skipStep: (step: string) => call<S["Ok"]>("POST", `setup/${named(step)}/skip`),
  reopenStep: (step: string) => call<S["Ok"]>("POST", `setup/${named(step)}/reopen`),
  templates: () => call<S["TemplateView"][]>("GET", "templates"),
  applyTemplate: (template: string) => call<S["TemplateApplied"]>("POST", "templates/apply", { id: template }),
  folderCheck: (path: string) => call<S["FolderCheckView"]>("GET", `setup/folder-check?path=${id(path)}`),
  folders: (path?: string) => call<S["FolderListView"]>("GET", `setup/folders${path ? `?path=${id(path)}` : ""}`),
  saveBackupFolder: (body: S["BackupFolderAdd"]) => call<S["SettingsSaved"]>("POST", "setup/backup-folder", body),
  endpoints: () => call<S["EndpointView"][]>("GET", "ai/endpoints"),
  aiModels: (body: S["AiModelsAsk"]) => call<S["AiModelsView"]>("POST", "ai/models", body),
  aiLocal: () => call<S["LocalServerView"][]>("GET", "ai/local"),
  addAccount: (body: S["AiAccountAdd"]) => call<S["SettingsSaved"]>("POST", "ai/accounts", body),
  aiAccounts: () => call<S["AiAccountView"][]>("GET", "ai/accounts"),
  changeAccount: (name: string, body: S["AiAccountChange"]) =>
    call<S["SettingsSaved"]>("POST", `ai/accounts/${id(name)}`, body),
  removeAccount: (name: string, fingerprint: string) =>
    call<S["SettingsSaved"]>("POST", `ai/accounts/${id(name)}/remove`, { fingerprint } satisfies S["FingerprintIn"]),
  testAi: () => call<S["AiTestResult"][]>("POST", "ai/test"),
  /** Tests one account on its first model, whether or not any work uses it. */
  testAccount: (name: string) => call<S["AiTestResult"][]>("POST", `ai/accounts/${id(name)}/test`),
};

export const EVENTS_PATH = "api/events";
