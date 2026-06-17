import type { ServerEvent } from "@frontend/types/events";
import type { LaunchParams } from "../launcherBridge";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";
const WS_ORIGIN = import.meta.env.VITE_BACKEND_WS_ORIGIN ?? "ws://localhost:8000";

export interface ClaimedHandoff {
  sessionId: string;
  wsUrl: string;
  wsToken: string;
  source: string | null;
  sourceLanguage: string | null;
  targetLanguage: string | null;
  displayMode: NonNullable<LaunchParams["displayMode"]>;
  expiresAt: string;
}

function pickString(payload: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function normalizeClaimedHandoff(payload: unknown): ClaimedHandoff {
  const data = (payload ?? {}) as Record<string, unknown>;
  const displayMode = pickString(data, "displayMode", "display_mode") as ClaimedHandoff["displayMode"];
  return {
    sessionId: pickString(data, "sessionId", "session_id"),
    wsUrl: pickString(data, "wsUrl", "ws_url"),
    wsToken: pickString(data, "wsToken", "ws_token"),
    source: pickString(data, "source") || null,
    sourceLanguage: pickString(data, "sourceLanguage", "source_language") || null,
    targetLanguage: pickString(data, "targetLanguage", "target_language") || null,
    displayMode: displayMode || "bilingual",
    expiresAt: pickString(data, "expiresAt", "expires_at")
  };
}

function withWebSocketToken(wsUrl: string, wsToken: string): string {
  if (!wsUrl) {
    throw new Error("桌面接管缺少连接地址，请从 Web 端重新打开悬浮窗");
  }
  const isAbsolute = wsUrl.startsWith("ws://") || wsUrl.startsWith("wss://");
  const base = isAbsolute ? undefined : WS_ORIGIN;
  const url = new URL(wsUrl, base);
  if (!url.searchParams.get("token") && wsToken) {
    url.searchParams.set("token", wsToken);
  }
  if (!url.searchParams.get("token")) {
    throw new Error("桌面接管缺少连接凭证，请从 Web 端重新打开悬浮窗");
  }
  if (isAbsolute) return url.toString();
  return `${url.pathname}${url.search}${url.hash}`;
}

function toWebSocketUrl(wsUrl: string): string {
  if (wsUrl.startsWith("ws://") || wsUrl.startsWith("wss://")) return wsUrl;
  return new URL(wsUrl, WS_ORIGIN).toString();
}

export async function claimHandoffToken(token: string): Promise<ClaimedHandoff> {
  const response = await fetch(`${API_BASE_URL}/sessions/handoff/claim`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token })
  });

  if (!response.ok) {
    throw new Error(`Claim handoff failed: ${response.status}`);
  }

  const claim = normalizeClaimedHandoff(await response.json());
  if (!claim.wsUrl && claim.sessionId) {
    claim.wsUrl = `/api/ws/sessions/${encodeURIComponent(claim.sessionId)}`;
  }
  claim.wsUrl = withWebSocketToken(claim.wsUrl, claim.wsToken);
  return claim;
}

export function connectDesktopSession(
  wsUrl: string,
  onEvent: (event: ServerEvent) => void,
  wsToken = ""
): WebSocket {
  const normalizedUrl = withWebSocketToken(wsUrl, wsToken);
  const socket = new WebSocket(toWebSocketUrl(normalizedUrl));

  socket.addEventListener("open", () => {
    socket.send(JSON.stringify({ type: "start_session" }));
  });

  socket.addEventListener("message", (message) => {
    try {
      onEvent(JSON.parse(message.data) as ServerEvent);
    } catch {
      onEvent({ type: "error", message: "桌面端事件解析失败" });
    }
  });

  socket.addEventListener("error", () => onEvent({ type: "error", message: "桌面端 WebSocket 异常" }));
  return socket;
}
