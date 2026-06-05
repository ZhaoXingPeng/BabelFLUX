import { defineStore } from "pinia";
import { createSession, type CreateSessionPayload } from "../api/client";
import { createSessionSocket } from "../api/ws";
import type {
  RevisionEvent,
  SegmentStatus,
  ServerEvent,
  SessionStatus,
  SourceSyncState,
  SubtitleSegment
} from "../types/events";
import type {
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
const permissionSourceKeys = new Set(["microphone", "browser-tab", "screen-window"]);

const inputModeBySourceKey: Record<string, CreateSessionPayload["inputMode"]> = {
  "video-file": "upload_video",
  "audio-file": "upload_audio",
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
  sourceSegments: SubtitleSegment[];
  translationSegments: SubtitleSegment[];
  revisions: RevisionEvent[];
  errorMessage: string | null;
  productMode: ProductMode;
  activeMode: ProductMode | null;
  endingMode: ProductMode | null;
  showEndDialog: boolean;
  selectedDisplayMode: string;
  modeStates: Record<ProductMode, RuntimeState>;
  quickForm: QuickFormState;
  floatingForm: FloatingFormState;
  quickInput: SourceInputState;
  floatingInput: SourceInputState;
  startRequestId: number;
}

function upsertSegment(items: SubtitleSegment[], segment: SubtitleSegment): SubtitleSegment[] {
  const index = items.findIndex((item) => item.segmentId === segment.segmentId);
  if (index === -1) return [...items, segment];
  return items.map((item, itemIndex) => (itemIndex === index ? segment : item));
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
    if (!mediaDevices.getDisplayMedia) throw new Error("当前浏览器不支持屏幕或标签页采集");
    const stream = await mediaDevices.getDisplayMedia({ audio: true, video: true });
    stopMediaStream(stream);
    return sourceKey === "browser-tab" ? "浏览器标签页音频已授权" : "屏幕或窗口音频已授权";
  }

  throw new Error("该声源不需要浏览器授权");
}

