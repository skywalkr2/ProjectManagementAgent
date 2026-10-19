// The header (design 7.1): one row, 56px, from 1280px up. Left to right: the brand (a link to Today), a Demo chip, Ask as a
// search-style field, the status chip with the assistant's alive line beside it, Missed one, Hand something in, Help and the person's
// initials, which open the user menu. Below 1280px the status chip and the alive line move to a second small row under
// the rest; below 1024px the Ask field becomes an icon; on a phone one row remains, with the logo, the status chip and the
// user menu, and the assistant's state is in the chip's popover.
import { useQuery } from "@tanstack/react-query";
import { Button as AriaButton } from "react-aria-components";
import { api, type S } from "../lib/api";
import type { LiveState } from "../lib/live";
import { setDensity, setTheme, useAppearance, type Density, type Theme } from "../lib/theme";
import { viewHref } from "../lib/views";
import { useWords } from "../lib/wording";
import { MISSED_BUTTON, useMissedOne } from "../components/MissedOne";
import { afterClose } from "../ui/afterClose";
import { Button } from "../ui/Button";
import { Icon } from "../ui/Icon";
import { IconButton } from "../ui/IconButton";
import { MenuButton, type MenuGroup } from "../ui/MenuButton";
import { Pill } from "../ui/Pill";
import { AssistantLine } from "./AssistantLine";
import { StatusMenu } from "./StatusMenu";
import { initials } from "./status";
import styles from "./Header.module.css";

/** The menu of this device's appearance: theme and density, each a choice with a check. Shared with the phone's More sheet. */
export function useAppearanceGroups(): MenuGroup[] {
  const { t } = useWords();
  const { theme, density } = useAppearance();
  return [
    {
      id: "theme",
      title: t("user.theme"),
      selected: theme,
      entries: (["system", "light", "dark"] as Theme[]).map((id) => ({
        id,
        label: t(`user.theme.${id}`),
        icon: id === "system" ? "monitor" : id === "light" ? "sun" : "moon",
        run: () => setTheme(id),
      })),
    },
    {
      id: "density",
      title: t("user.density"),
      selected: density,
      entries: (["comfortable", "compact"] as Density[]).map((id) => ({ id, label: t(`user.density.${id}`), run: () => setDensity(id) })),
    },
  ];
}

/** The groups of the Help menu: the shortcuts, the setup guide, feedback, and the version as a line that does nothing. */
export function useHelpGroups(handlers: { onHelp: () => void; onOpenGuide: () => void; onFeedback: () => void }, version: string): MenuGroup[] {
  const { t } = useWords();
  return [
    {
      id: "help",
      entries: [
        { id: "shortcuts", label: t("help.open"), icon: "help", run: handlers.onHelp },
        { id: "guide", label: t("header.help_guide"), icon: "check", run: () => afterClose(handlers.onOpenGuide) },
        { id: "feedback", label: t("feedback.open"), icon: "chat", run: handlers.onFeedback },
      ],
    },
    { id: "version", entries: [{ id: "version", label: t("app.version", { version }), disabled: true }] },
  ];
}

/** The person's name for the avatar: their own, when the workspace knows it, else the workspace's. */
export function usePersonName(workspace: string): string {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  return me.data?.full_name?.trim() || workspace;
}

export function Header(props: {
  rc: Pick<S["RuntimeConfig"], "workspace_name" | "assistant_name" | "demo" | "logo" | "api_base" | "version">;
  live: { state: LiveState; lastUpdate: Date | null; refresh: () => void };
  narrow: boolean;
  shortcuts: Record<string, string>;
  onHandIn: () => void;
  onAsk: () => void;
  onHelp: () => void;
  onFeedback: () => void;
  onOpenGuide: (step?: string) => void;
}) {
  const { t } = useWords();
  const { rc } = props;
  const person = usePersonName(rc.workspace_name);
  const appearance = useAppearanceGroups();
  const helpGroups = useHelpGroups({ onHelp: props.onHelp, onOpenGuide: () => props.onOpenGuide(), onFeedback: props.onFeedback }, rc.version);
  const askKey = props.shortcuts.ask ?? "/";
  const missed = useMissedOne();
  return (
    <header className={styles.header}>
      <a className={styles.brand} href={viewHref("today")} aria-label={t("nav.brand_named", { name: rc.workspace_name })} title={rc.workspace_name}>
        {rc.logo ? (
          <img className={styles.logo} src={`${rc.api_base}/brand/logo`} alt="" />
        ) : (
          <span className={styles.mark} aria-hidden="true">
            {initials(rc.workspace_name)}
          </span>
        )}
        {!props.narrow && <span className={styles.name}>{rc.workspace_name}</span>}
      </a>
      {rc.demo && (
        <span className={styles.chip}>
          <Pill tone="warn">{t("demo.label")}</Pill>
        </span>
      )}
      {!props.narrow && (
        <>
          <button type="button" className={styles.ask} data-ask-button aria-label={t("ask.open")} aria-keyshortcuts={askKey} onClick={props.onAsk}>
            <Icon name="search" />
            <span className={styles.askText}>{t("header.ask_field")}</span>
            <kbd>{askKey}</kbd>
          </button>
          <IconButton icon="search" label={t("ask.open")} className={styles.askIcon} data-ask-button="" onPress={props.onAsk} />
        </>
      )}
      <span className={styles.spacer} />
      <div className={styles.status}>
        <StatusMenu live={props.live} demo={rc.demo} onOpenGuide={props.onOpenGuide} narrow={props.narrow} />
        {!props.narrow && <AssistantLine onOpenGuide={props.onOpenGuide} />}
      </div>
      {!props.narrow && (
        <div className={styles.end}>
          <IconButton icon="alert" label={t("missed.open")} {...{ [MISSED_BUTTON]: "" }} onPress={missed} />
          <Button variant="primary" icon="plus" onClick={props.onHandIn}>
            {t("handin.open")}
          </Button>
          <MenuButton groups={helpGroups} trigger={<IconButton icon="help" label={t("header.help")} data-feedback-button="" />} />
        </div>
      )}
      <MenuButton
        groups={appearance}
        trigger={
          <AriaButton className={styles.avatar} aria-label={t("user.open", { name: person })}>
            {initials(person)}
          </AriaButton>
        }
      />
    </header>
  );
}
