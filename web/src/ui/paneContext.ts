// What a list's detail pane is doing, for the table inside it (design 7.13): `squeezed` is true while a pane stands beside the
// table and takes its width, so the table keeps only its priority columns; a pane that overlays the table, a drawer or no
// pane leaves the table its whole width.
import { createContext, useContext } from "react";

export interface PaneState {
  squeezed: boolean;
}

export const PaneContext = createContext<PaneState>({ squeezed: false });

export function usePane(): PaneState {
  return useContext(PaneContext);
}