export const useSessionStore = defineStore("session", {
  state: (): SessionState => ({
    sessionId: null,
    status: "idle",
    wsConnected: false,
    sourceSyncState: { ...defaultSourceSyncState },
    sourceSegments: [],
    translationSegments: [],
    revisions: [],
    errorMessage: null,
    productMode: "quick",
    activeMode: null,
    endingMode: null,
    showEndDialog: false,
    selectedDisplayMode: "逐句对照",
    modeStates: {
      quick: "setup",
      floating: "setup"
    },
    quickForm: {
      name: "国际技术分享同传",
      domain: "技术",
      sourceLanguage: "英语",
      targetLanguage: "中文",
      modelProfile: "智能默认",
      source: "video-file"
    },
    floatingForm: {
      domain: "通用",
      sourceLanguage: "自动检测",
      targetLanguage: "中文",
      modelProfile: "快速低延迟",
      source: "browser-tab",
      style: "双语字幕",
      size: "标准",
      opacity: "90%"
    },
    quickInput: { ...defaultSourceInputState },
    floatingInput: { ...defaultSourceInputState },
    startRequestId: 0
  }),

  getters: {
    activeSourceSegment: (state): SubtitleSegment | undefined =>
      [...state.sourceSegments].reverse().find((segment) => segment.status !== "revised"),
    activeTranslationSegment: (state): SubtitleSegment | undefined =>
      [...state.translationSegments].reverse().find((segment) => segment.status !== "revised"),
    productModes: (): ProductModeOption[] => productModeOptions,
    modelProfiles: (): string[] => modelProfileOptions,
    domains: (): string[] => domainOptions,
    languages: (): string[] => languageOptions,
    targetLanguages: (): string[] => targetLanguageOptions,
    displayModes: (): string[] => displayModeOptions,
    quickSources: (): SourceOption[] => quickSourceOptions,
    floatingSources: (): SourceOption[] => floatingSourceOptions,
    transcriptPairs: (state): TranscriptPair[] => {
      if (state.sourceSegments.length === 0 && state.translationSegments.length === 0) return samplePairs;

      const maxLength = Math.max(state.sourceSegments.length, state.translationSegments.length);
      return Array.from({ length: maxLength }, (_, index) => {
        const source = state.sourceSegments[index];
        const translation = state.translationSegments[index];
        return {
          time: source ? `${Math.round(source.startMs / 1000)}s` : "--",
          source: source?.text ?? "等待源语言转写...",
          translation: translation?.text ?? "等待译文...",
          state: translation?.status ?? source?.status ?? "partial"
        };
      });
    },
    currentPair(): TranscriptPair {
      return this.transcriptPairs[this.transcriptPairs.length - 1] ?? samplePairs[0];
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
      return [
        { label: "时长", value: "18:24" },
        { label: "语言", value: `${this.quickForm.sourceLanguage} -> ${this.quickForm.targetLanguage}` },
        { label: "修正", value: `${this.revisions.length} 条` },
        { label: "导出", value: "TXT / SRT / MD" }
      ];
    }
  },

  actions: {
    selectMode(mode: ProductMode) {
      this.productMode = mode;
    },

    selectQuickSource(source: SourceOption) {
      if (source.disabled || this.quickForm.source === source.key) return;
      this.quickForm.source = source.key;
      this.quickInput = { ...defaultSourceInputState };
    },

    selectFloatingSource(source: SourceOption) {
      if (source.disabled || this.floatingForm.source === source.key) return;
      this.floatingForm.source = source.key;
      this.floatingInput = { ...defaultSourceInputState };
    },

    setQuickSourceFile(file: File | null) {
      this.quickInput.fileName = file?.name ?? "";
    },

    updateQuickSourceUrl(url: string) {
      this.quickInput.url = url;
    },

    setFloatingSourceFile(file: File | null) {
      this.floatingInput.fileName = file?.name ?? "";
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

    openDesktopFloating() {
      window.location.href = "lingosync://floating/start";
    },

    async startMode(mode: ProductMode) {
      const blockedSource = mode === "quick" ? this.quickSource.disabled : this.floatingSource.disabled;
      const inputReady =
        mode === "quick"
          ? isSourceInputReady(this.quickForm.source, this.quickInput)
          : isSourceInputReady(this.floatingForm.source, this.floatingInput);
      if (blockedSource || !inputReady || !["setup", "report", "error"].includes(this.modeStates[mode])) return;

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
      this.startRequestId += 1;
      this.modeStates[this.endingMode] = "report";
      if (this.activeMode === this.endingMode) this.activeMode = null;
      this.showEndDialog = false;
      this.endingMode = null;
      this.stopSession("stopped");
    },

    resetMode(mode: ProductMode) {
      if (this.activeMode === mode) {
        this.startRequestId += 1;
        this.activeMode = null;
        this.stopSession("idle");
        this.resetSessionData();
      }
      this.modeStates[mode] = "setup";
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
      this.status = "connecting";
      this.errorMessage = null;

      try {
        const session = await createSession(this.buildSessionPayload(mode));

        if (!this.isCurrentStart(mode, requestId)) return false;

        this.sessionId = session.sessionId;
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
      this.sessionId = null;
      this.sourceSyncState = { ...defaultSourceSyncState };
      this.sourceSegments = [];
      this.translationSegments = [];
      this.revisions = [];
      this.errorMessage = null;
    },

    connectSocket(sessionId: string, mode: ProductMode, requestId: number) {
      socket?.close();
      let connection: WebSocket;
      connection = createSessionSocket(sessionId, {
        onOpen: () => {
          if (!this.isCurrentStart(mode, requestId, sessionId)) {
            connection.close();
            return;
          }
          this.wsConnected = true;
          this.status = "running";
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
      });
      socket = connection;
    },

    applyServerEvent(event: ServerEvent) {
      if (event.type === "session_started") {
        this.sessionId = event.sessionId;
        return;
      }

      if (event.type === "source_sync_state") {
        this.sourceSyncState = event.state;
        return;
      }

      if (event.type === "transcript_segment") {
        this.sourceSegments = upsertSegment(this.sourceSegments, event.segment);
        return;
      }

      if (event.type === "translation_segment") {
        this.translationSegments = upsertSegment(this.translationSegments, event.segment);
        return;
      }

      if (event.type === "revision_event") {
        this.revisions = [event.revision, ...this.revisions].slice(0, 20);
        this.markRevised(event.revision.targetSegmentIds);
        return;
      }

      if (event.type === "error") {
        this.status = "error";
        this.errorMessage = event.message;
      }
    },

    markRevised(segmentIds: string[]) {
      const updateStatus = (segment: SubtitleSegment): SubtitleSegment =>
        segmentIds.includes(segment.segmentId)
          ? { ...segment, status: "revised" as SegmentStatus }
          : segment;

      this.sourceSegments = this.sourceSegments.map(updateStatus);
      this.translationSegments = this.translationSegments.map(updateStatus);
    }
  }
});
