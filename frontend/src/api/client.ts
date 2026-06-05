const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

export interface CreateSessionPayload {
  inputMode: "demo" | "upload_video" | "browser_audio";
  sourceLanguage: string;
  targetLanguage: string;
}

export interface CreateSessionResponse {
  sessionId: string;
  status: string;
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
