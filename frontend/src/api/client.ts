const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

export type DesktopDisplayMode = "bilingual" | "translation-only" | "floating" | "compact";

export interface CreateSessionPayload {
  inputMode:
    | "demo"
    | "upload_video"
    | "upload_audio"
    | "url"
    | "microphone"
    | "browser_audio"
    | "screen_window"
    | "system_audio";
  sourceLanguage: string;
  targetLanguage: string;
  productMode: "quick" | "floating";
  sessionName: string;
  domain: string;
  modelProfile: string;
  sourceKey: string;
  sourceFileName?: string;
  sourceUrl?: string;
  sourcePermission?: "idle" | "requesting" | "granted" | "denied";
}

export interface CreateSessionResponse {
  sessionId: string;
  status: string;
}

export interface IssueHandoffPayload {
  source?: string;
  sourceLanguage?: string;
  targetLanguage?: string;
  displayMode: DesktopDisplayMode;
}

export interface IssueHandoffResponse {
  handoffToken: string;
  expiresAt: string;
  deepLinkUrl: string;
}

export interface ClaimHandoffResponse {
  sessionId: string;
  wsUrl: string;
  wsToken: string;
  source: string | null;
  sourceLanguage: string | null;
  targetLanguage: string | null;
  displayMode: DesktopDisplayMode;
  expiresAt: string;
}

export async function createSession(
  payload: CreateSessionPayload
): Promise<CreateSessionResponse> {
  const response = await fetch(`${API_BASE_URL}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw new Error(`Create session failed: ${response.status}`);
  }

  return response.json();
}

export async function issueSessionHandoff(
  sessionId: string,
  payload: IssueHandoffPayload
): Promise<IssueHandoffResponse> {
  const response = await fetch(`${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}/handoff`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw new Error(`Issue handoff failed: ${response.status}`);
  }

  return response.json();
}

export async function claimSessionHandoff(token: string): Promise<ClaimHandoffResponse> {
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
