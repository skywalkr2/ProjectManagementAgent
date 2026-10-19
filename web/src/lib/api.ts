// The API client. Types come from the server's OpenAPI schema (npm run gen:api), so a changed field fails the build.
// Paths are relative: the page's <base> points at the configured base path, so the same build works under any path.
import type { components } from "../api/schema";

export type S = components["schemas"];

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    /** What the server says would fix it, when it says (the `X-Cockpit-Needs` header): "read-token". */
    public needs: string | null = null,
  ) {
    super(detail || `HTTP ${status}`);
  }
}

async function send<T>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`api/${path}`, { method, credentials: "same-origin", ...init });
  if (!response.ok) {
    let detail = "";
    try {
      const data = (await response.json()) as { detail?: unknown; error?: unknown };
      detail = typeof data.detail === "string" ? data.detail : typeof data.error === "string" ? data.error : "";
    } catch {
      detail = "";
    }
    throw new ApiError(response.status, detail, response.headers.get("X-Cockpit-Needs"));
  }
  return (await response.json()) as T;
}

async function call<T>(method: "GET" | "POST" | "PUT" | "DELETE", path: string, body?: unknown): Promise<T> {
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
  todayQueue: () => call<S["QueueLineView"][]>("GET", "today/queue"),
  source: (src: string) => call<S["SourceView"]>("GET", `sources/${id(src)}`),
  widenSource: (src: string, body: S["SourceWiden"]) => call<S["Applied"]>("POST", `sources/${id(src)}/widen`, body),
  followups: () => call<S["FollowupSection"][]>("GET", "followups"),

  watchSources: () => call<S["WatchSourceView"][]>("GET", "watch"),
  /** The go for a newly added source's intake: every item held for it starts. */
  intakeGo: (source: string) => call<S["IntakeStarted"]>("POST", `watch/${id(source)}/intake/go`),
  /** Opening what a newly added source's intake found: its results show on Today one by one again. */
  intakeSeen: (source: string) => call<S["IntakeSeen"]>("POST", `watch/${id(source)}/intake/seen`),
  intakeUnseen: (source: string, requests: string[]) =>
    call<S["IntakeUnseen"]>("POST", `watch/${id(source)}/intake/unseen`, { requests }),
  /** What looking further back would take in and cost, before anything is read. */
  lookBackPreview: (source: string, days: number) =>
    call<S["LookBackView"]>("GET", `watch/${id(source)}/look-back?days=${days}`),
  lookBack: (source: string, days: number) => call<S["LookBackView"]>("POST", `watch/${id(source)}/look-back`, { days }),
  watchKinds: () => call<S["WatchKindView"][]>("GET", "watch/kinds"),
  watchAuthors: () => call<S["WatchAuthorOption"][]>("GET", "watch/authors"),
  addSource: (body: S["WatchSourceIn"]) => call<S["SettingsSaved"]>("POST", "watch/sources", body),
  changeSource: (src: string, body: S["WatchSourceChange"]) =>
    call<S["SettingsSaved"]>("POST", `watch/sources/${id(src)}`, body),
  removeSource: (src: string, fingerprint: string) =>
    call<S["SettingsSaved"]>("POST", `watch/sources/${id(src)}/remove`, { fingerprint } satisfies S["FingerprintIn"]),
  /** The folders of a mailbox source, and which one its server marks as sent mail. */
  watchFolders: (src: string) => call<S["MailFoldersView"]>("GET", `watch/${id(src)}/folders`),
  addSentFolder: (src: string, body: S["SentFolderIn"]) => call<S["SettingsSaved"]>("POST", `watch/${id(src)}/sent-folder`, body),
  readSource: (src: string) => call<S["WatchSourceView"]>("POST", `watch/${id(src)}/read`),
  handInRecent: (src: string) => call<S["WatchSourceView"]>("POST", `watch/${id(src)}/recent`),
  autoClosed: () => call<S["AutoClosedView"][]>("GET", "auto-closed"),
  silentCloses: () => call<S["SilentClosesView"]>("GET", "silent-closes"),
  sinceYesterday: () => call<S["SinceYesterdayView"]>("GET", "since-yesterday"),
  sinceSeen: (until: string) => call<S["Ok"]>("POST", "since-yesterday/seen", { until } satisfies S["SinceSeen"]),
  closeSeen: (ref: string) => call<S["Created"]>("POST", "silent-closes/seen", { ref } satisfies S["SilentCloseSeen"]),
  closerLook: (req: string, readVersion: number) =>
    call<S["Created"]>("POST", `requests/${id(req)}/closer-look`, { read_version: readVersion }),
  setAside: () => call<S["SetAsideFolder"]>("GET", "set-aside"),
  setAsideMail: (item: string, section: S["SetAsideIn"]["section"]) =>
    call<S["SetAsideDone"]>("POST", `mail/${id(item)}/set-aside`, { section } satisfies S["SetAsideIn"]),
  isWork: (item: string, readVersion: number) =>
    call<S["SetAsideDone"]>("POST", `set-aside/${id(item)}/work`, { read_version: readVersion }),
  putBack: (item: string, readVersion: number) =>
    call<S["SetAsideDone"]>("POST", `set-aside/${id(item)}/put-back`, { read_version: readVersion }),
  sortingRule: (body: S["SortingRuleIn"]) => call<S["SettingsSaved"]>("POST", "watch/sorting", body),
  confirmSetAside: (fingerprint: string, ids: string[]) =>
    call<S["ConfirmDone"]>("POST", "set-aside/confirm", { fingerprint, ids } satisfies S["ConfirmIn"]),
  unconfirmSetAside: (ids: string[]) =>
    call<S["Created"]>("POST", "set-aside/unconfirm", { ids } satisfies S["UnconfirmIn"]),

  ask: (question: string) => call<S["Created"]>("POST", "ask", { question }),
  asks: () => call<S["AskView"][]>("GET", "asks"),
  quality: () => call<S["QualityView"]>("GET", "quality"),
  /** Save, or correct, the person's own count for a day: what Undo takes comes back as `previous`. */
  saveCount: (day: string, body: S["QualityCountIn"]) => call<S["QualityCountSaved"]>("PUT", `quality/counts/${id(day)}`, body),
  undoCount: (day: string, previous: S["QualityCountBefore"] | null) =>
    call<S["Ok"]>("POST", `quality/counts/${id(day)}/undo`, { previous } satisfies S["QualityCountUndo"]),
  missed: (text: string) => call<S["MissedSent"]>("POST", "missed", { text } satisfies S["MissedIn"]),
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
  newPersonForm: (q: string) => call<S["NewPersonPrefillView"]>("GET", `questions/${id(q)}/new-person`),
  addNewPerson: (q: string, body: S["NewPersonIn"]) => call<S["NewPersonDone"]>("POST", `questions/${id(q)}/new-person`, body),
  projectPartOf: (cs: string, index: number, project: string) =>
    call<S["Applied"]>("POST", `changesets/${id(cs)}/ops/${index}/part-of`, { project }),
  notAProject: (cs: string, index: number) => call<S["Applied"]>("POST", `changesets/${id(cs)}/ops/${index}/not-a-project`),
  answer: (q: string, body: S["Answer"]) => call<S["Noted"]>("POST", `questions/${id(q)}/answer`, body),
  /** A note goes with the change only when there is one: with none, the request is the same as it always was. */
  actionStatus: (a: string, status: S["ActionState"]["status"], note?: string) =>
    call<S["Noted"]>("POST", `actions/${id(a)}/status`, note ? { status, note } : { status }),
  putOnHold: (a: string, waiting_for: string) => call<S["HoldChanged"]>("POST", `actions/${id(a)}/hold`, { waiting_for }),
  takeOffHold: (a: string) => call<S["HoldChanged"]>("POST", `actions/${id(a)}/unhold`),
  restoreHold: (a: string, hold: S["HoldState"] | null) => call<S["Ok"]>("POST", `actions/${id(a)}/hold/restore`, { hold }),
  reply: (q: string, text: string) => call<S["Handed"]>("POST", `questions/${id(q)}/reply`, { text }),
  retry: (req: string, use?: string) =>
    call<S["Ok"]>("POST", `requests/${id(req)}/retry`, use ? { use } : undefined),
  allowData: (req: string) => call<S["DataLevelAllowed"]>("POST", `requests/${id(req)}/allow-data`),
  requestAccounts: (req: string) => call<S["AccountChoice"][]>("GET", `requests/${id(req)}/accounts`),
  dismiss: (req: string, readVersion: number) =>
    call<S["RequestChanged"]>("POST", `requests/${id(req)}/dismiss`, { read_version: readVersion }),
  undismiss: (req: string, readVersion: number) =>
    call<S["RequestChanged"]>("POST", `requests/${id(req)}/undismiss`, { read_version: readVersion }),
  markSent: (person: string, text: string | null) =>
    call<S["SentCounts"]>("POST", `followups/${id(person)}/mark-sent`, { text }),
  unmarkSent: (person: string, body: S["Unmark"]) =>
    call<S["Ok"]>("POST", `followups/${id(person)}/unmark-sent`, body),
  nudgeSent: (person: string, body: S["NudgeSent"]) =>
    call<S["NudgeRecorded"]>("POST", `followups/${id(person)}/followed-up`, body),
  nudgeUnsent: (person: string, body: S["NudgeUnsent"]) =>
    call<S["Ok"]>("POST", `followups/${id(person)}/unfollow`, body),
  followedUp: (person: string, action: string, note?: string) =>
    call<S["FollowedUp"]>("POST", `followups/${id(person)}/actions/${id(action)}/followed-up`, note ? { note } : undefined),
  unfollow: (person: string, action: string, body: S["Unfollow"]) =>
    call<S["Ok"]>("POST", `followups/${id(person)}/actions/${id(action)}/unfollow`, body),
  theyFinished: (person: string, action: string, note?: string) =>
    call<S["Noted"]>("POST", `followups/${id(person)}/actions/${id(action)}/finished`, note ? { note } : undefined),
  backup: () => call<S["Status"]>("POST", "backup"),

  /** What the assistant learned from each correction that has something to show, for the line under its card. */
  learned: () => call<S["LearnedView"]>("GET", "knowledge/learned"),
  proposals: () => call<S["ProposalsView"]>("GET", "knowledge/proposals"),
  catchUp: () => call<S["CatchUpView"]>("GET", "knowledge/catch-up"),
  /** The go for the learning runs held for the catch-up list: they all start. */
  catchUpGo: () => call<S["CatchUpStarted"]>("POST", "knowledge/catch-up/go"),
  keepKnowledge: (entry: string, body: S["KnowledgeKeep"]) => call<S["Applied"]>("POST", `knowledge/${id(entry)}/keep`, body),
  discardKnowledge: (entry: string, readVersion: number, reason?: string) =>
    call<S["Applied"]>("POST", `knowledge/${id(entry)}/discard`, { read_version: readVersion, reason: reason || null }),
  justThisTime: (entry: string, readVersion: number) =>
    call<S["Applied"]>("POST", `knowledge/${id(entry)}/just-this-time`, { read_version: readVersion }),
  narrowKnowledge: (entry: string, body: S["KnowledgeNarrow"]) =>
    call<S["Applied"]>("POST", `knowledge/${id(entry)}/narrow`, body),
  retireKnowledge: (entry: string, readVersion: number) =>
    call<S["Applied"]>("POST", `knowledge/${id(entry)}/retire`, { read_version: readVersion }),
  /** "Change this" on a row the assistant made; the note is the person's own words and is required. */
  changeThis: (kind: string, item: string, note: string) =>
    call<S["ChangeRequested"]>("POST", `items/${id(kind)}/${id(item)}/change`, { note }),
  rewordQuestion: (q: string, body: S["QuestionRewordIn"]) => call<S["Applied"]>("POST", `questions/${id(q)}/reword`, body),
  rerouteQuestion: (q: string, to: string) => call<S["Applied"]>("POST", `questions/${id(q)}/reroute`, { to }),
  /** Drop an action that is no longer needed, with Undo. */
  dropAction: (a: string, reason: string) => call<S["Applied"]>("POST", `actions/${id(a)}/drop`, { reason }),
  reviewReply: (a: string, body: S["ActionReplyIn"]) => call<S["Applied"]>("POST", `actions/${id(a)}/reply`, body),
  answeredAnotherWay: (a: string, body: S["AnsweredAnotherWayIn"]) => call<S["Applied"]>("POST", `replies/${id(a)}/answered`, body),
  /** Keep the drafted reply as the person copied it, so the message they send can be matched to it. */
  replyCopied: (a: string) => call<S["Copied"]>("POST", `replies/${id(a)}/copied`),
  /** The answer to "Did your message go out?"; the result is what Undo takes. */
  settleCopy: (c: string, how: S["CopyAnswer"]["how"]) => call<S["CopySettled"]>("POST", `copies/${id(c)}/settle`, { how }),
  unsettleCopy: (c: string, body: S["CopySettled"]) => call<S["Ok"]>("POST", `copies/${id(c)}/unsettle`, body),
  /** Add an action waiting for an owner to the open action it nearly repeats; `readVersion` is that action's version as read. */
  foldAction: (cs: string, index: number, into: string, readVersion: number) =>
    call<S["Applied"]>("POST", `changesets/${id(cs)}/ops/${index}/fold`, { into, read_version: readVersion }),
  dropQuestion: (q: string, reason: string) => call<S["Applied"]>("POST", `questions/${id(q)}/drop`, { reason }),
  questionSent: (q: string) => call<S["Applied"]>("POST", `questions/${id(q)}/sent`, {}),
  projects: () => call<S["ProjectView"][]>("GET", "projects"),
  notes: () => call<S["NoteView"][]>("GET", "notes"),
  unfiled: () => call<S["UnfiledView"]>("GET", "unfiled"),
  fileUnfiled: (body: S["UnfiledFile"]) => call<S["Applied"]>("POST", "unfiled/file", body),
  seriesPage: (series: string) => call<S["SeriesPageView"]>("GET", `series/${id(series)}/page`),
  recordPage: (kind: string, record: string) => call<S["RecordPageView"]>("GET", `record-pages/${id(record)}?kind=${id(kind)}`),
  declineOp: (cs: string, index: number) => call<S["Ok"]>("POST", `changesets/${id(cs)}/ops/${index}/decline`),
  undeclineOp: (cs: string, index: number) => call<S["Ok"]>("POST", `changesets/${id(cs)}/ops/${index}/undecline`),
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
  /** The person's own part in a project (run, design or watch), with Undo through the change it returns. */
  setProjectRole: (p: string, role: S["ProjectRoleIn"]["role"]) =>
    call<S["Applied"]>("POST", `projects/${id(p)}/role`, { role }),
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
  handover: () => call<S["HandoverView"]>("GET", "sync/handover"),
  chooseCopy: (which: S["HandoverChoice"]["which"]) => call<S["HandoverView"]>("POST", "sync/handover", { which }),
  changeMindAboutCopy: () => call<S["HandoverView"]>("DELETE", "sync/handover"),
  jobs: () => call<S["JobView"][]>("GET", "jobs"),

  pluginToday: () => call<S["TodayLineView"][]>("GET", "plugin-today"),
  agenda: () => call<S["AgendaItemView"][]>("GET", "today/agenda"),
  todo: () => call<S["TodoView"][]>("GET", "today/todo"),
  arrived: () => call<S["InboxView"]>("GET", "today/arrived"),
  checkArrived: () => call<S["InboxCheckView"]>("POST", "today/arrived/check"),
  taskKinds: (kind?: string, record?: string) =>
    call<S["TaskKindView"][]>("GET", kind && record ? `task-kinds?kind=${id(kind)}&id=${id(record)}` : "task-kinds"),
  startTask: (name: string, about: S["RecordReference"] | null) =>
    call<S["TaskStarted"]>("POST", `task-kinds/${named(name)}/start`, { about, note: "" }),

  /** The screens plugins add; with a project, only those its add-on shows on that project. */
  panels: (project?: string) => call<S["PanelView"][]>("GET", `panels${project ? `?project=${id(project)}` : ""}`),
  panelRows: (name: string, project?: string) =>
    call<S["PanelRow"][]>("GET", `panels/${named(name)}/rows${project ? `?project=${id(project)}` : ""}`),
  /** A document panel's blocks for the project in view, or the workspace; null when there is nothing to show yet. */
  panelDocument: (name: string, project?: string) =>
    call<S["DocumentView"]>("GET", `panels/${named(name)}/document${project ? `?project=${id(project)}` : ""}`),
  valueLists: () => call<S["ValueListView"][]>("GET", "lists"),
  listAdd: (list: string, value: string) => call<S["Applied"]>("POST", `lists/${named(list)}/add`, { value }),
  listRename: (list: string, value: string, to: string) =>
    call<S["Applied"]>("POST", `lists/${named(list)}/rename`, { value, to }),
  listRetire: (list: string, value: string) => call<S["Applied"]>("POST", `lists/${named(list)}/retire`, { value }),
  editRecord: (body: S["RecordEdit"]) => call<S["Applied"]>("POST", "records/edit", body),
  /** Why a promise exists: its words, who owes it to whom, its day, how it is known and what was heard since. */
  remind: (action: string, body: S["ReminderIn"]) => call<S["Applied"]>("POST", `reminders/${id(action)}`, body),
  promise: (action: string) => call<S["PromiseView"]>("GET", `promises/${id(action)}`),
  correctPromise: (action: string, body: S["PromiseCorrection"]) => call<S["Applied"]>("POST", `promises/${id(action)}/correct`, body),
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
  addCatalog: (address: string, fingerprint: string) =>
    call<S["SettingsSaved"]>("POST", "packs/catalogs", { address, fingerprint } satisfies S["CatalogAddress"]),
  removeCatalog: (address: string, fingerprint: string) =>
    call<S["SettingsSaved"]>("POST", "packs/catalogs/remove", { address, fingerprint } satisfies S["CatalogAddress"]),
  giveReadToken: (name: string, body: S["PackTokenIn"]) => call<S["SettingsSaved"]>("POST", `packs/${id(name)}/token`, body),
  /** The secrets each running add-on says it needs, and where each is read from; never a value. */
  addonSecrets: () => call<S["AddonSecretsView"][]>("GET", "addon-secrets"),
  /** Gives one secret an add-on needs, typed (kept on this computer) or as where it is kept. */
  giveAddonSecret: (plugin: string, secret: string, body: S["AddonSecretIn"]) =>
    call<S["SettingsSaved"]>("POST", `addons/${id(plugin)}/secrets/${id(secret)}`, body),
  /** Where the key that locks the backups is read from; never the key. */
  backupKey: () => call<S["BackupKeyView"]>("GET", "backup-key"),
  /** Gives the backup key: typed, made by the app (shown once in the answer's `made`), or as where it is kept. */
  setBackupKey: (body: S["BackupKeyIn"]) => call<S["BackupKeySaved"]>("POST", "backup-key", body),
  /** Installs (or updates) an add-on from the release its catalog entry names. It isn't turned on, and it is used after a restart. */
  installPack: (name: string) => call<S["PackInstalled"]>("POST", `packs/${id(name)}/install`),
  /** Takes away an add-on the app installed from the screen; it has to be off first. Used after a restart. */
  removePack: (name: string) => call<S["PackInstalled"]>("POST", `packs/${id(name)}/uninstall`),
  /** The person's first go: starts every run waiting for it. */
  firstGo: () => call<S["FirstGoStarted"]>("POST", "runs/first-go"),
  firstGoSorting: () => call<S["FirstGoSorting"]>("GET", "runs/first-go"),
  /** Adds an installed add-on to the ones that run; its code runs after the restart the person chooses. With Undo. */
  packOn: (name: string, fingerprint: string) =>
    call<S["SettingsSaved"]>("POST", `packs/${id(name)}/on`, { fingerprint } satisfies S["FingerprintIn"]),
  packOff: (name: string, fingerprint: string) =>
    call<S["SettingsSaved"]>("POST", `packs/${id(name)}/off`, { fingerprint } satisfies S["FingerprintIn"]),

  /** Leaves the add-ons that are installed and off as they are, so the setup guide stops asking about them. */
  leaveAddonsOff: () => call<S["Ok"]>("POST", "setup/addons/leave-off"),

  dataForms: () => call<S["DataFormView"][]>("GET", "data-forms"),
  dataFiles: (form: string, project?: string) =>
    call<S["DataFile"][]>("GET", `data-forms/${named(form)}/files${project ? `?project=${id(project)}` : ""}`),
  dataFile: (form: string, path: string, project?: string) =>
    call<S["DataFileView"]>(
      "GET",
      `data-forms/${named(form)}/file?path=${id(path)}${project ? `&project=${id(project)}` : ""}`,
    ),
  saveDataFile: (form: string, body: S["DataFileChange"]) =>
    call<S["DataFileSaved"]>("POST", `data-forms/${named(form)}/file`, body),
  removeDataFile: (form: string, body: S["DataFileChange"]) =>
    call<S["DataFileSaved"]>("POST", `data-forms/${named(form)}/remove`, body),
  /** Undo for a save or a removal: the layer's copy as it was (`before`), or none. */
  restoreDataFile: (form: string, body: S["DataFileRestore"]) =>
    call<S["DataFileSaved"]>("POST", `data-forms/${named(form)}/restore`, body),

  signIns: () => call<S["SignInView"][]>("GET", "sign-ins"),
  startSignIn: (name: string) => call<S["SignInStarted"]>("POST", `sign-ins/${named(name)}/start`),
  signOut: (name: string) => call<S["Ok"]>("DELETE", `sign-ins/${named(name)}`),
  startSignInSources: (name: string) => call<S["SignInView"]>("POST", `sign-ins/${named(name)}/sources`),
  saveSignInApp: (name: string, body: S["SignInApp"]) => call<S["SignInView"]>("POST", `sign-ins/${named(name)}/app`, body),
  setAsideSignInApp: (name: string) => call<S["SignInView"]>("POST", `sign-ins/${named(name)}/app/set-aside`),
  bringBackSignInApp: (name: string) => call<S["SignInView"]>("POST", `sign-ins/${named(name)}/app/bring-back`),

  settings: () => call<S["SettingsView"]>("GET", "settings"),
  saveSettings: (body: S["SettingsSave"]) => call<S["SettingsSaved"]>("POST", "settings", body),
  setup: () => call<S["SetupView"]>("GET", "setup"),
  /** Keeps where the walkthrough stands on the server: its screen, that it was closed, or that it was finished. */
  /** Where the walkthrough's first result stands: the look back offered with its estimate, under way, or done. */
  firstPromises: () => call<S["FirstPromisesView"]>("GET", "setup/first-promises"),
  /** The go for the look back the walkthrough offered: everything it counted starts. */
  firstPromisesGo: () => call<S["IntakeStarted"]>("POST", "setup/first-promises/go"),
  keepWalkthrough: (body: S["WalkthroughIn"]) => call<S["WalkthroughView"]>("POST", "setup/walkthrough", body),
  me: () => call<S["MeView"]>("GET", "me"),
  saveMe: (fullName: string) => call<S["MeView"]>("POST", "me", { full_name: fullName }),
  applyStepSettings: (step: string, fingerprint: string) =>
    call<S["SettingsSaved"]>("POST", `setup/${named(step)}/apply-settings`, { fingerprint }),
  skipStep: (step: string) => call<S["Ok"]>("POST", `setup/${named(step)}/skip`),
  reopenStep: (step: string) => call<S["Ok"]>("POST", `setup/${named(step)}/reopen`),
  templates: () => call<S["TemplateView"][]>("GET", "templates"),
  applyTemplate: (template: string) => call<S["TemplateApplied"]>("POST", "templates/apply", { id: template }),
  folderCheck: (path: string) => call<S["FolderCheckView"]>("GET", `setup/folder-check?path=${id(path)}`),
  /** The folders inside one, and with `files` (endings such as ".ics") the files that end that way. */
  folders: (path?: string, files?: string[]) => {
    const asked = [path ? `path=${id(path)}` : "", files && files.length > 0 ? `files=${id(files.join(","))}` : ""].filter(Boolean);
    return call<S["FolderListView"]>("GET", `setup/folders${asked.length > 0 ? `?${asked.join("&")}` : ""}`);
  },
  saveBackupFolder: (body: S["BackupFolderAdd"]) => call<S["SettingsSaved"]>("POST", "setup/backup-folder", body),
  endpoints: () => call<S["EndpointView"][]>("GET", "ai/endpoints"),
  aiModels: (body: S["AiModelsAsk"]) => call<S["AiModelsView"]>("POST", "ai/models", body),
  aiLocal: () => call<S["LocalServerView"][]>("GET", "ai/local"),
  addAccount: (body: S["AiAccountAdd"]) => call<S["SettingsSaved"]>("POST", "ai/accounts", body),
  aiAccounts: () => call<S["AiAccountView"][]>("GET", "ai/accounts"),
  aiSkills: () => call<S["AiSkillsView"]>("GET", "ai/skills"),
  aiRouting: () => call<S["AiRoutingView"]>("GET", "ai/routing"),
  /** What one account's connection check involves, to price it with a model's price. */
  aiCheckSize: () => call<S["AiCheckSize"]>("GET", "ai/check-size"),
  changeAccount: (name: string, body: S["AiAccountChange"]) =>
    call<S["SettingsSaved"]>("POST", `ai/accounts/${id(name)}`, body),
  /** What the check that comes with a change of account or model would cost, and whether one is offered at all. */
  switchEstimate: (name: string, body: S["AiAccountChange"]) =>
    call<S["AiSwitchEstimate"]>("POST", `ai/accounts/${id(name)}/switch-estimate`, body),
  /** Makes the change and checks the new choice in the background; a failure comes to Today. */
  switchAndCheck: (name: string, body: S["AiAccountChange"]) =>
    call<S["AiSwitched"]>("POST", `ai/accounts/${id(name)}/switch-check`, body),
  /** Puts a tier back as it was before the switch whose check didn't pass. */
  switchBack: (tier: string, fingerprint: string) =>
    call<S["SettingsSaved"]>("POST", `ai/switch/${id(tier)}/back`, { fingerprint } satisfies S["FingerprintIn"]),
  /** Keeps a switch whose check didn't pass. */
  keepSwitch: (tier: string) => call<S["Ok"]>("POST", `ai/switch/${id(tier)}/keep`),
  /** Keeps the sign-in an agent account now runs as, in place of the one recorded. */
  keepIdentity: (name: string) => call<S["Ok"]>("POST", `ai/accounts/${id(name)}/identity/keep`),
  /** Removes an account; `takeOver` names the backup that does its work in its place. */
  removeAccount: (name: string, fingerprint: string, takeOver?: string) =>
    call<S["SettingsSaved"]>("POST", `ai/accounts/${id(name)}/remove`, {
      fingerprint,
      ...(takeOver ? { take_over: takeOver } : {}),
    } satisfies S["AiAccountRemove"]),
  /** What measuring an account (or one of its models) would cost; nothing is run. */
  measureEstimate: (name: string, model?: string) =>
    call<S["AiMeasureEstimate"]>("POST", `ai/skills/${id(name)}/estimate`, model ? ({ model, confirmed: false } satisfies S["AiMeasureIn"]) : undefined),
  /** Measures an account's model (or all of them) in the background; `confirmed` is the person's go above the amount they asked to be asked about. */
  measure: (name: string, body: S["AiMeasureIn"]) => call<S["AiMeasureStarted"]>("POST", `ai/skills/${id(name)}/measure`, body),
  testAi: () => call<S["AiTestResult"][]>("POST", "ai/test"),
  /** Tests one account on its first model, whether or not any work uses it; with a tier and a model, with that tier's
   * kinds of work and their exact parameters, which is what lets the account stand in for it. */
  testAccount: (name: string, tier?: string, model?: string) => {
    const query = new URLSearchParams();
    if (tier) query.set("tier", tier);
    if (model) query.set("model", model);
    const text = query.toString();
    return call<S["AiTestResult"][]>("POST", `ai/accounts/${id(name)}/test${text ? `?${text}` : ""}`);
  },

  /** The answer to the question of using another kind of work's account while the work's own is paused: yes runs the
   * waiting work on it until the reset, no keeps it waiting. */
  borrowAccount: (body: S["AiBorrowAnswer"]) => call<S["AiBorrowed"]>("POST", "ai/borrow", body),

  knowledge: () => call<S["KnowledgeView"][]>("GET", "knowledge"),
  knowledgeRules: () => call<S["RuleView"][]>("GET", "knowledge/rules"),
  ruleReview: () => call<S["RuleReviewView"]>("GET", "knowledge/rules/review"),
  /** "Not now" on the rules review line: the review leaves Today for its week, and no rule changes. */
  ruleReviewNotNow: () => call<S["RuleReviewPutOff"]>("POST", "knowledge/rules/review/not-now"),
  /** Takes a "Not now" back: the line is on Today again at once. */
  ruleReviewNotNowUndo: (signal: string) => call<S["Ok"]>("POST", `knowledge/rules/review/not-now/${id(signal)}/undo`),
  keepRule: (entry: string, readVersion: number) =>
    call<S["Applied"]>("POST", `knowledge/${id(entry)}/keep-rule`, { read_version: readVersion } satisfies S["ReadVersion"]),
};

export const EVENTS_PATH = "api/events";
