// Picking a folder on this computer from a list (design 7.8): open a folder to look inside, go up, use the one shown.
// Only offered when the app runs on the person's own computer; the server refuses to list folders otherwise.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { Heading } from "react-aria-components";
import { api, ApiError } from "../lib/api";
import { useWords } from "../lib/wording";
import { ModalPanel } from "./ModalPanel";
import { Skeleton } from "../ui/Skeleton";

/** A folder's address inside another, using the separator the address already uses. */
export function joinPath(base: string, name: string): string {
  const sep = base.includes("\\") && !base.includes("/") ? "\\" : "/";
  return base.endsWith(sep) ? `${base}${name}` : `${base}${sep}${name}`;
}

/** Whether this app can list folders here. It can't when hosted; callers then offer a typed path and say nothing about it. */
export function useFolderListing(enabled = true): boolean {
  const probe = useQuery({ queryKey: ["folders", ""], queryFn: () => api.folders(), retry: false, enabled });
  return enabled && !probe.isError;
}

export function FolderPicker(props: { start?: string; onPick: (path: string) => void; onClose: () => void }) {
  const { t } = useWords();
  const titleId = useId();
  const [path, setPath] = useState<string | undefined>(props.start?.trim() || undefined);
  const folders = useQuery({
    queryKey: ["folders", path ?? ""],
    queryFn: () => api.folders(path),
    retry: false,
  });
  const here = folders.data?.path;
  const heading = useRef<HTMLParagraphElement>(null);
  const moved = useRef(false);
  // After opening a folder, focus goes to the line naming where you are, so it is read out and the list is next.
  useEffect(() => {
    if (!here) return;
    if (moved.current) heading.current?.focus();
    moved.current = true;
  }, [here]);

  const problem =
    folders.error instanceof ApiError && folders.error.detail ? folders.error.detail : folders.isError ? t("folders.failed") : "";
  return (
    <ModalPanel titleId={titleId} onClose={props.onClose}>
      <Heading slot="title" id={titleId} level={2}>
        {t("folders.title")}
      </Heading>
      {problem && (
        <p className="problem-note" role="alert">
          {problem}
        </p>
      )}
      {problem && path && (
        <div className="row-end">
          <button type="button" className="btn" onClick={() => setPath(undefined)}>
            {t("folders.start_over")}
          </button>
        </div>
      )}
      {folders.isPending && <Skeleton />}
      {folders.data && (
        <>
          <p className="path" ref={heading} tabIndex={-1}>
            {t("folders.here", { path: folders.data.path })}
          </p>
          <div className="row-end">
            <button
              type="button"
              className="btn"
              disabled={!folders.data.parent}
              onClick={() => setPath(folders.data?.parent ?? undefined)}
            >
              {t("folders.up")}
            </button>
          </div>
          {folders.data.folders.length === 0 ? (
            <p className="empty">{t("folders.none")}</p>
          ) : (
            <ul className="folder-list">
              {folders.data.folders.map((name) => (
                <li key={name}>
                  <button type="button" className="link-button" onClick={() => setPath(joinPath(folders.data!.path, name))}>
                    {name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <div className="row-end">
        <button type="button" className="btn quiet" onClick={props.onClose}>
          {t("action.cancel")}
        </button>
        <button type="button" className="btn primary" disabled={!folders.data} onClick={() => folders.data && props.onPick(folders.data.path)}>
          {t("folders.use")}
        </button>
      </div>
    </ModalPanel>
  );
}
