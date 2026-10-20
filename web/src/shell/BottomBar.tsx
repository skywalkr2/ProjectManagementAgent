// The phone's bottom bar (design 7.1): Today, Work, a raised + (Hand something in), Ask and More. Work and More open a
// sheet listing their entries; More also holds the Help items and this device's theme and density.
import { useState } from "react";
import { Dialog, Heading, Link, Modal, ModalOverlay } from "react-aria-components";
import { setDensity, setTheme, useAppearance, type Density, type Theme } from "../lib/theme";
import { viewHref, type View } from "../lib/views";
import { useWords } from "../lib/wording";
import { MISSED_BUTTON, useAnythingToMiss, useMissedOne } from "../components/MissedOne";
import { afterClose } from "../ui/afterClose";
import { Icon } from "../ui/Icon";
import { IconButton } from "../ui/IconButton";
import { SegmentedControl } from "../ui/SegmentedControl";
import { useNav, type NavEntry } from "./nav";
import styles from "./BottomBar.module.css";

function Sheet(props: { title: string; onClose: () => void; children: React.ReactNode }) {
  const { t } = useWords();
  return (
    <ModalOverlay isOpen onOpenChange={(open) => !open && props.onClose()} isDismissable className={styles.overlay}>
      <Modal className={styles.sheet} data-modal-open="">
        <Dialog className={styles.dialog} aria-labelledby="sheet-title">
          <div className={styles.head}>
            <Heading slot="title" id="sheet-title" className={styles.title}>
              {props.title}
            </Heading>
            <IconButton icon="close" label={t("action.close")} onPress={props.onClose} />
          </div>
          {props.children}
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}

function Links(props: { entries: NavEntry[]; current: View; onPick: () => void }) {
  return (
    <div className={styles.list}>
      {props.entries.map((e) => (
        <Link key={e.view} href={viewHref(e.view)} className={styles.link} aria-current={props.current === e.view ? "page" : undefined} onPress={props.onPick}>
          {e.icon ? <Icon name={e.icon} /> : null}
          <span>{e.label}</span>
          {e.count ? <span className={styles.count}>{e.count}</span> : null}
        </Link>
      ))}
    </div>
  );
}

export function BottomBar(props: {
  current: View;
  version: string;
  onHandIn: () => void;
  onAsk: () => void;
  onHelp: () => void;
  onFeedback: () => void;
  onOpenGuide: () => void;
}) {
  const { t } = useWords();
  const nav = useNav();
  const missed = useMissedOne();
  const anythingMissed = useAnythingToMiss();
  const { theme, density } = useAppearance();
  const [sheet, setSheet] = useState<"work" | "more" | null>(null);
  const close = () => setSheet(null);
  const later = (run: () => void) => () => {
    close();
    // The sheet leaves first, so what opens next gets focus and the page behind is no longer inert.
    afterClose(run);
  };
  const todayCurrent = props.current === "today";
  const workCurrent = props.current.startsWith("work/");
  return (
    <>
      <nav className={styles.bar} aria-label={t("nav.label")}>
        <a className={styles.item} href={viewHref("today")} aria-current={todayCurrent ? "page" : undefined}>
          <Icon name="home" />
          {t("nav.home")}
        </a>
        <button type="button" className={styles.item} aria-current={workCurrent ? "page" : undefined} aria-haspopup="dialog" onClick={() => setSheet("work")}>
          <Icon name="inbox" />
          {t("nav.work")}
        </button>
        <span className={styles.plusCell}>
          <button type="button" className={styles.plus} aria-label={t("handin.open")} onClick={props.onHandIn}>
            <Icon name="plus" size={22} />
          </button>
        </span>
        <button type="button" className={styles.item} data-ask-button="" onClick={props.onAsk}>
          <Icon name="chat" />
          {t("ask.open")}
        </button>
        <button type="button" className={styles.item} data-feedback-button="" aria-haspopup="dialog" onClick={() => setSheet("more")}>
          <Icon name="more" />
          {t("nav.more")}
        </button>
      </nav>
      {sheet === "work" && (
        <Sheet title={t("nav.work")} onClose={close}>
          <Links entries={nav.work} current={props.current} onPick={close} />
        </Sheet>
      )}
      {sheet === "more" && (
        <Sheet title={t("nav.more")} onClose={close}>
          <Links entries={[...nav.records, ...nav.bottom]} current={props.current} onPick={close} />
          <p className={styles.section}>{t("header.help")}</p>
          <div className={styles.list}>
            {anythingMissed && (
              <button type="button" className={styles.link} {...{ [MISSED_BUTTON]: "" }} onClick={later(missed)}>
                <Icon name="alert" />
                {t("missed.open")}
              </button>
            )}
            <button type="button" className={styles.link} onClick={later(props.onHelp)}>
              <Icon name="help" />
              {t("help.open")}
            </button>
            <button type="button" className={styles.link} onClick={later(props.onOpenGuide)}>
              <Icon name="check" />
              {t("header.help_guide")}
            </button>
            <button type="button" className={styles.link} onClick={later(props.onFeedback)}>
              <Icon name="chat" />
              {t("feedback.open")}
            </button>
            <button type="button" className={styles.link} disabled>
              {t("app.version", { version: props.version })}
            </button>
          </div>
          <p className={styles.section}>{t("user.theme")}</p>
          <div className={styles.choices}>
            <SegmentedControl<Theme>
              label={t("user.theme")}
              value={theme}
              onChange={setTheme}
              options={(["system", "light", "dark"] as Theme[]).map((id) => ({ value: id, label: t(`user.theme.${id}`) }))}
            />
          </div>
          <p className={styles.section}>{t("user.density")}</p>
          <div className={styles.choices}>
            <SegmentedControl<Density>
              label={t("user.density")}
              value={density}
              onChange={setDensity}
              options={(["comfortable", "compact"] as Density[]).map((id) => ({ value: id, label: t(`user.density.${id}`) }))}
            />
          </div>
        </Sheet>
      )}
    </>
  );
}
