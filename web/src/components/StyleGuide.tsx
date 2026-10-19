// The style guide (design 7.11): every shared component in every state, the type scale and the color roles, in light and
// dark. It is shown only for a demo workspace or in development, and is not in the sidebar (#styleguide).
import { useEffect, useId, useState } from "react";
import { Heading } from "react-aria-components";
import { applyTheme, useAppearance, type Theme } from "../lib/theme";
import { useToasts } from "../lib/toasts";
import { useWords } from "../lib/wording";
import { Button } from "../ui/Button";
import { Drawer } from "../ui/Drawer";
import { EmptyState } from "../ui/EmptyState";
import { ICON_NAMES, Icon } from "../ui/Icon";
import { IconButton } from "../ui/IconButton";
import { LoadFailed } from "../ui/LoadFailed";
import { MenuButton } from "../ui/MenuButton";
import { Panel } from "../ui/Panel";
import { Pill } from "../ui/Pill";
import { Row } from "../ui/Row";
import { SegmentedControl } from "../ui/SegmentedControl";
import { Skeleton } from "../ui/Skeleton";
import { StatusChip } from "../ui/StatusChip";
import { ModalPanel, restoreFocus } from "./ModalPanel";
import styles from "./StyleGuide.module.css";

const TYPE_SCALE = [
  { token: "text-2xl", weight: "semibold" },
  { token: "text-xl", weight: "semibold" },
  { token: "text-lg", weight: "semibold" },
  { token: "text-md", weight: "semibold" },
  { token: "text-md", weight: "regular" },
  { token: "text-sm", weight: "medium" },
  { token: "text-xs", weight: "semibold" },
] as const;

/** The color roles: the token that fills them, the one drawn on top, and what each is for. */
const ROLES = [
  { token: "canvas", on: "text", use: "canvas" },
  { token: "surface", on: "text", use: "surface" },
  { token: "surface-sunk", on: "text-muted", use: "sunk" },
  { token: "accent", on: "text-on-accent", use: "accent" },
  { token: "accent-soft", on: "accent-text", use: "accent_soft" },
  { token: "warn-soft", on: "warn", use: "warn" },
  { token: "danger-soft", on: "danger", use: "danger" },
  { token: "ok-soft", on: "ok", use: "ok" },
  { token: "mark", on: "mark-text", use: "mark" },
] as const;

const WEIGHT = { regular: "var(--weight-regular)", medium: "var(--weight-medium)", semibold: "var(--weight-semibold)" } as const;

function Section(props: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <Panel title={props.title}>
      <div className={styles.stack}>
        {props.note && <p className={styles.caption}>{props.note}</p>}
        {props.children}
      </div>
    </Panel>
  );
}

