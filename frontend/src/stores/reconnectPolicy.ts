export const WS_RECONNECT_MAX_ATTEMPTS = 3;
export const WS_RECONNECT_BASE_DELAY_MS = 500;

export function reconnectDelayMs(attempt: number): number {
  const normalizedAttempt = Math.max(1, Math.floor(attempt));
  return WS_RECONNECT_BASE_DELAY_MS * 2 ** (normalizedAttempt - 1);
}

export function canReconnect(attempt: number): boolean {
  return Number.isFinite(attempt) && attempt >= 0 && attempt < WS_RECONNECT_MAX_ATTEMPTS;
}
