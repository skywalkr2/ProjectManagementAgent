// Runs something once the menu, popover or sheet an action was chosen in has finished closing. They hand focus back to what
// opened them a frame after they go, so an action that moves focus somewhere of its own (a heading, a field) waits two
// frames to have the last word.
export function afterClose(run: () => void): void {
  window.requestAnimationFrame(() => window.requestAnimationFrame(run));
}
