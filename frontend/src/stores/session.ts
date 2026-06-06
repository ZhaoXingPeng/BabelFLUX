import { defineStore } from "pinia";
import {
  createSession,
  getSessionReport,
  issueSessionHandoff,
  reportDownloadUrl,
  uploadSessionMedia,
  type CreateSessionPayload,
  type DesktopDisplayMode,
  type ReportFormat,
  type SessionReport
} from "../api/client";
import { createSessionSocket } from "../api/ws";
import {
  acquireStream,
  startAudioCapture,
  startMediaElementAudioCapture,
  type AudioCaptureSession,
  type CaptureSourceKind
} from "../composables/useAudioCapture";
import { findActiveSegment, testVideoFixture, type TestVideoRevision } from "../fixtures/testVideo";
import type {
  RevisionEvent,
  SegmentStatus,
  ServerEvent,
  SessionStatus,
  SourceSyncState,
  SubtitleSegment
} from "../types/events";
import type {
  DesktopLaunchState,
  FloatingFormState,
  ProductMode,
  ProductModeOption,
  QuickFormState,
  ReportMetric,
  RuntimeState,
  SourceInputState,
  SourceOption,
  TranscriptPair,
  WorkspaceTile
} from "../types/workflow";

let socket: WebSocket | null = null;
let desktopLaunchTimer: number | null = null;
let desktopLaunchDismissTimer: number | null = null;
let removeDesktopLaunchListeners: (() => void) | null = null;
// File 对象不放进响应式 state（不可序列化），用模块级暂存供上传模式在 start 前上传字节。
const pendingFiles: { quick: File | null; floating: File | null } = { quick: null, floating: null };
const localPreviewUrls: Record<ProductMode, string | null> = { quick: null, floating: null };
// 实时采集句柄与“本次会话应采集的音源种类”，同样不入响应式 state。
let audioCapture: AudioCaptureSession | null = null;
let pendingCaptureKind: CaptureSourceKind | null = null;
let pendingMediaElementCapture = false;
let pendingMediaReadyState: SourceSyncState | null = null;
let mediaElement: HTMLMediaElement | null = null;
let captureStarted = false;
let playbackStartPending = false;
let mediaPlaybackActive = false;
let estimatedOutputLatencyMs = 1500;
const recentOutputLatencies: number[] = [];

