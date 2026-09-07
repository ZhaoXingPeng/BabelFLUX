import { describe, expect, it } from "vitest";
import type { ServerEvent } from "../types/events";
import {
  reduceSessionReportEvent,
  type SessionReportState
} from "./sessionReportState";

const baseState = (): SessionReportState => ({
  reportId: null,
  status: "running",
  activeMode: "quick",
  modeStates: {
    quick: "running",
    floating: "setup"
  }
});

const reportEvent = (reportId: string): ServerEvent => ({
  type: "session_report",
  reportId
});

describe("session report state reducer", () => {
  it("moves the active quick session to report state", () => {
    const previous = baseState();
    const next = reduceSessionReportEvent(previous, reportEvent("quick-report"));

    expect(next).toMatchObject({
      reportId: "quick-report",
      status: "stopped",
      activeMode: null,
      modeStates: { quick: "report", floating: "setup" }
    });
    expect(previous).toMatchObject({
      reportId: null,
      activeMode: "quick",
      modeStates: { quick: "running" }
    });
  });

  it("preserves floating mode when its report arrives", () => {
    const previous: SessionReportState = {
      ...baseState(),
      activeMode: "floating",
      modeStates: { quick: "setup", floating: "running" }
    };

    const next = reduceSessionReportEvent(previous, reportEvent("floating-report"));

    expect(next?.activeMode).toBeNull();
    expect(next?.modeStates).toEqual({ quick: "setup", floating: "report" });
  });

  it("keeps the legacy quick fallback when no mode is active", () => {
    const previous: SessionReportState = {
      ...baseState(),
      activeMode: null,
      modeStates: { quick: "setup", floating: "running" }
    };

    const next = reduceSessionReportEvent(previous, reportEvent("fallback-report"));

    expect(next?.modeStates).toEqual({ quick: "report", floating: "running" });
  });

  it("ignores events that do not represent a report", () => {
    const previous = baseState();
    const event: ServerEvent = {
      type: "error",
      message: "temporary"
    };

    expect(reduceSessionReportEvent(previous, event)).toBeNull();
  });
});
