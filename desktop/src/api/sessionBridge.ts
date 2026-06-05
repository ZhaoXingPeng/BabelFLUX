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

export async function claimHandoffToken(token: string): Promise<ClaimedHandoff> {
  const response = await fetch(`${API_BASE_URL}/sessions/handoff/claim`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token })
  });

  if (!response.ok) {
    throw new Error(`Claim handoff failed: ${response.status}`);
  }

  return response.json();
}

export function connectDesktopSession(wsUrl: string, onEvent: (event: ServerEvent) => void): WebSocket {
  const socket = new WebSocket(wsUrl.startsWith("ws") ? wsUrl : `${WS_ORIGIN}${wsUrl}`);

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