function revokeLocalPreview(mode: ProductMode) {
  const url = localPreviewUrls[mode];
  if (url && typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(url);
  localPreviewUrls[mode] = null;
}

function setLocalPreview(mode: ProductMode, file: File | null): string | null {
  revokeLocalPreview(mode);
  if (!file || typeof URL.createObjectURL !== "function") return null;
  localPreviewUrls[mode] = URL.createObjectURL(file);
  return localPreviewUrls[mode];
}

const captureKindBySource: Record<string, CaptureSourceKind> = {
  microphone: "microphone",
  "browser-tab": "browser_audio",
  "screen-window": "screen_window",
  "system-audio": "system_audio"
};

const DESKTOP_LAUNCH_TIMEOUT_MS = 2500;
const DESKTOP_LAUNCH_SUCCESS_VISIBLE_MS = 3500;
const DEFAULT_SESSION_NAME_PATTERN = /^同传_\d{8}_\d{4}$/;
// 本地测试视频字幕的「同传产出延迟」：音频说到某句后约 1.5s，右侧才产出该句字幕，贴近真实同传节奏。
const SUBTITLE_LATENCY_MS = 1500;
const MIN_OUTPUT_LATENCY_MS = 500;
const MAX_OUTPUT_LATENCY_MS = 6000;
const OUTPUT_LATENCY_SAMPLE_SIZE = 8;

const defaultSourceSyncState: SourceSyncState = {
  status: "listening",
  lagMs: 0,
  message: "等待开始会话"
};

const productModeOptions: ProductModeOption[] = [
  { key: "quick", label: "快速同传", description: "Web 工作台" },
  { key: "floating", label: "客户端悬浮", description: "桌面端全局能力" }
];

const modelProfileOptions = ["智能默认", "快速低延迟", "高准确", "成本优先", "指定供应商"];
const domainOptions = ["通用", "技术", "商务", "教育", "医疗", "法律", "自定义术语表"];
const languageOptions = ["自动检测", "英语", "中文", "日语", "韩语", "法语", "德语"];
const targetLanguageOptions = ["中文", "英语", "日语", "韩语"];
const displayModeOptions = ["分区对照", "逐句对照", "悬浮字幕"];
const displayModeCopy: Record<string, string> = {
  分区对照: "原文和译文分栏审阅",
  逐句对照: "一句原文对应一句译文",
  悬浮字幕: "Web 内嵌字幕层，桌面端可全局悬浮"
};

const quickSourceOptions: SourceOption[] = [
  {
    key: testVideoFixture.key,
    label: testVideoFixture.label,
    channel: "mp4 + m4a + 中英字幕",
    availability: "web"
  },
  { key: "video-file", label: "视频文件", channel: "mp4 / mov / webm", availability: "web" },
  { key: "audio-file", label: "音频文件", channel: "mp3 / wav / m4a", availability: "web" },
  { key: "url", label: "URL", channel: "网页视频或直播链接", availability: "web" },
  { key: "microphone", label: "麦克风", channel: "外放或线下讲座兜底", availability: "web" },
  { key: "browser-tab", label: "浏览器标签页音频", channel: "网课、网页视频", availability: "web" },
  { key: "screen-window", label: "屏幕或窗口", channel: "浏览器权限能力", availability: "web" },
  { key: "system-audio", label: "系统音频", channel: "桌面端能力", availability: "desktop", disabled: true }
];

const floatingSourceOptions: SourceOption[] = [
  { key: "microphone", label: "麦克风", channel: "外放或会议室", availability: "web" },
  { key: "browser-tab", label: "浏览器标签页音频", channel: "网页视频和网课", availability: "web" },
  { key: "screen-window", label: "屏幕或窗口音频", channel: "浏览器权限能力", availability: "web" },
  { key: "system-audio", label: "系统音频", channel: "桌面端能力", availability: "desktop", disabled: true }
];

const defaultSourceInputState: SourceInputState = {
  fileName: "",
  url: "",
  permissionState: "idle",
  permissionMessage: "等待准备声源"
};

const fileSourceKeys = new Set(["video-file", "audio-file"]);
const playbackControlledSourceKeys = new Set(["video-file", "audio-file"]);
const permissionSourceKeys = new Set(["microphone", "browser-tab", "screen-window"]);

const inputModeBySourceKey: Record<string, CreateSessionPayload["inputMode"]> = {
  [testVideoFixture.key]: "demo",
  "video-file": "media_element_audio",
  "audio-file": "media_element_audio",
  url: "url",
  microphone: "microphone",
  "browser-tab": "browser_audio",
  "screen-window": "screen_window",
  "system-audio": "system_audio"
};

const languageCodeByLabel: Record<string, string> = {
  自动检测: "auto",
  英语: "en",
  中文: "zh",
  日语: "ja",
  韩语: "ko",
  法语: "fr",
  德语: "de"
};

const samplePairs: TranscriptPair[] = [
  {
    time: "00:00:04",
    source: "Today we are going to talk about real-time AI translation.",
    translation: "今天我们要讨论实时 AI 翻译。",
    state: "final"
  },
  {
    time: "00:00:11",
    source: "The system should balance latency, accuracy and stability.",
    translation: "系统需要在延迟、准确率和稳定性之间取得平衡。",
    state: "translated"
  },
  {
    time: "00:00:18",
    source: "When more context arrives, earlier subtitles can be revised.",
    translation: "当后续上下文到达时，前面的字幕可以被自动修正。",
    state: "revised"
  }
];

interface SessionState {
  sessionId: string | null;
  status: SessionStatus;
  wsConnected: boolean;
  sourceSyncState: SourceSyncState;
  mediaUrl: string | null;
  audioUrl: string | null;
  playbackMs: number;
  activeSegmentId: string | null;
  fixtureAppliedRevisionIds: string[];
  sourceSegments: SubtitleSegment[];
  translationSegments: SubtitleSegment[];
  revisions: RevisionEvent[];
  errorMessage: string | null;
  productMode: ProductMode;
  activeMode: ProductMode | null;
  endingMode: ProductMode | null;
  showEndDialog: boolean;
  selectedDisplayMode: string;
  desktopLaunchState: DesktopLaunchState;
  desktopLaunchMessage: string;
  desktopDownloadPromptOpen: boolean;
  desktopHandoffUrl: string | null;
  modeStates: Record<ProductMode, RuntimeState>;
  quickForm: QuickFormState;
  floatingForm: FloatingFormState;
  quickInput: SourceInputState;
  floatingInput: SourceInputState;
  startRequestId: number;
  reportId: string | null;
  report: SessionReport | null;
  reportLoading: boolean;
  reportError: string | null;
}

function upsertSegment(items: SubtitleSegment[], segment: SubtitleSegment): SubtitleSegment[] {
  const index = items.findIndex((item) => item.segmentId === segment.segmentId);
  if (index === -1) return [...items, segment];
  return items.map((item, itemIndex) => (itemIndex === index ? segment : item));
}

function createFixtureSourceSegments(): SubtitleSegment[] {
  return testVideoFixture.segments.map((segment) => ({
    segmentId: segment.segmentId,
    text: segment.en,
    language: "en",
    startMs: segment.startMs,
    endMs: segment.endMs,
    status: "final"
  }));
}

function createFixtureTranslationSegments(): SubtitleSegment[] {
  return testVideoFixture.segments.map((segment) => ({
    segmentId: segment.segmentId,
    text: segment.zh,
    language: "zh",
    startMs: segment.startMs,
    endMs: segment.endMs,
    status: "final"
  }));
}

function createFixtureRevisionEvent(revision: TestVideoRevision): RevisionEvent {
  return {
    revisionId: revision.revisionId,
    targetSegmentIds: [revision.segmentId],
    beforeText: revision.beforeText,
    afterText: revision.afterText,
    reason: revision.reason,
    confidence: revision.confidence
  };
}

function formatPlaybackTime(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function streamText(text: string, progress: number): string {
  const value = text.trim();
  if (!value || progress >= 0.98) return value;
  const units = /\s/.test(value) ? value.split(/(\s+)/).filter(Boolean) : Array.from(value);
  const visible = Math.max(1, Math.ceil(units.length * (0.18 + clamp01(progress) * 0.82)));
  return units.slice(0, visible).join("");
}

function defaultSessionName(): string {
  const date = new Date();
  const pad = (value: number) => String(value).padStart(2, "0");
  return `同传_${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}_${pad(date.getHours())}${pad(date.getMinutes())}`;
}

function shouldRefreshDefaultSessionName(name: string): boolean {
  return name.trim().length === 0 || DEFAULT_SESSION_NAME_PATTERN.test(name);
}

function formatRuntimeState(state: RuntimeState): string {
  const labels: Record<RuntimeState, string> = {
    setup: "待开始",
    connecting: "连接中",
    running: "运行中",
    paused: "已暂停",
    report: "已生成报告",
    error: "启动失败"
  };
  return labels[state];
}

function toLanguageCode(label: string): string {
  return languageCodeByLabel[label] ?? label;
}

function toDesktopDisplayMode(style: string): DesktopDisplayMode {
  return style === "仅译文" ? "translation-only" : "bilingual";
}

function getUrlError(sourceKey: string, url: string): string | null {
  if (sourceKey !== "url") return null;
  const value = url.trim();
  if (!value) return "请输入 URL";

  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:"
      ? null
      : "仅支持 http 或 https URL";
  } catch {
    return "URL 格式不正确";
  }
}

function isSourceInputReady(sourceKey: string, input: SourceInputState): boolean {
  if (fileSourceKeys.has(sourceKey)) return input.fileName.trim().length > 0;
  if (sourceKey === "url") return getUrlError(sourceKey, input.url) === null;
  if (permissionSourceKeys.has(sourceKey)) return input.permissionState === "granted";
  return true;
}

function canStartMode(source: SourceOption, sourceKey: string, input: SourceInputState, state: RuntimeState): boolean {
  return ["setup", "report", "error"].includes(state) && !source.disabled && isSourceInputReady(sourceKey, input);
}

function stopMediaStream(stream: MediaStream) {
  stream.getTracks().forEach((track) => track.stop());
}

async function requestBrowserPermission(sourceKey: string): Promise<string> {
  const mediaDevices = navigator.mediaDevices;
  if (!mediaDevices) throw new Error("当前浏览器不支持媒体权限");

  if (sourceKey === "microphone") {
    const stream = await mediaDevices.getUserMedia({ audio: true });
    stopMediaStream(stream);
    return "麦克风已授权";
  }

  if (sourceKey === "browser-tab" || sourceKey === "screen-window") {
    const stream = await acquireStream(captureKindBySource[sourceKey]);
    stopMediaStream(stream);
    return sourceKey === "browser-tab"
      ? "标签页音频已授权"
      : "屏幕或窗口音频已授权";
  }

  if (sourceKey === "system-audio") {
    throw new Error("Windows 系统音频由桌面客户端原生采集，无需浏览器授权。");
  }

  throw new Error("该声源不需要浏览器授权");
}

function triggerDownload(url: string, filename?: string) {
  const anchor = document.createElement("a");
  anchor.href = url;
  if (filename) anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function srtTimestamp(ms: number): string {
  const clamped = Math.max(0, ms);
  const h = Math.floor(clamped / 3_600_000);
  const m = Math.floor((clamped % 3_600_000) / 60_000);
  const s = Math.floor((clamped % 60_000) / 1000);
  const millis = clamped % 1000;
  const pad = (value: number, len = 2) => String(value).padStart(len, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)},${pad(millis, 3)}`;
}

function median(values: number[]): number {
  if (values.length === 0) return SUBTITLE_LATENCY_MS;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}

function recordOutputLatency(segment: SubtitleSegment, playbackMs: number) {
  if (playbackMs <= 0 || segment.startMs < 0) return;
  const latency = playbackMs - segment.startMs;
  if (latency < MIN_OUTPUT_LATENCY_MS || latency > MAX_OUTPUT_LATENCY_MS) return;
  recentOutputLatencies.push(latency);
  while (recentOutputLatencies.length > OUTPUT_LATENCY_SAMPLE_SIZE) recentOutputLatencies.shift();
  estimatedOutputLatencyMs = median(recentOutputLatencies);
}

function combinedTimeline(
  sourceSegments: SubtitleSegment[],
  translationSegments: SubtitleSegment[]
): Array<{ segmentId: string; startMs: number; endMs: number }> {
  const ids: string[] = [];
  [...sourceSegments, ...translationSegments].forEach((segment) => {
    if (!ids.includes(segment.segmentId)) ids.push(segment.segmentId);
  });

  return ids
    .map((segmentId) => {
      const source = sourceSegments.find((segment) => segment.segmentId === segmentId);
      const translation = translationSegments.find((segment) => segment.segmentId === segmentId);
      const startMs = source?.startMs ?? translation?.startMs ?? 0;
      const endMs = Math.max(source?.endMs ?? 0, translation?.endMs ?? 0);
      return { segmentId, startMs, endMs };
    })
    .sort((a, b) => a.startMs - b.startMs);
}

function activeSegmentForPlayback(
  sourceSegments: SubtitleSegment[],
  translationSegments: SubtitleSegment[],
  playbackMs: number
): string | null {
  const timeline = combinedTimeline(sourceSegments, translationSegments);
  if (timeline.length === 0) return null;

  const displayClockMs = Math.max(0, playbackMs - estimatedOutputLatencyMs);
  const enriched = timeline.map((segment, index) => {
    const next = timeline[index + 1];
    return {
      ...segment,
      endMs: Math.max(segment.endMs, next?.startMs ?? 0, segment.startMs + 2000)
    };
  });
  const exact = enriched.find(
    (segment) => displayClockMs >= segment.startMs && displayClockMs < segment.endMs
  );
  if (exact) return exact.segmentId;
  return [...enriched].reverse().find((segment) => segment.startMs <= displayClockMs)?.segmentId
    ?? enriched[enriched.length - 1]?.segmentId
    ?? null;
}

/** 客户端报告渲染（本地演示下载用，与后端 report.py 的 txt/srt/md/json 对齐）。 */
function renderReportClient(
  report: SessionReport,
  format: ReportFormat
): { body: string; mime: string; ext: string } {
  if (format === "json") {
    return { body: JSON.stringify(report, null, 2), mime: "application/json", ext: "json" };
  }
  if (format === "srt") {
    const body = report.segments
      .map((seg, index) => {
        const end = seg.endMs > seg.startMs ? seg.endMs : seg.startMs + 2000;
        return `${index + 1}\n${srtTimestamp(seg.startMs)} --> ${srtTimestamp(end)}\n${seg.sourceText}\n${seg.finalTranslation}\n`;
      })
      .join("\n");
    return { body, mime: "application/x-subrip", ext: "srt" };
  }
  if (format === "md") {
    const lines = [
      `# ${report.sessionName}`,
      "",
      `- **领域**：${report.domain}`,
      `- **语言**：${report.sourceLanguage} → ${report.targetLanguage}`,
      `- **时长**：${report.durationText}`,
      `- **句数**：${report.metrics.segments}　实时修正：${report.metrics.realtimeRevisions}　会后修正：${report.metrics.finalRevisions}`,
      "",
      "## 摘要",
      report.summary,
      "",
      "## 双语终稿",
      "",
      "| 时间 | 原文 | 终稿译文 |",
      "| --- | --- | --- |",
      ...report.segments.map(
        (seg) =>
          `| ${seg.timecode} | ${seg.sourceText.replace(/\|/g, "\\|")} | ${seg.finalTranslation.replace(/\|/g, "\\|")} |`
      )
    ];
    return { body: lines.join("\n"), mime: "text/markdown", ext: "md" };
  }
  const lines = [
    `# ${report.sessionName}`,
    `领域：${report.domain}  |  语言：${report.sourceLanguage} -> ${report.targetLanguage}  |  时长：${report.durationText}`,
    `生成时间：${report.generatedAt}`,
    "",
    "【摘要】",
    report.summary,
    "",
    "【双语终稿】",
    ...report.segments.flatMap((seg) => [`[${seg.timecode}] ${seg.sourceText}`, `          ${seg.finalTranslation}`])
  ];
  if (report.finalRevisions.length) {
    lines.push("", "【校正记录】");
    report.finalRevisions.forEach((rev) => lines.push(`- ${rev.beforeText}  =>  ${rev.afterText}  （${rev.reason}）`));
  }
  return { body: lines.join("\n"), mime: "text/plain", ext: "txt" };
}

