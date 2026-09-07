import type { ServerEvent, SessionStatus } from "../types/events";
import type { ProductMode, RuntimeState } from "../types/workflow";

export interface SessionReportState {
  reportId: string | null;
  status: SessionStatus;
  activeMode: ProductMode | null;
  modeStates: Record<ProductMode, RuntimeState>;
}

/** Computes report lifecycle state without fetching data or triggering side effects. */
export function reduceSessionReportEvent(
  state: SessionReportState,
  event: ServerEvent
): SessionReportState | null {
  if (event.type !== "session_report") return null;

  const mode = state.activeMode ?? "quick";
  return {
    ...state,
    reportId: event.reportId,
    status: "stopped",
    activeMode: null,
    modeStates: {
      ...state.modeStates,
      [mode]: "report"
    }
  };
}
