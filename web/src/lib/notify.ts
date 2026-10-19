// Browser notifications for reminders while the app is open (design 6.32). The browser's own permission is asked for only
// from the button in Settings, never when a screen loads; with no permission nothing is shown.
export type NotifyState = "unsupported" | "default" | "granted" | "denied";

const supported = () => typeof Notification !== "undefined";

/** Whether this browser can show notifications, and whether the person has allowed them. */
export function notifyState(): NotifyState {
  if (!supported()) return "unsupported";
  return Notification.permission;
}

/** Asks the browser for permission; the answer is the new state. Called only from a button the person pressed. */
export async function askNotify(): Promise<NotifyState> {
  if (!supported()) return "unsupported";
  try {
    await Notification.requestPermission();
  } catch {
    // An old browser takes a callback rather than returning a promise; the state is read again below either way.
  }
  return notifyState();
}

/** Shows one notification when they are allowed; the tag keeps one reminder from showing twice. */
export function showNotification(title: string, body?: string, tag?: string): void {
  if (notifyState() !== "granted") return;
  try {
    new Notification(title, { body, tag });
  } catch {
    // A browser that refuses to build one (some phones) simply shows none.
  }
}
