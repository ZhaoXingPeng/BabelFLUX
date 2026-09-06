import type { SourceSyncState } from "./events";

export type ProductMode = "quick" | "floating";
export type RuntimeState = "setup" | "connecting" | "running" | "paused" | "report" | "error";
export type SourcePermissionState = "idle" | "requesting" | "granted" | "denied";
export type DesktopLaunchState = "idle" | "launching" | "launched" | "fallback" | "error";

export interface ProductModeOption {
  key: ProductMode;
  label: string;
  description: string;
}

export interface SourceOption {
  key: string;
  label: string;
  channel: string;
  availability: "web" | "desktop";
  disabled?: boolean;
  fixture?: boolean;
}

export interface GlossaryTerm {
  sourceTerm: string;
  targetTerm: string;
}

export interface SourceInputState {
  fileName: string;
  url: string;
  permissionState: SourcePermissionState;
  permissionMessage: string;
}

export interface TranscriptPair {
  segmentId?: string;
  time: string;
  source: string;
  translation: string;
  state: string;
  isActive?: boolean;
  originalTranslation?: string;
  revisionReason?: string;
}

export interface WorkspaceTile {
  label: string;
  value: string;
}

export interface ReportMetric {
  label: string;
  value: string;
}

export interface QuickFormState {
  name: string;
  domain: string;
  sourceLanguage: string;
  targetLanguage: string;
  modelProfile: string;
  source: string;
  ttsEnabled: boolean;
  glossary: GlossaryTerm[];
}

export interface FloatingFormState {
  domain: string;
  sourceLanguage: string;
  targetLanguage: string;
  modelProfile: string;
  source: string;
  ttsEnabled: boolean;
  style: string;
  size: string;
  opacity: string;
  captionPinned: boolean;
  captionOffsetY: number;
}

export interface RuntimeSummary {
  status: string;
  wsConnected: boolean;
  sourceSyncState: SourceSyncState;
  errorMessage: string | null;
}
