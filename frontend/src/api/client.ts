export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

export type DesktopDisplayMode = "bilingual" | "translation-only" | "floating" | "compact";

export interface CreateSessionPayload {
  inputMode:
    | "demo"
    | "url"
    | "microphone"
    | "browser_audio"
    | "screen_window"
    | "media_element_audio"
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
  ttsEnabled?: boolean;
}

export interface CreateSessionResponse {
  sessionId: string;
  wsToken: string;
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

export type ReportFormat = "txt" | "srt" | "md" | "json";

export interface SessionReportMetrics {
  segments: number;
  realtimeRevisions: number;
  finalRevisions: number;
  durationText: string;
}

export interface SessionReportSegment {
  segmentId: string;
  startMs: number;
  endMs: number;
  timecode: string;
  sourceText: string;
  liveTranslation: string;
  finalTranslation: string;
  revisedRealtime: boolean;
}

export interface SessionReportRevision {
  segmentId: string;
  beforeText: string;
  afterText: string;
  reason: string;
  stage?: string;
}

export interface SessionReport {
  reportId: string;
  sessionId: string;
  sessionName: string;
  domain: string;
  sourceLanguage: string;
  targetLanguage: string;
  modelProfile?: string;
  durationMs: number;
  durationText: string;
  generatedAt: string;
  summary: string;
  qualityNotes: string;
  glossaryHits: { term: string; translation: string }[];
  metrics: SessionReportMetrics;
  segments: SessionReportSegment[];
  finalRevisions: SessionReportRevision[];
  realtimeRevisions: SessionReportRevision[];
  correctionModel: string | null;
  correctionStatus?: "completed" | "partial" | "fallback" | "timeout" | "skipped" | "pending";
  correctionError?: string;
  correctionElapsedMs?: number;
}

export interface SessionHistoryEntry {
  sessionId: string;
  reportId: string | null;
  sessionName: string;
  productMode: string;
  inputMode: string;
  sourceLabel: string;
  domain: string;
  modelProfile?: string;
  sourceLanguage: string;
  targetLanguage: string;
  status: "created" | "running" | "correcting" | "completed" | "fallback" | "failed" | string;
  startedAt: string;
  endedAt: string | null;
  durationMs: number;
  segmentCount: number;
  realtimeRevisionCount: number;
  finalRevisionCount: number;
  correctionStatus?: "completed" | "partial" | "fallback" | "timeout" | "skipped" | "pending";
  updatedAt: string;
  availableFormats: ReportFormat[];
}

export interface SessionHistoryListResponse {
  items: SessionHistoryEntry[];
}

export async function getSessionReport(sessionId: string): Promise<SessionReport> {
  const response = await fetch(`${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}/report`);
  if (!response.ok) {
    throw new Error(`Get report failed: ${response.status}`);
  }
  return response.json();
}

export async function getSessionHistory(): Promise<SessionHistoryEntry[]> {
  const response = await fetch(`${API_BASE_URL}/sessions/history`);
  if (!response.ok) {
    throw new Error(`Get session history failed: ${response.status}`);
  }
  const payload = (await response.json()) as SessionHistoryListResponse;
  return payload.items;
}

export async function deleteSessionHistory(sessionId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/sessions/history/${encodeURIComponent(sessionId)}`, {
    method: "DELETE"
  });
  if (!response.ok) {
    throw new Error(`Delete session history failed: ${response.status}`);
  }
}

/** 报告下载直链（浏览器据 Content-Disposition 触发下载，含中文文件名已 RFC 5987 兜底）。 */
export function reportDownloadUrl(sessionId: string, format: ReportFormat): string {
  return `${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}/report/download?format=${format}`;
}
