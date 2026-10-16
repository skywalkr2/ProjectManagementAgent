// One setting as a form control, with its label, hint, default and a way back to the default. Used by the Settings screen
// and by every other form built from setting items (a source's settings, an add-on's data file).
import { useRef, useState } from "react";
import { depthOf, fileName, formatValue, fromDraft, isOff, labelOf, switchOf, toDraft, type Draft, type Item } from "../lib/settings";
import { languageChoices } from "../lib/languages";
import { useWords } from "../lib/wording";
import { FolderPicker, useFolderListing } from "./FolderPicker";
import { restoreFocus } from "./ModalPanel";
import { SecretField, type SecretInput } from "./SecretField";

export function SettingRow(props: {
  item: Item;
  draft: Draft;
  onChange: (draft: Draft) => void;
  /** Puts the setting back to its default; the button is shown only where there is one to go back to. */
  onReset?: () => void;
  /** Added to the control's id, so two forms on a screen never share one. */
  idPrefix?: string;
  disabled: boolean;
  depth: number;
  /** The switch this setting depends on, when it is off. */
  gate: Item | null;
  canList: boolean;
  /** Where a secret setting can be typed: given, a setting that holds a secret offers a password box. */
  secret?: SecretInput;
}) {
  const { t, has } = useWords();
  const [picking, setPicking] = useState(false);
  const chooser = useRef<HTMLButtonElement>(null);
  const { item, draft } = props;
  const id = `${props.idPrefix ?? ""}setting-${item.key}`;
  const label = labelOf(item, t, has);
  const readOnly = item.type === "other" || (!item.locked && !item.editable);
  const note = item.locked
    ? t(item.source === "env" ? "settings.locked_env" : "settings.locked_flag")
    : readOnly
      ? item.plugin
        ? t("settings.changed_in_addon")
        : t("settings.changed_in", { file: fileName(item) })
      : null;
  const hint = label !== item.description ? item.description : null;
  const parsed = !readOnly && !item.locked && draft !== toDraft(item) ? fromDraft(item, draft) : null;
  const invalid = parsed && !parsed.ok ? t(`settings.invalid.${parsed.problem}`) : null;
  const waiting = props.gate ? t(props.gate.type === "yes_no" ? "settings.needs_on" : "settings.needs_value", { label: labelOf(props.gate, t, has) }) : null;
  const describedBy = [hint && `${id}-hint`, waiting && `${id}-waiting`, item.type === "list" && `${id}-list`, invalid && `${id}-bad`, note && `${id}-note`, `${id}-default`]
    .filter(Boolean)
    .join(" ");
  const off = item.locked || props.disabled || props.gate !== null;
  const option = (o: string) => (has(`settings.option.${item.key}.${o}`) ? t(`settings.option.${item.key}.${o}`) : o);
  // A list of languages shows each tag as its name in the browser's language, in the order of those names.
  const choices =
    item.choices === "languages"
      ? languageChoices(item.options ?? []).map((c) => ({ tag: c.tag, label: c.label }))
      : (item.options ?? []).map((o) => ({ tag: o, label: option(o) }));

  const typedSecret = !!props.secret && item.secret === true && item.type === "text" && !readOnly && !item.locked;
  let control;
  if (typedSecret && props.secret) {
    const secret = props.secret;
    control = (
      <SecretField
        id={id}
        labelId={`${id}-label`}
        label={label}
        local={secret.local}
        held={secret.held[item.key] ?? null}
        reference={String(draft)}
        onReference={(reference) => props.onChange(reference)}
        pasted={secret.pasted[item.key] ?? ""}
        onPaste={(value) => secret.onPaste(item.key, value)}
        disabled={off}
        describedBy={describedBy}
      />
    );
  } else if (readOnly) {
    control = (
      <p className="setting-value" id={id}>
        {formatValue(item.value, t)}
      </p>
    );
  } else if (item.type === "yes_no") {
    control = (
      <input
        id={id}
        type="checkbox"
        checked={draft === true}
        disabled={off}
        aria-describedby={describedBy}
        onChange={(e) => props.onChange(e.target.checked)}
      />
    );
  } else if (item.type === "choice") {
    control = (
      <select id={id} value={String(draft)} disabled={off} aria-describedby={describedBy} onChange={(e) => props.onChange(e.target.value)}>
        {choices.map((c) => (
          <option key={c.tag} value={c.tag}>
            {c.label}
          </option>
        ))}
      </select>
    );
  } else if (item.type === "list") {
    control = (
      <textarea
        id={id}
        className="short"
        value={String(draft)}
        disabled={off}
        aria-describedby={describedBy}
        onChange={(e) => props.onChange(e.target.value)}
      />
    );
  } else {
    const input = (
      <input
        id={id}
        type="text"
        inputMode={item.type === "text" ? undefined : "decimal"}
        value={String(draft)}
        disabled={off}
        aria-invalid={invalid ? true : undefined}
        aria-describedby={describedBy}
        onChange={(e) => props.onChange(e.target.value)}
      />
    );
    // A folder can be picked from a list where the app can list folders; otherwise it is typed, with no fuss.
    control =
      item.picker === "folder" && props.canList ? (
        <div className="inline-field">
          {input}
          <button type="button" className="btn primary" ref={chooser} disabled={off} onClick={() => setPicking(true)}>
            {t("settings.choose_folder")}
            <span className="sr"> {label}</span>
          </button>
          {String(draft) !== "" && (
            <button type="button" className="btn quiet" disabled={off} onClick={() => props.onChange("")}>
              {t("settings.clear_value")}
              <span className="sr"> {label}</span>
            </button>
          )}
        </div>
      ) : (
        input
      );
  }

  const checkbox = item.type === "yes_no" && !readOnly;
  return (
    <div
      className={`setting${props.depth ? " dependent" : ""}${props.gate ? " waiting" : ""}`}
      data-key={item.key}
      style={props.depth ? { marginInlineStart: `${Math.min(props.depth, 3) * 20}px` } : undefined}
    >
      {checkbox ? (
        <label className="check-line" htmlFor={id}>
          {control}
          <span>{label}</span>
        </label>
      ) : readOnly ? (
        <span className="setting-label">{label}</span>
      ) : typedSecret ? (
        <span className="setting-label" id={`${id}-label`}>
          {label}
        </span>
      ) : (
        <label className="setting-label" htmlFor={id}>
          {label}
        </label>
      )}
      {checkbox ? null : control}
      {hint && (
        <p className="hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      {waiting && (
        <p className="hint" id={`${id}-waiting`}>
          {waiting}
        </p>
      )}
      {item.type === "list" && !readOnly && (
        <p className="hint" id={`${id}-list`}>
          {t("settings.list_hint")}
        </p>
      )}
      {invalid && (
        <p className="problem-note" id={`${id}-bad`}>
          {invalid}
        </p>
      )}
      {note && (
        <p className="hint" id={`${id}-note`}>
          {note}
        </p>
      )}
      <div className="setting-foot">
        {item.type !== "other" && (
          <p className="hint" id={`${id}-default`}>
            {t("settings.default", { value: formatValue(item.default, t) })}
          </p>
        )}
        {item.source === "file" && item.editable && !item.locked && props.onReset && (
          <button
            type="button"
            className="btn quiet small"
            disabled={props.disabled}
            aria-label={t("settings.back_to_default_named", { label })}
            onClick={props.onReset}
          >
            {t("settings.back_to_default")}
          </button>
        )}
      </div>
      {picking && (
        <FolderPicker
          start={String(draft) || undefined}
          onClose={() => {
            setPicking(false);
            restoreFocus(() => chooser.current);
          }}
          onPick={(picked) => {
            setPicking(false);
            props.onChange(picked);
            restoreFocus(() => chooser.current);
          }}
        />
      )}
    </div>
  );
}

/** A form made of setting items, one row each, with the drafts held by the caller. A setting that depends on a switch
 * is indented under it and greyed while the switch is off. */
export function ItemFields(props: {
  items: Item[];
  edits: Record<string, Draft>;
  onEdit: (key: string, draft: Draft) => void;
  disabled?: boolean;
  idPrefix: string;
  /** Lets secret settings be typed (a source's form); left out, they are plain text boxes for where they are kept. */
  secret?: SecretInput;
}) {
  const canList = useFolderListing(props.items.some((i) => i.picker === "folder"));
  return (
    <>
      {props.items.map((item) => {
        const gate = switchOf(item, props.items);
        return (
          <SettingRow
            key={item.key}
            item={item}
            idPrefix={props.idPrefix}
            draft={item.key in props.edits ? props.edits[item.key] : toDraft(item)}
            onChange={(draft) => props.onEdit(item.key, draft)}
            onReset={() => props.onEdit(item.key, toDraft({ ...item, value: item.default }))}
            disabled={props.disabled ?? false}
            depth={depthOf(item, props.items)}
            gate={gate && isOff(gate, props.edits) ? gate : null}
            canList={canList}
            secret={props.secret}
          />
        );
      })}
    </>
  );
}
