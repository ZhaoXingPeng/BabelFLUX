import type { ServerEvent } from "../types/events";

const WS_BASE_URL = import.meta.env.VITE_BACKEND_WS_URL ?? "ws://localhost:8000/api";

interface SessionSocketHandlers {
  onEvent: (event: ServerEvent) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (message: string) => void;
}

interface SessionSocketOptions {
  autoStart?: boolean;
  token?: string;
}

export function createSessionSocket(
  sessionId: string,
  handlers: SessionSocketHandlers,
  options: SessionSocketOptions = {}
): WebSocket {
  const url = new URL(`${WS_BASE_URL}/ws/sessions/${sessionId}`);
  if (options.token) url.searchParams.set("token", options.token);
  const socket = new WebSocket(url.toString());

  socket.addEventListener("open", () => {
    handlers.onOpen?.();
    if (options.autoStart ?? true) {
      socket.send(JSON.stringify({ type: "start_session" }));
    }
  });

  socket.addEventListener("message", (message) => {
    try {
      handlers.onEvent(JSON.parse(message.data) as ServerEvent);
    } catch {
      handlers.onError?.("后端事件解析失败");
    }
  });

  socket.addEventListener("close", () => handlers.onClose?.());
  socket.addEventListener("error", () => handlers.onError?.("WebSocket 连接异常"));

  return socket;
}
