import { describe, expect, it } from "vitest";
import {
  WS_RECONNECT_MAX_ATTEMPTS,
  reconnectDelayMs,
  canReconnect
} from "./reconnectPolicy";

describe("WebSocket reconnect policy", () => {
  it("uses bounded exponential delays", () => {
    expect(reconnectDelayMs(1)).toBe(500);
    expect(reconnectDelayMs(2)).toBe(1000);
    expect(reconnectDelayMs(3)).toBe(2000);
    expect(reconnectDelayMs(0)).toBe(500);
  });

  it("stops after the configured attempt budget", () => {
    expect(canReconnect(0)).toBe(true);
    expect(canReconnect(WS_RECONNECT_MAX_ATTEMPTS - 1)).toBe(true);
    expect(canReconnect(WS_RECONNECT_MAX_ATTEMPTS)).toBe(false);
    expect(canReconnect(Number.NaN)).toBe(false);
  });
});