export const useSessionStore = defineStore("session", {
  state: (): SessionState => ({
    sessionId: null,
    status: "idle",
    wsConnected: false,
    sourceSyncState: {
      status: "listening",
      lagMs: 0,
      message: "本地测试素材已就绪"
    },
    mediaUrl: testVideoFixture.videoUrl,
    audioUrl: testVideoFixture.audioUrl,
    playbackMs: 0,
    activeSegmentId: testVideoFixture.segments[0]?.segmentId ?? null,
    fixtureAppliedRevisionIds: [],
    sourceSegments: createFixtureSourceSegments(),
    translationSegments: createFixtureTranslationSegments(),
    revisions: [],
    errorMessage: null,
    productMode: "quick",
    activeMode: null,
    endingMode: null,
    showEndDialog: false,
    selectedDisplayMode: "逐句对照",
    desktopLaunchState: "idle",
    desktopLaunchMessage: "等待投送到桌面悬浮窗",
    desktopDownloadPromptOpen: false,
    desktopHandoffUrl: null,
    modeStates: {
      quick: "setup",
      floating: "setup"
    },
    quickForm: {
      name: defaultSessionName(),
      domain: "通用",
      sourceLanguage: "英语",
      targetLanguage: "中文",
      modelProfile: "智能默认",
      source: testVideoFixture.key
    },
    floatingForm: {
      domain: "通用",
      sourceLanguage: "自动检测",
      targetLanguage: "中文",
      modelProfile: "快速低延迟",
      source: "browser-tab",
      style: "双语字幕",
      size: "标准",
      opacity: "90%",
      captionPinned: false,
      captionOffsetY: 0
    },
    quickInput: { ...defaultSourceInputState },
    floatingInput: { ...defaultSourceInputState },
    startRequestId: 0,
    reportId: null,
    report: null,
    reportLoading: false,
    reportError: null
  }),

  getters: {
    activeSourceSegment: (state): SubtitleSegment | undefined =>
      state.activeSegmentId
        ? state.sourceSegments.find((segment) => segment.segmentId === state.activeSegmentId)
        : [...state.sourceSegments].reverse().find((segment) => segment.status !== "revised"),
    activeTranslationSegment: (state): SubtitleSegment | undefined =>
      state.activeSegmentId
        ? state.translationSegments.find((segment) => segment.segmentId === state.activeSegmentId)
        : [...state.translationSegments].reverse().find((segment) => segment.status !== "revised"),
    productModes: (): ProductModeOption[] => productModeOptions,
    modelProfiles: (): string[] => modelProfileOptions,
    domains: (): string[] => domainOptions,
    languages: (): string[] => languageOptions,
    targetLanguages: (): string[] => targetLanguageOptions,
    displayModes: (): string[] => displayModeOptions,
    quickSources: (): SourceOption[] => quickSourceOptions,
    floatingSources: (): SourceOption[] => floatingSourceOptions,
    transcriptPairs: (state): TranscriptPair[] => {
      if (state.sourceSegments.length === 0 && state.translationSegments.length === 0) {
        // 会话已开始但字幕尚未「延迟产出」时显示空白等待，而非示例占位字幕；
        // 仅在没有任何会话（首屏预览态）时才回退到 samplePairs。
        return state.sessionId ? [] : samplePairs;
      }

      const ids: string[] = [];
      [...state.sourceSegments, ...state.translationSegments].forEach((segment) => {
        if (!ids.includes(segment.segmentId)) ids.push(segment.segmentId);
      });

      return ids.map((segmentId) => {
        const source = state.sourceSegments.find((segment) => segment.segmentId === segmentId);
        const translation = state.translationSegments.find((segment) => segment.segmentId === segmentId);
        const sourceStatus = source?.status;
        const translationStatus = translation?.status;
        const stateLabel =
          translationStatus === "revised"
            ? "revised"
            : sourceStatus === "partial" || translationStatus === "partial"
              ? "partial"
              : (translationStatus ?? sourceStatus ?? "partial");
        const startMs = source?.startMs ?? translation?.startMs ?? 0;
        return {
          segmentId,
          time: formatPlaybackTime(startMs),
          source: source?.text ?? "",
          translation: translation?.text ?? "",
          state: stateLabel,
          isActive: segmentId === state.activeSegmentId,
          originalTranslation: translation?.originalText,
          revisionReason: translation?.revisionReason
        };
      }).filter((pair) => pair.source || pair.translation);
    },
    currentPair(): TranscriptPair {
      return (
        this.transcriptPairs.find((pair) => pair.isActive) ??
        this.transcriptPairs[this.transcriptPairs.length - 1] ??
        samplePairs[0]
      );
    },
    quickSource(state): SourceOption {
      return quickSourceOptions.find((source) => source.key === state.quickForm.source) ?? quickSourceOptions[0];
    },
    floatingSource(state): SourceOption {
      return (
        floatingSourceOptions.find((source) => source.key === state.floatingForm.source) ??
        floatingSourceOptions[0]
      );
    },
    quickStatusLabel(state): string {
      return formatRuntimeState(state.modeStates.quick);
    },
    floatingStatusLabel(state): string {
      return formatRuntimeState(state.modeStates.floating);
    },
    selectedDisplayDescription(state): string {
      return displayModeCopy[state.selectedDisplayMode];
    },
    mediaKind(state): "video" | "audio" {
      return state.quickForm.source === testVideoFixture.key || state.quickForm.source === "video-file" || state.quickForm.source === "url"
        ? "video"
        : "audio";
    },
    isLive(state): boolean {
      return ["running", "paused", "report"].includes(state.modeStates.quick);
    },
    quickUrlError(state): string | null {
      return getUrlError(state.quickForm.source, state.quickInput.url);
    },
    floatingUrlError(state): string | null {
      return getUrlError(state.floatingForm.source, state.floatingInput.url);
    },
    quickCanStart(): boolean {
      return canStartMode(this.quickSource, this.quickForm.source, this.quickInput, this.modeStates.quick);
    },
    floatingCanStart(): boolean {
      return canStartMode(
        this.floatingSource,
        this.floatingForm.source,
        this.floatingInput,
        this.modeStates.floating
      );
    },
    workspaceTiles(): WorkspaceTile[] {
      return [
        { label: "源文实时转写", value: this.currentPair.source },
        { label: "译文实时输出", value: this.currentPair.translation },
        {
          label: "修正记录",
          value: this.revisions[0]
            ? `${this.revisions[0].beforeText} -> ${this.revisions[0].afterText}`
            : "等待修正事件"
        },
        { label: "术语与摘要", value: "AI translation · 实时 AI 翻译 · 术语命中" }
      ];
    },
    reportMetrics(): ReportMetric[] {
      const report = this.report;
      if (report) {
        const segmentCount = report.metrics.segments || report.segments.length || this.transcriptPairs.length;
        const durationText =
          report.durationText ||
          report.metrics.durationText ||
          formatPlaybackTime(report.durationMs || this.playbackMs);
        return [
          { label: "时长", value: durationText },
          { label: "句数", value: `${segmentCount} 句` },
          {
            label: "修正",
            value: `实时 ${report.metrics.realtimeRevisions} · 会后 ${report.metrics.finalRevisions}`
          },
          { label: "导出", value: "TXT / SRT / MD / JSON" }
        ];
      }
      return [
        { label: "时长", value: formatPlaybackTime(this.playbackMs) },
        { label: "句数", value: `${this.transcriptPairs.length} 句` },
        { label: "修正", value: `${this.revisions.length} 条` },
        { label: "导出", value: "TXT / SRT / MD / JSON" }
      ];
    }
  },

  actions: {
    selectMode(mode: ProductMode) {
      this.productMode = mode;
    },

    selectQuickSource(source: SourceOption) {
      if (source.disabled || this.quickForm.source === source.key) return;
      pendingFiles.quick = null;
      revokeLocalPreview("quick");
      this.quickForm.source = source.key;
      this.quickInput = { ...defaultSourceInputState };
      if (source.key === testVideoFixture.key) {
        this.loadTestVideoFixturePreview();
      } else if (!this.activeMode) {
        this.clearLocalMediaPreview();
      }
    },

    selectFloatingSource(source: SourceOption) {
      if (source.disabled || this.floatingForm.source === source.key) return;
      this.floatingForm.source = source.key;
      this.floatingInput = { ...defaultSourceInputState };
    },

    setQuickSourceFile(file: File | null) {
      this.quickInput.fileName = file?.name ?? "";
      pendingFiles.quick = file;
      const previewUrl = setLocalPreview("quick", file);
      if (this.quickForm.source === "video-file") {
        this.mediaUrl = previewUrl;
        this.audioUrl = null;
      } else if (this.quickForm.source === "audio-file") {
        this.mediaUrl = null;
        this.audioUrl = previewUrl;
      }
    },

    updateQuickSourceUrl(url: string) {
      this.quickInput.url = url;
    },

    setFloatingSourceFile(file: File | null) {
      this.floatingInput.fileName = file?.name ?? "";
      pendingFiles.floating = file;
    },

    updateFloatingSourceUrl(url: string) {
      this.floatingInput.url = url;
    },

    async requestQuickSourceAccess() {
      await this.requestSourceAccess("quick");
    },

    async requestFloatingSourceAccess() {
      await this.requestSourceAccess("floating");
    },

    async requestSourceAccess(mode: ProductMode) {
      const form = mode === "quick" ? this.quickForm : this.floatingForm;
      const input = mode === "quick" ? this.quickInput : this.floatingInput;

      input.permissionState = "requesting";
      input.permissionMessage = "正在请求权限";

      try {
        input.permissionMessage = await requestBrowserPermission(form.source);
        input.permissionState = "granted";
      } catch (error) {
        input.permissionState = "denied";
        input.permissionMessage = error instanceof Error ? error.message : "权限申请失败";
      }
    },

    clearDesktopLaunchWatchers() {
      if (desktopLaunchTimer !== null) {
        window.clearTimeout(desktopLaunchTimer);
        desktopLaunchTimer = null;
      }
      if (desktopLaunchDismissTimer !== null) {
        window.clearTimeout(desktopLaunchDismissTimer);
        desktopLaunchDismissTimer = null;
      }
      removeDesktopLaunchListeners?.();
      removeDesktopLaunchListeners = null;
    },

    markDesktopLaunchLaunched() {
      if (this.desktopLaunchState !== "launching") return;
      this.clearDesktopLaunchWatchers();
      this.desktopLaunchState = "launched";
      this.desktopLaunchMessage = "桌面悬浮窗已唤起";
      this.desktopDownloadPromptOpen = true;
      desktopLaunchDismissTimer = window.setTimeout(() => {
        if (this.desktopLaunchState !== "launched") return;
        this.desktopDownloadPromptOpen = false;
        this.desktopLaunchState = "idle";
        this.desktopLaunchMessage = "等待投送到桌面悬浮窗";
        desktopLaunchDismissTimer = null;
      }, DESKTOP_LAUNCH_SUCCESS_VISIBLE_MS);
      try {
        window.localStorage.setItem("lingosync.clientSeen", "1");
      } catch {
        // localStorage can be unavailable in privacy modes; launch success should not depend on it.
      }
    },

    armDesktopLaunchFallback() {
      this.clearDesktopLaunchWatchers();

      const handleVisibility = () => {
        if (document.visibilityState === "hidden") this.markDesktopLaunchLaunched();
      };
      const handleBlur = () => this.markDesktopLaunchLaunched();
      window.addEventListener("blur", handleBlur, { once: true });
      document.addEventListener("visibilitychange", handleVisibility);
      removeDesktopLaunchListeners = () => {
        window.removeEventListener("blur", handleBlur);
        document.removeEventListener("visibilitychange", handleVisibility);
      };

      desktopLaunchTimer = window.setTimeout(() => {
        this.clearDesktopLaunchWatchers();
        if (this.desktopLaunchState !== "launching") return;
        this.desktopLaunchState = "fallback";
        this.desktopLaunchMessage = "未检测到桌面客户端";
        this.desktopDownloadPromptOpen = true;
      }, DESKTOP_LAUNCH_TIMEOUT_MS);
    },

    launchDesktopUrl(deepLinkUrl: string) {
      this.desktopHandoffUrl = deepLinkUrl;
      this.desktopLaunchState = "launching";
      this.desktopLaunchMessage = "正在唤起桌面悬浮窗";
      this.desktopDownloadPromptOpen = false;
      this.armDesktopLaunchFallback();
      window.location.assign(deepLinkUrl);
    },

    async openDesktopFloating() {
      const targetLanguage = toLanguageCode(this.floatingForm.targetLanguage);
      const displayMode = toDesktopDisplayMode(this.floatingForm.style);

      this.desktopLaunchState = "launching";
      this.desktopLaunchMessage = "正在准备桌面悬浮窗";
      this.desktopDownloadPromptOpen = false;

      if (!this.sessionId) {
        const params = new URLSearchParams({
          source: "system-audio",
          sourceLanguage: "auto",
          targetLanguage,
          displayMode
        });
        this.launchDesktopUrl(`lingosync://floating/start?${params.toString()}`);
        return;
      }

      try {
        const handoff = await issueSessionHandoff(this.sessionId, {
          source: this.quickForm.source,
          sourceLanguage: toLanguageCode(this.quickForm.sourceLanguage),
          targetLanguage: toLanguageCode(this.quickForm.targetLanguage),
          displayMode
        });
        this.launchDesktopUrl(handoff.deepLinkUrl);
      } catch (error) {
        this.desktopLaunchState = "error";
        this.desktopLaunchMessage = error instanceof Error ? error.message : "无法创建桌面接管凭据";
        this.desktopDownloadPromptOpen = true;
      }
    },

    dismissDesktopDownloadPrompt() {
      this.clearDesktopLaunchWatchers();
      this.desktopDownloadPromptOpen = false;
      if (
        this.desktopLaunchState === "fallback" ||
        this.desktopLaunchState === "launched" ||
        this.desktopLaunchState === "error"
      ) {
        this.desktopLaunchState = "idle";
        this.desktopLaunchMessage = "等待投送到桌面悬浮窗";
      }
    },

    continueWithWebFloating() {
      this.desktopDownloadPromptOpen = false;
      this.selectedDisplayMode = "悬浮字幕";
      this.desktopLaunchState = "idle";
      this.desktopLaunchMessage = "已切回网页悬浮字幕";
    },

    reopenDesktop() {
      if (!this.desktopHandoffUrl) {
        this.openDesktopFloating();
        return;
      }
      this.launchDesktopUrl(this.desktopHandoffUrl);
    },

    async startMode(mode: ProductMode) {
      const blockedSource = mode === "quick" ? this.quickSource.disabled : this.floatingSource.disabled;
      const inputReady =
        mode === "quick"
          ? isSourceInputReady(this.quickForm.source, this.quickInput)
          : isSourceInputReady(this.floatingForm.source, this.floatingInput);
      if (blockedSource || !inputReady || !["setup", "report", "error"].includes(this.modeStates[mode])) return;

      if (mode === "quick" && shouldRefreshDefaultSessionName(this.quickForm.name)) {
        this.quickForm.name = defaultSessionName();
      }

      const requestId = this.startRequestId + 1;
      this.startRequestId = requestId;

      const previousMode = this.activeMode;
      if (previousMode && previousMode !== mode) {
        this.modeStates[previousMode] = "setup";
        this.stopSession("idle");
      }

      this.activeMode = mode;
      this.productMode = mode;
      this.modeStates.quick = mode === "quick" ? "connecting" : "setup";
      this.modeStates.floating = mode === "floating" ? "connecting" : "setup";

      const started = await this.startConfiguredSession(mode, requestId);
      if (!this.isCurrentStart(mode, requestId)) return;

      if (started) {
        this.modeStates[mode] = "running";
      } else {
        this.modeStates[mode] = "error";
        this.activeMode = null;
      }
    },

    pauseMode(mode: ProductMode) {
      if (this.activeMode !== mode || this.modeStates[mode] !== "running") return;
      this.modeStates[mode] = "paused";
      this.pauseSession();
    },

    resumeMode(mode: ProductMode) {
      if (this.activeMode !== mode || this.modeStates[mode] !== "paused") return;
      this.modeStates[mode] = "running";
      this.resumeSession();
    },

    handleMediaPlaybackPaused() {
      mediaPlaybackActive = false;
      if (this.activeMode !== "quick" || playbackStartPending) return;
      if (this.modeStates.quick === "running") this.pauseMode("quick");
    },

    handleMediaPlaybackPlayed() {
      mediaPlaybackActive = true;
      if (this.activeMode !== "quick") return;

      if (this.isMediaElementCaptureSource() && !captureStarted) {
        mediaPlaybackActive = false;
        mediaElement?.pause();
        return;
      }

      if (playbackStartPending) {
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "start_session" }));
          playbackStartPending = false;
          this.status = "running";
          this.modeStates.quick = "running";
        }
        return;
      }

      if (this.modeStates.quick === "paused") this.resumeMode("quick");
    },

    askEnd(mode: ProductMode) {
      this.endingMode = mode;
      this.showEndDialog = true;
    },

    cancelEnd() {
      this.showEndDialog = false;
      this.endingMode = null;
    },

    confirmEnd() {
      if (!this.endingMode) return;
      const mode = this.endingMode;
      this.showEndDialog = false;
      this.endingMode = null;

      // 已经收到报告（音频自然结束路径）→ 仅关闭弹窗
      if (this.modeStates[mode] === "report" && this.report) return;

      this.modeStates[mode] = "report";

      const isFixture =
        this.sessionId === testVideoFixture.key || this.sessionId === "local-test-video-fixture";

      if (socket && socket.readyState === WebSocket.OPEN && !isFixture) {
        // 优雅结束：发 stop_session 但不立即关闭 socket，等后端完成会后完整纠偏后下发
        // session_report（由 applyServerEvent 处理）。保持 isCurrentStart 有效以接收该事件。
        this.reportId = null;
        this.report = null;
        this.reportError = null;
        this.reportLoading = true;
        socket.send(JSON.stringify({ type: "stop_session" }));
        void this.stopCapture();
        const endingRequestId = this.startRequestId;
        // 兜底：后端长时间无报告（异常/断连）时降级，避免一直卡在“生成中”。
        window.setTimeout(() => {
          if (this.startRequestId === endingRequestId && this.reportLoading && !this.reportId) {
            this.reportLoading = false;
            this.reportError = "报告生成超时，请稍后在报告区重试下载";
            if (this.activeMode === mode) this.activeMode = null;
            this.stopSession("stopped");
          }
        }, 30000);
      } else {
        // 无后端会话（本地 fixture 演示）→ 客户端合成报告，保证“结束→可看”闭环。
        this.startRequestId += 1;
        if (this.activeMode === mode) this.activeMode = null;
        this.buildLocalReport();
        this.stopSession("stopped");
      }
    },

    resetMode(mode: ProductMode) {
      if (this.activeMode === mode) {
        this.activeMode = null;
        this.stopSession("idle");
      }
      // 无论该模式此前是否在跑，都清掉上一段的报告/字幕/进度，确保是"干净的下一次任务"。
      this.startRequestId += 1;
      this.resetSessionData();
      this.modeStates[mode] = "setup";
      if (mode === "quick" && shouldRefreshDefaultSessionName(this.quickForm.name)) {
        this.quickForm.name = defaultSessionName();
      }
      if (mode === "quick" && this.quickForm.source === testVideoFixture.key && !this.activeMode) {
        this.loadTestVideoFixturePreview();
      }
    },

    /** 本地测试视频自然播放结束 → 自动收尾出报告，贴近"音频播放完自动结束"的真实路径。 */
    handleFixtureEnded() {
      if (!["running", "paused"].includes(this.modeStates.quick)) return;
      if (this.sessionId !== "local-test-video-fixture") {
        this.endingMode = "quick";
        this.confirmEnd();
        return;
      }
      this.revealFixtureSegmentsUpTo(testVideoFixture.durationMs);
      this.modeStates.quick = "report";
      this.startRequestId += 1;
      this.activeMode = null;
      this.buildLocalReport();
      this.stopSession("stopped");
    },

    buildSessionPayload(mode: ProductMode): CreateSessionPayload {
      const form = mode === "quick" ? this.quickForm : this.floatingForm;
      const input = mode === "quick" ? this.quickInput : this.floatingInput;
      const sourceKey = form.source;

      return {
        inputMode: inputModeBySourceKey[sourceKey] ?? "demo",
        sourceLanguage: toLanguageCode(form.sourceLanguage),
        targetLanguage: toLanguageCode(form.targetLanguage),
        productMode: mode,
        sessionName: mode === "quick" ? this.quickForm.name : "悬浮字幕",
        domain: form.domain,
        modelProfile: form.modelProfile,
        sourceKey,
        sourceFileName: input.fileName || undefined,
        sourceUrl: sourceKey === "url" ? input.url.trim() : undefined,
        sourcePermission: input.permissionState
      };
    },

    isCurrentStart(mode: ProductMode, requestId: number, sessionId?: string): boolean {
      return (
        this.activeMode === mode &&
        this.startRequestId === requestId &&
        (sessionId === undefined || this.sessionId === sessionId)
      );
    },

    async startConfiguredSession(mode: ProductMode, requestId: number): Promise<boolean> {
      this.stopSession("idle");
      this.resetSessionData();
      if (mode === "quick") this.applyQuickLocalFilePreview();
      this.status = "connecting";
      this.errorMessage = null;

      if (mode === "quick" && this.quickForm.source === testVideoFixture.key) {
        this.startTestVideoFixtureSession(requestId);
        return true;
      }

      try {
        const session = await createSession(this.buildSessionPayload(mode));

        if (!this.isCurrentStart(mode, requestId)) return false;

        this.sessionId = session.sessionId;

        const sourceKey = mode === "quick" ? this.quickForm.source : this.floatingForm.source;
        const inputMode = inputModeBySourceKey[sourceKey] ?? "demo";
        if (inputMode === "upload_video" || inputMode === "upload_audio") {
          // 备用后端解码路径：必须在 start_session 前把文件字节传给后端。
          const file = pendingFiles[mode];
          if (!file) {
            this.status = "error";
            this.errorMessage = "未找到待上传的文件，请重新选择";
            return false;
          }
          await uploadSessionMedia(session.sessionId, file);
          if (!this.isCurrentStart(mode, requestId)) return false;
        }

        this.connectSocket(session.sessionId, mode, requestId);
        return true;
      } catch (error) {
        if (!this.isCurrentStart(mode, requestId)) return false;

        this.status = "error";
        this.errorMessage =
          error instanceof Error ? error.message : "创建会话失败，请确认后端已启动";
        return false;
      }
    },

    stopSession(nextStatus: SessionStatus = "stopped") {
      void this.stopCapture();
      playbackStartPending = false;
      mediaPlaybackActive = false;
      pendingMediaElementCapture = false;
      pendingMediaReadyState = null;
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "stop_session" }));
      }
      socket?.close();
      socket = null;
      this.wsConnected = false;
      this.status = nextStatus;
    },

    pauseSession() {
      if (this.status !== "running") return;
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "pause_session" }));
      }
      this.status = "paused";
    },

    resumeSession() {
      if (this.status !== "paused") return;
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "resume_session" }));
      }
      this.status = "running";
    },

    resetSessionData() {
      playbackStartPending = false;
      mediaPlaybackActive = false;
      pendingMediaElementCapture = false;
      pendingMediaReadyState = null;
      mediaElement = null;
      estimatedOutputLatencyMs = SUBTITLE_LATENCY_MS;
      recentOutputLatencies.length = 0;
      this.sessionId = null;
      this.sourceSyncState = { ...defaultSourceSyncState };
      this.mediaUrl = null;
      this.audioUrl = null;
      this.playbackMs = 0;
      this.activeSegmentId = null;
      this.fixtureAppliedRevisionIds = [];
      this.sourceSegments = [];
      this.translationSegments = [];
      this.revisions = [];
      this.errorMessage = null;
      this.reportId = null;
      this.report = null;
      this.reportLoading = false;
      this.reportError = null;
    },

    loadTestVideoFixturePreview() {
      this.mediaUrl = testVideoFixture.videoUrl;
      this.audioUrl = testVideoFixture.audioUrl;
      this.playbackMs = 0;
      this.activeSegmentId = testVideoFixture.segments[0]?.segmentId ?? null;
      this.fixtureAppliedRevisionIds = [];
      this.sourceSegments = createFixtureSourceSegments();
      this.translationSegments = createFixtureTranslationSegments();
      this.revisions = [];
      this.sourceSyncState = {
        status: "listening",
        lagMs: 0,
        message: "本地测试素材已就绪"
      };
    },

    clearLocalMediaPreview() {
      this.mediaUrl = null;
      this.audioUrl = null;
      this.playbackMs = 0;
      this.activeSegmentId = null;
      this.fixtureAppliedRevisionIds = [];
      this.sourceSegments = [];
      this.translationSegments = [];
      this.revisions = [];
      this.sourceSyncState = { ...defaultSourceSyncState };
    },

    applyQuickLocalFilePreview() {
      const previewUrl = localPreviewUrls.quick;
      if (this.quickForm.source === "video-file") {
        this.mediaUrl = previewUrl;
        this.audioUrl = null;
      } else if (this.quickForm.source === "audio-file") {
        this.mediaUrl = null;
        this.audioUrl = previewUrl;
      }
    },

    setMediaElement(element: HTMLMediaElement | null) {
      mediaElement = element;
      if (element && pendingMediaReadyState && pendingMediaElementCapture && !captureStarted) {
        void this.startMediaElementStreaming(pendingMediaReadyState);
      }
    },

    startTestVideoFixtureSession(requestId: number) {
      if (!this.isCurrentStart("quick", requestId)) return;

      this.sessionId = "local-test-video-fixture";
      this.wsConnected = true;
      this.status = "running";
      // 媒体就绪，但字幕不再一次性灌入：跟随左侧播放进度逐句"听到一句、出一句"。
      this.mediaUrl = testVideoFixture.videoUrl;
      this.audioUrl = testVideoFixture.audioUrl;
      this.revealFixtureSegmentsUpTo(0);
      this.sourceSyncState = {
        status: "syncing",
        lagMs: 0,
        message: "本地素材已就绪，播放即开始实时同传"
      };
    },

    syncPlayback(currentTimeSeconds: number) {
      if (this.status !== "running" || this.modeStates.quick !== "running") return;
      const playbackMs = Math.max(0, Math.round(currentTimeSeconds * 1000));
      this.playbackMs = playbackMs;
      if (this.sessionId !== "local-test-video-fixture") {
        this.updateActiveSegmentFromPlayback(playbackMs);
        return;
      }

      this.revealFixtureSegmentsUpTo(playbackMs);
      this.sourceSyncState = {
        status: "syncing",
        lagMs: 0,
        message: `本地素材同步 ${formatPlaybackTime(playbackMs)}`
      };
    },

    syncFixturePlayback(currentTimeSeconds: number) {
      this.syncPlayback(currentTimeSeconds);
    },

    updateActiveSegmentFromPlayback(playbackMs?: number) {
      if (this.sessionId === "local-test-video-fixture") return;
      const currentPlaybackMs = playbackMs ?? this.playbackMs;
      this.activeSegmentId = activeSegmentForPlayback(
        this.sourceSegments,
        this.translationSegments,
        currentPlaybackMs
      );
    },

    isMediaElementCaptureSource(): boolean {
      return (
        this.activeMode === "quick" &&
        this.sessionId !== "local-test-video-fixture" &&
        fileSourceKeys.has(this.quickForm.source)
      );
    },

    /**
     * 按播放进度幂等重算本地测试视频应显示的字幕：
     * 同传有 1~2s 产出延迟——音频说到 startMs 的句子，约 SUBTITLE_LATENCY_MS 后才在右侧产出。
     * 故以「有效进度 effectiveMs = 播放进度 - 延迟」决定显示/活动句：视频未播放(进度0)时右侧为空，
     * 播放后字幕滞后约 1.5s 逐句滚出。刚产出的一句标记 partial（流式光标）；atMs 已到的纠偏即时套用。
     * 幂等设计保证拖动进度条前后都能正确显示/回退，不残留旧状态。
     */
    revealFixtureSegmentsUpTo(playbackMs: number) {
      const PARTIAL_WINDOW_MS = 900;
      const effectiveMs = playbackMs - SUBTITLE_LATENCY_MS;
      const revealed = testVideoFixture.segments.filter((segment) => effectiveMs >= segment.startMs);
      const activeSegment = findActiveSegment(testVideoFixture.segments, effectiveMs);
      const activeId = activeSegment?.segmentId ?? revealed[revealed.length - 1]?.segmentId ?? null;

      const revealedIds = new Set(revealed.map((segment) => segment.segmentId));
      // 纠偏是显示层事件：按播放进度 atMs 触发，但只套用到已经产出的句子上。
      const dueRevisions = testVideoFixture.revisions.filter(
        (revision) => playbackMs >= revision.atMs && revealedIds.has(revision.segmentId)
      );
      const revisionBySegment = new Map(dueRevisions.map((revision) => [revision.segmentId, revision] as const));

      this.sourceSegments = revealed.map((segment) => ({
        segmentId: segment.segmentId,
        text:
          segment.segmentId === activeId && effectiveMs - segment.startMs < PARTIAL_WINDOW_MS
            ? streamText(segment.en, (effectiveMs - segment.startMs) / PARTIAL_WINDOW_MS)
            : segment.en,
        language: "en",
        startMs: segment.startMs,
        endMs: segment.endMs,
        status:
          segment.segmentId === activeId && effectiveMs - segment.startMs < PARTIAL_WINDOW_MS
            ? ("partial" as SegmentStatus)
            : ("final" as SegmentStatus)
      }));

      this.translationSegments = revealed.map((segment) => {
        const revision = revisionBySegment.get(segment.segmentId);
        if (revision) {
          return {
            segmentId: segment.segmentId,
            text: revision.afterText,
            language: "zh",
            startMs: segment.startMs,
            endMs: segment.endMs,
            status: "revised" as SegmentStatus,
            originalText: revision.beforeText,
            revisionReason: revision.reason
          };
        }
        const isFreshActive =
          segment.segmentId === activeId && effectiveMs - segment.startMs < PARTIAL_WINDOW_MS;
        return {
          segmentId: segment.segmentId,
          text: isFreshActive ? streamText(segment.zh, (effectiveMs - segment.startMs) / PARTIAL_WINDOW_MS) : segment.zh,
          language: "zh",
          startMs: segment.startMs,
          endMs: segment.endMs,
          status: (isFreshActive ? "partial" : "final") as SegmentStatus
        };
      });

      this.revisions = dueRevisions.map((revision) => createFixtureRevisionEvent(revision)).reverse();
      this.fixtureAppliedRevisionIds = dueRevisions.map((revision) => revision.revisionId);
      this.activeSegmentId = activeId;
      this.playbackMs = playbackMs;
    },

    connectSocket(sessionId: string, mode: ProductMode, requestId: number) {
      socket?.close();
      // 判定本次会话是否需要前端实时采集音频（麦克风/标签页/屏幕/系统音频）。
      const sourceKey = mode === "quick" ? this.quickForm.source : this.floatingForm.source;
      pendingCaptureKind = captureKindBySource[sourceKey] ?? null;
      pendingMediaElementCapture = mode === "quick" && fileSourceKeys.has(sourceKey);
      pendingMediaReadyState = null;
      captureStarted = false;
      playbackStartPending =
        mode === "quick" &&
        playbackControlledSourceKeys.has(sourceKey) &&
        !pendingMediaElementCapture;
      mediaPlaybackActive = false;
      let connection: WebSocket;
      connection = createSessionSocket(
        sessionId,
        {
          onOpen: () => {
            if (!this.isCurrentStart(mode, requestId, sessionId)) {
              connection.close();
              return;
            }
            this.wsConnected = true;
            this.status = "running";
            if (playbackStartPending && mediaPlaybackActive) {
              connection.send(JSON.stringify({ type: "start_session" }));
              playbackStartPending = false;
              this.modeStates.quick = "running";
            }
          },
          onClose: () => {
            if (!this.isCurrentStart(mode, requestId, sessionId)) return;
            this.wsConnected = false;
            if (this.status === "running") this.status = "stopped";
          },
          onError: (message) => {
            if (!this.isCurrentStart(mode, requestId, sessionId)) return;
            this.status = "error";
            this.errorMessage = message;
          },
          onEvent: (event) => {
            if (this.isCurrentStart(mode, requestId, sessionId)) this.applyServerEvent(event);
          }
        },
        { autoStart: !playbackStartPending }
      );
      socket = connection;
    },

    applyServerEvent(event: ServerEvent) {
      if (event.type === "session_started") {
        this.sessionId = event.sessionId;
        return;
      }

      const liveEventsLocked =
        this.reportLoading || Boolean(this.activeMode && this.modeStates[this.activeMode] === "report");

      if (event.type === "source_sync_state") {
        if (liveEventsLocked) return;
        if (pendingMediaElementCapture && event.state.status === "ready") {
          pendingMediaReadyState = event.state;
          void this.startMediaElementStreaming(event.state);
          return;
        }
        this.sourceSyncState = event.state;
        // 后端管线就绪（pcm_queue 已建）后再开始推流，避免早期帧被丢弃。
        if (pendingCaptureKind && !captureStarted && event.state.status === "ready") {
          captureStarted = true;
          void this.startCaptureStreaming(pendingCaptureKind);
        }
        return;
      }

      if (event.type === "transcript_segment") {
        if (liveEventsLocked) return;
        recordOutputLatency(event.segment, this.playbackMs);
        this.sourceSegments = upsertSegment(this.sourceSegments, event.segment);
        this.updateActiveSegmentFromPlayback();
        return;
      }

      if (event.type === "translation_segment") {
        if (liveEventsLocked) return;
        recordOutputLatency(event.segment, this.playbackMs);
        this.translationSegments = upsertSegment(this.translationSegments, event.segment);
        this.updateActiveSegmentFromPlayback();
        return;
      }

      if (event.type === "revision_event") {
        if (liveEventsLocked) return;
        this.revisions = [event.revision, ...this.revisions].slice(0, 20);
        this.markRevised(event.revision);
        return;
      }

      if (event.type === "session_report") {
        // 会话自然结束或 stop_session 后，后端完成会后完整纠偏并下发报告 id。
        // 适用于「音频播放完自动结束」与「用户手动结束」两条路径。
        this.reportId = event.reportId;
        const mode = this.activeMode ?? "quick";
        this.modeStates[mode] = "report";
        this.status = "stopped";
        this.activeMode = null;
        void this.loadReport();
        return;
      }

      if (event.type === "error") {
        this.status = "error";
        this.errorMessage = event.message;
      }
    },

    markRevised(revision: RevisionEvent) {
      const updateStatus = (segment: SubtitleSegment): SubtitleSegment =>
        revision.targetSegmentIds.includes(segment.segmentId)
          ? { ...segment, status: "revised" as SegmentStatus }
          : segment;

      this.sourceSegments = this.sourceSegments.map(updateStatus);
      this.translationSegments = this.translationSegments.map((segment) =>
        revision.targetSegmentIds.includes(segment.segmentId)
          ? {
              ...segment,
              text: revision.afterText,
              status: "revised" as SegmentStatus,
              originalText: revision.beforeText,
              revisionReason: revision.reason
            }
          : segment
      );
    },

    async loadReport() {
      if (!this.sessionId || !this.reportId) return;
      this.reportLoading = true;
      this.reportError = null;
      try {
        this.report = await getSessionReport(this.sessionId);
      } catch (error) {
        this.reportError = error instanceof Error ? error.message : "报告拉取失败";
      } finally {
        this.reportLoading = false;
      }
    },

    /** 实时采集类音源：取流 → 16k PCM → WS 二进制推送。后端管线就绪后调用。 */
    async startCaptureStreaming(kind: CaptureSourceKind) {
      try {
        const stream = await acquireStream(kind);
        if (!socket || socket.readyState !== WebSocket.OPEN) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        audioCapture = await startAudioCapture(stream, {
          onChunk: (chunk) => {
            if (socket && socket.readyState === WebSocket.OPEN) socket.send(chunk);
          },
          onEnded: () => {
            // 用户在系统选择器中停止共享 → 通知后端收尾并出报告。
            if (socket && socket.readyState === WebSocket.OPEN) {
              socket.send(JSON.stringify({ type: "audio_end" }));
            }
          },
          onError: (message) => {
            this.errorMessage = message;
          }
        });
      } catch (error) {
        this.status = "error";
        this.errorMessage = error instanceof Error ? error.message : "音频采集启动失败";
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "audio_end" }));
        }
      }
    },

    /** 上传视频/音频：从正在播放的媒体元素采集同一份音频，保证模型输入与画面同源。 */
    async startMediaElementStreaming(readyState: SourceSyncState) {
      if (!this.isMediaElementCaptureSource()) {
        this.sourceSyncState = readyState;
        return;
      }
      if (!mediaElement) {
        pendingMediaReadyState = readyState;
        return;
      }
      if (!socket || socket.readyState !== WebSocket.OPEN) return;

      try {
        if (!captureStarted) {
          captureStarted = true;
          audioCapture = await startMediaElementAudioCapture(mediaElement, {
            frameMs: 80,
            onChunk: (chunk) => {
              if (socket && socket.readyState === WebSocket.OPEN) socket.send(chunk);
            },
            onClock: (clock) => {
              if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ type: "media_clock", ...clock }));
              }
            },
            onEnded: () => {
              if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ type: "audio_end" }));
              }
            },
            onError: (message) => {
              this.errorMessage = message;
            }
          });
        }
        pendingMediaReadyState = null;
        this.sourceSyncState = readyState;
        this.status = "running";
        this.modeStates.quick = "running";
        try {
          await mediaElement.play();
        } catch {
          // 浏览器可能阻止带声音自动播放；采集链路已就绪，用户手动播放即可同步推流。
        }
      } catch (error) {
        captureStarted = false;
        this.status = "error";
        this.modeStates.quick = "error";
        this.errorMessage =
          error instanceof Error ? error.message : "媒体元素音频采集启动失败";
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "audio_end" }));
        }
      }
    },

    async stopCapture() {
      pendingCaptureKind = null;
      pendingMediaElementCapture = false;
      pendingMediaReadyState = null;
      captureStarted = false;
      if (audioCapture) {
        const capture = audioCapture;
        audioCapture = null;
        await capture.stop();
      }
    },

    /** 下载报告：真实后端会话走后端直链（含中文文件名）；本地演示走客户端渲染。 */
    downloadReport(format: ReportFormat) {
      if (this.sessionId && this.reportId) {
        triggerDownload(reportDownloadUrl(this.sessionId, format));
        return;
      }
      if (this.report) {
        const { body, mime, ext } = renderReportClient(this.report, format);
        const blob = new Blob([body], { type: mime });
        const url = URL.createObjectURL(blob);
        triggerDownload(url, `${this.report.sessionName || "同传报告"}.${ext}`);
        window.setTimeout(() => URL.revokeObjectURL(url), 4000);
      }
    },

    /** 本地演示（fixture，无后端）合成一份报告，保证“结束→可看可下载”闭环。 */
    buildLocalReport() {
      const segs = this.transcriptPairs
        .filter((pair) => pair.segmentId)
        .map((pair, index) => ({
          segmentId: pair.segmentId ?? `local-${index}`,
          startMs: 0,
          endMs: 0,
          timecode: pair.time,
          sourceText: pair.source,
          liveTranslation: pair.originalTranslation ?? pair.translation,
          finalTranslation: pair.translation,
          revisedRealtime: pair.state === "revised"
        }));
      const finalRevisions = this.revisions.map((rev) => ({
        segmentId: rev.targetSegmentIds[0] ?? "",
        beforeText: rev.beforeText,
        afterText: rev.afterText,
        reason: rev.reason,
        stage: "实时"
      }));
      this.report = {
        reportId: "",
        sessionId: this.sessionId ?? "",
        sessionName: this.quickForm.name || "本地演示报告",
        domain: this.quickForm.domain,
        sourceLanguage: this.quickForm.sourceLanguage,
        targetLanguage: this.quickForm.targetLanguage,
        durationMs: this.playbackMs,
        durationText: formatPlaybackTime(this.playbackMs),
        generatedAt: new Date().toLocaleString(),
        summary: `本地测试素材演示：共 ${segs.length} 句，含 ${finalRevisions.length} 处自动纠偏。`,
        qualityNotes: "本地演示报告由前端依据测试素材合成，未经后端大模型完整纠偏。",
        glossaryHits: [],
        metrics: {
          segments: segs.length,
          realtimeRevisions: finalRevisions.length,
          finalRevisions: 0,
          durationText: formatPlaybackTime(this.playbackMs)
        },
        segments: segs,
        finalRevisions,
        realtimeRevisions: finalRevisions,
        correctionModel: null
      };
      this.reportId = null;
      this.reportLoading = false;
    }
  }
});