export function StyleGuide() {
  const { t } = useWords();
  const { push } = useToasts();
  const device = useAppearance();
  const [theme, setThemeShown] = useState<Theme>(device.theme);
  const [filter, setFilter] = useState("send");
  const [drawer, setDrawer] = useState(false);
  const [dialog, setDialog] = useState(false);
  const [draft, setDraft] = useState("");
  const [choice, setChoice] = useState("a");
  const fieldId = useId();

  // The page's own theme toggle shows both themes without changing what this device remembers.
  useEffect(() => {
    applyTheme(theme);
    return () => applyTheme(device.theme);
  }, [theme, device.theme]);

  return (
    <div className={styles.page}>
      <div className={styles.top}>
        <h1>{t("styleguide.title")}</h1>
        <SegmentedControl<Theme>
          label={t("styleguide.theme")}
          value={theme}
          onChange={setThemeShown}
          options={(["system", "light", "dark"] as Theme[]).map((id) => ({ value: id, label: t(`user.theme.${id}`) }))}
        />
      </div>

      <Section title={t("styleguide.type")} note={t("styleguide.type_note")}>
        <div className={styles.scale}>
          {TYPE_SCALE.map((row) => (
            <div key={`${row.token}-${row.weight}`} className={styles.scaleRow}>
              <span className={styles.token}>
                --{row.token} · {row.weight}
              </span>
              <span style={{ fontSize: `var(--${row.token})`, lineHeight: `var(--lh-${row.token.slice(5)})`, fontWeight: WEIGHT[row.weight] }}>{t("styleguide.sample_text")}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title={t("styleguide.colors")} note={t("styleguide.colors_note")}>
        <div className={styles.swatches}>
          {ROLES.map((role) => (
            <div key={role.token} className={styles.swatch} style={{ background: `var(--${role.token})`, color: `var(--${role.on})` }}>
              <span className={styles.token} style={{ color: "inherit" }}>
                --{role.token}
              </span>
              <span>{t(`styleguide.role.${role.use}`)}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title={t("styleguide.buttons")} note={t("styleguide.buttons_note")}>
        <div className={styles.demo}>
          <Button variant="primary">{t("styleguide.primary")}</Button>
          <Button>{t("styleguide.secondary")}</Button>
          <Button variant="ghost">{t("styleguide.ghost")}</Button>
          <Button variant="danger">{t("styleguide.danger")}</Button>
          <Button variant="primary" size="sm">
            {t("styleguide.small")}
          </Button>
          <Button icon="plus" variant="primary">
            {t("styleguide.with_icon")}
          </Button>
          <Button loading variant="primary">
            {t("styleguide.loading")}
          </Button>
          <Button loading>{t("styleguide.loading")}</Button>
        </div>
        <div className={styles.demo}>
          <Button variant="primary" disabled reason={t("styleguide.reason")}>
            {t("styleguide.primary")}
          </Button>
          <Button disabled reason={t("styleguide.reason")}>
            {t("styleguide.secondary")}
          </Button>
          <Button variant="ghost" disabled>
            {t("styleguide.ghost")}
          </Button>
          <Button variant="danger" disabled reason={t("styleguide.reason")}>
            {t("styleguide.danger")}
          </Button>
        </div>
        <div className={styles.demo}>
          <IconButton icon="help" label={t("styleguide.icon_help")} />
          <IconButton icon="refresh" label={t("styleguide.icon_refresh")} variant="secondary" />
          <IconButton icon="close" label={t("styleguide.icon_close")} size="sm" />
          <IconButton icon="more" label={t("styleguide.icon_more")} isDisabled />
        </div>
      </Section>

      <Section title={t("styleguide.pills")} note={t("styleguide.pills_note")}>
        <div className={styles.demo}>
          <Pill>{t("styleguide.pill_neutral")}</Pill>
          <Pill tone="need">{t("styleguide.pill_need")}</Pill>
          <Pill tone="warn">{t("styleguide.pill_warn")}</Pill>
          <Pill tone="danger">{t("styleguide.pill_danger")}</Pill>
          <Pill tone="ok">{t("styleguide.pill_ok")}</Pill>
          <StatusChip aria-label={t("styleguide.chip_live")}>{t("styleguide.chip_live")}</StatusChip>
          <StatusChip tone="warn" aria-label={t("styleguide.chip_warn")}>
            {t("styleguide.chip_warn")}
          </StatusChip>
        </div>
      </Section>

      <Panel title={t("styleguide.rows")} count={4} flush>
        <ul className={styles.list}>
          <Row
            pill={<Pill tone="need">{t("styleguide.pill_need")}</Pill>}
            title={t("styleguide.row_title")}
            meta={t("styleguide.row_meta")}
            primary={<Button variant="primary" size="sm">{t("styleguide.row_primary")}</Button>}
            menu={<MenuButton groups={[{ id: "a", entries: [{ id: "x", label: t("styleguide.menu_item") }] }]} trigger={<IconButton icon="more" size="sm" label={t("styleguide.icon_more")} tooltip={false} />} />}
          />
          <Row
            selected
            pill={<Pill tone="warn">{t("styleguide.pill_warn")}</Pill>}
            title={t("styleguide.row_title")}
            meta={t("styleguide.row_meta")}
            primary={<Button variant="primary" size="sm">{t("styleguide.row_primary")}</Button>}
          />
          <Row title={t("styleguide.row_long")} meta={t("styleguide.row_meta")} primary={<Button size="sm">{t("styleguide.row_primary")}</Button>} />
          <Row pill={<Pill tone="danger">{t("styleguide.pill_danger")}</Pill>} title={t("styleguide.row_title")}>
            <p className={styles.caption}>{t("styleguide.row_expanded")}</p>
          </Row>
        </ul>
      </Panel>

      <Section title={t("styleguide.segmented")}>
        <div className={styles.demo}>
          <SegmentedControl
            label={t("styleguide.segmented")}
            value={filter}
            onChange={setFilter}
            options={[
              { value: "send", label: t("styleguide.seg_a") },
              { value: "waiting", label: t("styleguide.seg_b") },
              { value: "all", label: t("styleguide.seg_c") },
            ]}
          />
        </div>
      </Section>

      <Section title={t("styleguide.states")} note={t("styleguide.states_note")}>
        <div className={styles.stack}>
          <Panel title={t("styleguide.empty")} small>
            <EmptyState icon="inbox" text={t("styleguide.empty_text")} action={{ label: t("styleguide.empty_action"), onClick: () => undefined }} />
          </Panel>
          <Panel title={t("styleguide.empty_inline")} small>
            <EmptyState inline text={t("styleguide.empty_inline_text")} action={{ label: t("styleguide.empty_inline_action"), onClick: () => undefined }} />
          </Panel>
          <Panel title={t("styleguide.failed")} small>
            <LoadFailed message={t("styleguide.failed_text")} detail={t("styleguide.failed_detail")} onRetry={() => undefined} />
          </Panel>
          <Panel title={t("styleguide.skeleton")} small flush>
            <Skeleton rows={3} />
          </Panel>
        </div>
      </Section>

      <Section title={t("styleguide.floating")} note={t("styleguide.floating_note")}>
        <div className={styles.demo}>
          <Button
            id="styleguide-drawer"
            onClick={() => {
              setDraft("");
              setDrawer(true);
            }}
          >
            {t("styleguide.open_drawer")}
          </Button>
          <Button id="styleguide-dialog" onClick={() => setDialog(true)}>
            {t("styleguide.open_dialog")}
          </Button>
          <MenuButton
            placement="bottom start"
            groups={[
              { id: "one", entries: [{ id: "a", label: t("styleguide.menu_item"), icon: "check" }, { id: "b", label: t("styleguide.menu_disabled"), disabled: true, reason: t("styleguide.reason") }] },
              { id: "two", title: t("user.theme"), selected: "light", entries: [{ id: "light", label: t("user.theme.light"), icon: "sun" }, { id: "dark", label: t("user.theme.dark"), icon: "moon" }] },
            ]}
            trigger={<Button icon="chevron-down">{t("styleguide.open_menu")}</Button>}
          />
          <Button onClick={() => push({ message: t("styleguide.toast"), undo: () => undefined })}>{t("styleguide.show_toast")}</Button>
          <Button
            onClick={() => {
              push({ message: t("styleguide.toast"), undo: () => undefined });
              push({ message: t("styleguide.toast_b"), undo: () => undefined });
              // Several choices and an Undo: the buttons wrap under the words, which keep a width that reads.
              push({
                message: t("styleguide.toast_c"),
                action: { label: t("styleguide.toast_c_action"), run: () => undefined },
                more: [{ label: t("styleguide.toast_c_more"), run: () => undefined }],
                undo: () => undefined,
              });
            }}
          >
            {t("styleguide.show_toasts")}
          </Button>
        </div>
      </Section>

      <Section title={t("styleguide.forms")} note={t("styleguide.forms_note")}>
        <div className={styles.form}>
          <div className="field">
            <label htmlFor={`${fieldId}-a`}>{t("styleguide.field")}</label>
            <input id={`${fieldId}-a`} placeholder={t("styleguide.placeholder")} />
            <p className="hint">{t("styleguide.hint")}</p>
          </div>
          <div className="field">
            <label htmlFor={`${fieldId}-b`}>{t("styleguide.field_error")}</label>
            <input id={`${fieldId}-b`} className={styles.invalid} defaultValue={t("styleguide.value")} aria-invalid="true" aria-describedby={`${fieldId}-e`} />
            <p id={`${fieldId}-e`} className={styles.error}>
              {t("styleguide.error")}
            </p>
          </div>
          <div className="field">
            <label htmlFor={`${fieldId}-c`}>{t("styleguide.field_disabled")}</label>
            <input id={`${fieldId}-c`} disabled defaultValue={t("styleguide.value")} />
          </div>
          <div className="field">
            <label htmlFor={`${fieldId}-d`}>{t("styleguide.field_select")}</label>
            <select id={`${fieldId}-d`}>
              <option>{t("styleguide.seg_a")}</option>
              <option>{t("styleguide.seg_b")}</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor={`${fieldId}-f`}>{t("styleguide.field_text")}</label>
            <textarea id={`${fieldId}-f`} className="short" />
          </div>
          <div className={styles.choiceRow}>
            <label className={styles.choice}>
              <input type="checkbox" defaultChecked /> {t("styleguide.check_on")}
            </label>
            <label className={styles.choice}>
              <input type="checkbox" /> {t("styleguide.check_off")}
            </label>
            <label className={styles.choice}>
              <input type="checkbox" disabled /> {t("styleguide.check_disabled")}
            </label>
            <label className={styles.choice}>
              <input type="radio" name={`${fieldId}-r`} checked={choice === "a"} onChange={() => setChoice("a")} /> {t("styleguide.seg_a")}
            </label>
            <label className={styles.choice}>
              <input type="radio" name={`${fieldId}-r`} checked={choice === "b"} onChange={() => setChoice("b")} /> {t("styleguide.seg_b")}
            </label>
          </div>
        </div>
      </Section>

      <Section title={t("styleguide.evidence")} note={t("styleguide.evidence_note")}>
        <div className={styles.stack}>
          <p className="because">
            {t("styleguide.because")} <q>{t("styleguide.quote")}</q> <a href="#styleguide">{t("styleguide.source")}</a>
          </p>
          <div className="source">
            <p className="src">
              {t("styleguide.source_from")} <Pill>{t("styleguide.outside")}</Pill>
            </p>
            <p>
              {t("styleguide.source_before")} <mark>{t("styleguide.source_marked")}</mark> {t("styleguide.source_after")}
            </p>
          </div>
        </div>
      </Section>

      <Section title={t("styleguide.icons")} note={t("styleguide.icons_note")}>
        <div className={styles.icons}>
          {ICON_NAMES.map((name) => (
            <div key={name} className={styles.icon}>
              <Icon name={name} size={18} />
              <span className={styles.token}>{name}</span>
            </div>
          ))}
        </div>
      </Section>

      <Drawer open={drawer} title={t("styleguide.drawer_title")} dirty={draft !== ""} onClose={() => { setDrawer(false); }} footer={<Button variant="primary" onClick={() => setDrawer(false)}>{t("styleguide.drawer_save")}</Button>}>
        <div className="field">
          <label htmlFor={`${fieldId}-g`}>{t("styleguide.field_text")}</label>
          <textarea id={`${fieldId}-g`} value={draft} onChange={(e) => setDraft(e.target.value)} />
          <p className="hint">{t("styleguide.drawer_hint")}</p>
        </div>
      </Drawer>
      {dialog && (
        <ModalPanel
          titleId="styleguide-dialog-title"
          onClose={() => {
            setDialog(false);
            restoreFocus(() => document.getElementById("styleguide-dialog"));
          }}
        >
          <Heading slot="title" id="styleguide-dialog-title">
            {t("styleguide.dialog_title")}
          </Heading>
          <p>{t("styleguide.dialog_text")}</p>
          <div className="row-end">
            <Button
              onClick={() => {
                setDialog(false);
                restoreFocus(() => document.getElementById("styleguide-dialog"));
              }}
            >
              {t("action.cancel")}
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                setDialog(false);
                restoreFocus(() => document.getElementById("styleguide-dialog"));
              }}
            >
              {t("styleguide.danger")}
            </Button>
          </div>
        </ModalPanel>
      )}
    </div>
  );
}
