export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

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

export interface UploadMediaResponse {
  mediaId: string;
  fileName: string;
  sizeBytes: number;
}

/** 上传本地媒体字节到会话（upload_video / upload_audio 模式必需，须在 start_session 之前完成）。 */
export async function uploadSessionMedia(
  sessionId: string,
  file: File
): Promise<UploadMediaResponse> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}/media`, {
    method: "POST",
    body
  });
  if (!response.ok) {
    throw new Error(`Upload media failed: ${response.status}`);
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
}

export async function getSessionReport(sessionId: string): Promise<SessionReport> {
  const response = await fetch(`${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}/report`);
  if (!response.ok) {
    throw new Error(`Get report failed: ${response.status}`);
  }
  return response.json();
}

/** 报告下载直链（浏览器据 Content-Disposition 触发下载，含中文文件名已 RFC 5987 兜底）。 */
export function reportDownloadUrl(sessionId: string, format: ReportFormat): string {
  return `${API_BASE_URL}/sessions/${encodeURIComponent(sessionId)}/report/download?format=${format}`;
}
