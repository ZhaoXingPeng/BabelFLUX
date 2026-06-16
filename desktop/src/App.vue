<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow, PhysicalPosition } from "@tauri-apps/api/window";
import FloatingCaption from "@frontend/components/workbench/FloatingCaption.vue";
import type { SourceSyncState, ServerEvent } from "@frontend/types/events";
import type { TranscriptPair } from "@frontend/types/workflow";
import { createSession, getSessionReport, reportDownloadUrl, type ReportFormat } from "@frontend/api/client";
import {
  acquireStream,
  startAudioCapture,
  type AudioCaptureSession,
  type CaptureSourceKind
} from "@frontend/composables/useAudioCapture";
import { claimHandoffToken, connectDesktopSession } from "./api/sessionBridge";
import { getLaunchDeepLink, listenForDeepLinks, parseLaunchParams, type LaunchParams } from "./launcherBridge";
import { loadOverlaySettings, saveOverlaySettings, type OverlaySettings } from "./localSettings";
import { startNativeSystemAudioCapture } from "./nativeAudioCapture";
import { registerUnlockShortcut, setOverlayLocked } from "./overlayWindow";

const settings = ref<OverlaySettings>(loadOverlaySettings());
// Older builds used the pin action as a click-through lock, which left users
// unable to unpin or close the overlay. Normalize that persisted state on boot.
settings.value.locked = false;
settings.value.form.captionPinned = false;
let currentWindow: ReturnType<typeof getCurrentWindow> | null = null;
try {
  currentWindow = getCurrentWindow();
} catch {
  currentWindow = null;
}
const pair = ref<TranscriptPair>({
  time: "00:00",
  source: "Waiting for audio…",
  translation: "选择音源后开始悬浮同传。",
  state: "partial",
  isActive: true
});
const status = ref<SourceSyncState>({
  status: "listening",
  lagMs: 0,
  message: "等待音源"
});
const errorMessage = ref("");
const displayMode = ref<NonNullable<LaunchParams["displayMode"]>>("bilingual");

// 模式：handoff = 由 Web 工作台投送（仅显示）；standalone = 悬浮窗自选音源、自采集。
const mode = ref<"handoff" | "standalone">("standalone");
const capturing = ref(false);
const starting = ref(false);
const reportPending = ref(false);
const activeSessionId = ref<string | null>(null);
const reportId = ref<string | null>(null);

const SOURCE_OPTIONS: { value: CaptureSourceKind; label: string }[] = [
  { value: "system_audio", label: "Windows 系统音频" },
  { value: "screen_window", label: "屏幕 / 窗口" },
  { value: "browser_audio", label: "标签页音频" },
  { value: "microphone", label: "麦克风" }
];
const selectedSource = ref<CaptureSourceKind>("system_audio");
const launchSourceMap: Record<string, CaptureSourceKind> = {
  "system-audio": "system_audio",
  system_audio: "system_audio",
  "screen-window": "screen_window",
  screen_window: "screen_window",
  "browser-tab": "browser_audio",
  browser_audio: "browser_audio",
  microphone: "microphone"
};

let socket: WebSocket | null = null;
let capture: AudioCaptureSession | null = null;
let captureStarted = false;
let dragState:
  | {
      pointerId: number;
      startScreenX: number;
      startScreenY: number;
      windowX: number;
      windowY: number;
      scaleFactor: number;
    }
  | null = null;
let pendingDragPosition: PhysicalPosition | null = null;
let dragFrame = 0;
let cleanupDeepLink: (() => void) | null = null;
let cleanupForwardedDeepLink: (() => void) | null = null;
let cleanupShortcut: (() => void) | null = null;
let nativeAudioWatchdog: number | null = null;
let nativeAudioChunks = 0;
let nativeAudioSignalChunks = 0;
let pendingReportResolver: ((ready: boolean) => void) | null = null;
// 16kHz s16le mono 约 32KB/s；超过 1 秒发送积压时丢当前帧，避免旧音频拖慢同传。
const MAX_AUDIO_SOCKET_BUFFER_BYTES = 32_000;

const shellStyle = computed(() => ({ opacity: settings.value.opacity }));

const languageCodeByLabel: Record<string, string> = {
  自动检测: "auto",
  英语: "en",
  中文: "zh",
  日语: "ja",
  韩语: "ko",
  法语: "fr",
  德语: "de"
};
const toCode = (label: string) => languageCodeByLabel[label] ?? label;

function applyStandaloneLaunchParams(params: LaunchParams) {
  mode.value = "standalone";
  displayMode.value = params.displayMode ?? displayMode.value;
  starting.value = false;
  capturing.value = false;
  captureStarted = false;
  status.value = { status: "listening", lagMs: 0, message: "等待音源" };
  if (params.source && launchSourceMap[params.source]) {
    selectedSource.value = launchSourceMap[params.source];
  }
}

function formatTime(ms: number): string {
  const total = Math.floor(ms / 1000);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function resolvePendingReport(ready: boolean) {
  pendingReportResolver?.(ready);
  pendingReportResolver = null;
}

async function waitForReport(timeoutMs = 45_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (reportId.value) return true;
    if (activeSessionId.value) {
      try {
        const report = await getSessionReport(activeSessionId.value);
        reportId.value = report.reportId;
        return true;
      } catch {
        // Report is not persisted yet; keep polling until the bounded backend path finishes.
      }
    }
    await wait(1_000);
  }
  resolvePendingReport(false);
  return false;
}

function reportFilename(format: ReportFormat) {
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  return `BabelFlux-report-${stamp}.${format}`;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 4000);
}

async function downloadCurrentReport(format: ReportFormat = "txt") {
  if (!activeSessionId.value) return false;
  const response = await fetch(reportDownloadUrl(activeSessionId.value, format));
  if (!response.ok) return false;
  downloadBlob(await response.blob(), reportFilename(format));
  return true;
}

function applyEvent(event: ServerEvent) {
  if (event.type === "session_started") {
    status.value = { status: "syncing", lagMs: 0, message: "悬浮窗已接管" };
    return;
  }
  if (event.type === "source_sync_state") {
    status.value = event.state;
    // standalone：后端管线就绪后再开始推流，避免早期帧被丢弃。
    if (mode.value === "standalone" && capturing.value && !captureStarted && event.state.status === "ready") {
      captureStarted = true;
      void beginCapture();
    }
    return;
  }
  if (event.type === "transcript_segment") {
    pair.value = {
      ...pair.value,
      segmentId: event.segment.segmentId,
      source: event.segment.text,
      time: formatTime(event.segment.startMs),
      state: event.segment.status,
      isActive: true
    };
    return;
  }
  if (event.type === "translation_segment") {
    pair.value = {
      ...pair.value,
      segmentId: event.segment.segmentId,
      translation: event.segment.text,
      time: formatTime(event.segment.startMs),
      state: event.segment.status,
      isActive: true
    };
    return;
  }
  if (event.type === "revision_event") {
    pair.value = {
      ...pair.value,
      translation: event.revision.afterText,
      state: "revised",
      originalTranslation: event.revision.beforeText,
      revisionReason: event.revision.reason,
      isActive: true
    };
    return;
  }
  if (event.type === "session_report") {
    reportId.value = event.reportId;
    reportPending.value = false;
    status.value = { status: "ready", lagMs: 0, message: "最终报告已生成，正在下载" };
    resolvePendingReport(true);
    return;
  }
  if (event.type === "error") {
    errorMessage.value = event.message;
    status.value = { status: "missing", lagMs: 0, message: event.message };
    resolvePendingReport(false);
  }
}

// ---- handoff 模式（由 Web 工作台投送，仅显示）----
async function startFromLaunchParams(params: LaunchParams) {
  errorMessage.value = "";
  if (!params.token) {
    if (capture || socket || capturing.value || mode.value === "handoff") await stopStandalone();
    applyStandaloneLaunchParams(params);
    return;
  }
  displayMode.value = params.displayMode ?? "bilingual";
  try {
    if (capture || socket || capturing.value) await stopStandalone();
    const claim = await claimHandoffToken(params.token);
    mode.value = "handoff";
    displayMode.value = claim.displayMode;
    activeSessionId.value = claim.sessionId;
    reportId.value = null;
    socket?.close();
    socket = connectDesktopSession(claim.wsUrl, applyEvent);
  } catch (error) {
    applyStandaloneLaunchParams(params);
    errorMessage.value = error instanceof Error ? error.message : "桌面接管失败";
    status.value = { status: "missing", lagMs: 0, message: errorMessage.value };
  }
}

function clearNativeAudioWatchdog() {
  if (nativeAudioWatchdog !== null) {
    window.clearTimeout(nativeAudioWatchdog);
    nativeAudioWatchdog = null;
  }
}

function resetNativeAudioStats() {
  clearNativeAudioWatchdog();
  nativeAudioChunks = 0;
  nativeAudioSignalChunks = 0;
}

function hasPcmSignal(chunk: ArrayBuffer) {
  const pcm = new Int16Array(chunk);
  for (let index = 0; index < pcm.length; index += 1) {
    if (Math.abs(pcm[index]) > 64) return true;
  }
  return false;
}

function trackNativeAudioChunk(chunk: ArrayBuffer) {
  if (selectedSource.value !== "system_audio") return;
  nativeAudioChunks += 1;
  const hasSignal = hasPcmSignal(chunk);
  if (hasSignal) nativeAudioSignalChunks += 1;

  if (nativeAudioChunks === 1) {
    clearNativeAudioWatchdog();
    status.value = {
      status: "syncing",
      lagMs: 0,
      message: hasSignal ? "已捕获 Windows 系统音频" : "已连接 Windows 系统音频，等待声音"
    };
    return;
  }

  if (hasSignal && nativeAudioSignalChunks === 1) {
    status.value = { status: "syncing", lagMs: 0, message: "已捕获 Windows 系统音频" };
    return;
  }

  if (nativeAudioChunks === 30 && nativeAudioSignalChunks === 0) {
    status.value = {
      status: "lagging",
      lagMs: 0,
      message: "正在监听 Windows 系统音频，尚未检测到声音"
    };
  }
}

function sendAudioChunk(chunk: ArrayBuffer) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  if (socket.bufferedAmount > MAX_AUDIO_SOCKET_BUFFER_BYTES) return;
  socket.send(chunk);
}

// ---- standalone 模式（悬浮窗自选音源、自采集同传）----
async function startStandalone() {
  if (starting.value || capturing.value) return;
  starting.value = true;
  errorMessage.value = "";
  captureStarted = false;
  const kind = selectedSource.value;
  try {
    const session = await createSession({
      inputMode: kind,
      sourceLanguage: toCode(settings.value.form.sourceLanguage),
      targetLanguage: toCode(settings.value.form.targetLanguage),
      productMode: "floating",
      sessionName: "悬浮自采集",
      domain: settings.value.form.domain,
      modelProfile: settings.value.form.modelProfile,
      sourceKey: kind,
      sourcePermission: "granted"
    });
    activeSessionId.value = session.sessionId;
    reportId.value = null;
    capturing.value = true;
    status.value = {
      status: "syncing",
      lagMs: 0,
      message: kind === "system_audio" ? "正在读取 Windows 系统音频" : "正在连接同传引擎…"
    };
    socket?.close();
    socket = connectDesktopSession(
      `/api/ws/sessions/${session.sessionId}?token=${encodeURIComponent(session.wsToken)}`,
      applyEvent
    );
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "无法创建悬浮同传会话";
    status.value = { status: "missing", lagMs: 0, message: errorMessage.value };
    capturing.value = false;
  } finally {
    starting.value = false;
  }
}

async function beginCapture() {
  try {
    resetNativeAudioStats();
    const sendChunk = (chunk: ArrayBuffer) => {
      trackNativeAudioChunk(chunk);
      sendAudioChunk(chunk);
    };
    const handleEnded = () => {
      if (reportPending.value) return;
      if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "audio_end" }));
      void stopStandalone();
    };
    const handleError = (message: string) => {
      errorMessage.value = message;
      status.value = { status: "missing", lagMs: 0, message };
    };

    if (selectedSource.value === "system_audio") {
      nativeAudioWatchdog = window.setTimeout(() => {
        if (selectedSource.value !== "system_audio" || !capturing.value || nativeAudioChunks > 0) return;
        status.value = {
          status: "lagging",
          lagMs: 0,
          message: "未收到 Windows 音频帧，请确认默认输出设备正在播放声音"
        };
      }, 3000);
      capture = await startNativeSystemAudioCapture({
        frameMs: 40,
        onChunk: sendChunk,
        onEnded: handleEnded,
        onError: handleError
      });
      return;
    }

    const stream = await acquireStream(selectedSource.value);
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    capture = await startAudioCapture(stream, {
      frameMs: 40,
      onChunk: sendChunk,
      onEnded: handleEnded,
      onError: handleError
    });
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "音频采集启动失败";
    status.value = { status: "missing", lagMs: 0, message: errorMessage.value };
    void stopStandalone();
  }
}

async function stopStandalone() {
  resolvePendingReport(false);
  reportPending.value = false;
  capturing.value = false;
  captureStarted = false;
  resetNativeAudioStats();
  if (capture) {
    const current = capture;
    capture = null;
    await current.stop();
  }
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "stop_session" }));
  }
  socket?.close();
  socket = null;
  activeSessionId.value = null;
  reportId.value = null;
  status.value = { status: "listening", lagMs: 0, message: "已停止，可重新选择音源" };
}

async function finishStandaloneAndDownloadReport() {
  if (mode.value !== "standalone" || !activeSessionId.value) {
    await stopStandalone();
    return;
  }
  if (reportPending.value) return;

  reportPending.value = true;
  capturing.value = false;
  captureStarted = false;
  resetNativeAudioStats();
  status.value = { status: "syncing", lagMs: 0, message: "正在生成最终报告" };

  if (capture) {
    const current = capture;
    capture = null;
    await current.stop();
  }

  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: "stop_session" }));
    const ready = await waitForReport();
    if (ready) {
      const downloaded = await downloadCurrentReport("txt");
      if (downloaded) await wait(1200);
    } else {
      status.value = { status: "missing", lagMs: 0, message: "报告生成超时，可在 Web 端稍后下载" };
      await wait(1200);
    }
  }

  socket?.close();
  socket = null;
  reportPending.value = false;
}

async function closeOverlayWindow() {
  if (mode.value === "standalone" && (capturing.value || socket || activeSessionId.value)) {
    await finishStandaloneAndDownloadReport();
  } else {
    await stopStandalone();
  }
  mode.value = "standalone";
  errorMessage.value = "";
  try {
    await invoke("exit_overlay_app");
    return;
  } catch {
  }
  try {
    if (currentWindow) {
      await currentWindow.close();
      return;
    }
  } catch {
  }
  window.close();
}

function startWindowDrag(event: PointerEvent) {
  if (event.button !== 0) return;
  if (settings.value.form.captionPinned || settings.value.locked) return;
  const target = event.target as HTMLElement | null;
  if (target?.closest("button, input, select, textarea, a")) return;
  if (!currentWindow) return;
  event.preventDefault();
  (event.currentTarget as HTMLElement | null)?.setPointerCapture?.(event.pointerId);
  void Promise.all([currentWindow.outerPosition(), currentWindow.scaleFactor()])
    .then(([position, scaleFactor]) => {
      dragState = {
        pointerId: event.pointerId,
        startScreenX: event.screenX,
        startScreenY: event.screenY,
        windowX: position.x,
        windowY: position.y,
        scaleFactor
      };
    })
    .catch(() => {
      void currentWindow?.startDragging().catch(() => undefined);
    });
}

function moveWindowDrag(event: PointerEvent) {
  if (!currentWindow || !dragState || event.pointerId !== dragState.pointerId) return;
  event.preventDefault();
  const nextX = Math.round(dragState.windowX + (event.screenX - dragState.startScreenX) * dragState.scaleFactor);
  const nextY = Math.round(dragState.windowY + (event.screenY - dragState.startScreenY) * dragState.scaleFactor);
  pendingDragPosition = new PhysicalPosition(nextX, nextY);
  if (dragFrame) return;
  dragFrame = requestAnimationFrame(() => {
    dragFrame = 0;
    const position = pendingDragPosition;
    pendingDragPosition = null;
    if (position) void currentWindow?.setPosition(position).catch(() => undefined);
  });
}

function endWindowDrag(event: PointerEvent) {
  if (!dragState || event.pointerId !== dragState.pointerId) return;
  (event.currentTarget as HTMLElement | null)?.releasePointerCapture?.(event.pointerId);
  dragState = null;
}

async function listenForForwardedDeepLinks(handler: (params: LaunchParams) => void) {
  try {
    return await listen<string>("deep-link-url", (event) => handler(parseLaunchParams(event.payload)));
  } catch {
    return () => undefined;
  }
}

watch(settings, (value) => saveOverlaySettings(value), { deep: true });
watch(
  () => settings.value.form.captionPinned,
  async () => {
    dragState = null;
    settings.value.locked = false;
    await setOverlayLocked(false);
  }
);

onMounted(async () => {
  settings.value.locked = false;
  settings.value.form.captionPinned = false;
  await setOverlayLocked(false);
  cleanupDeepLink = await listenForDeepLinks(startFromLaunchParams);
  cleanupForwardedDeepLink = await listenForForwardedDeepLinks(startFromLaunchParams);
  cleanupShortcut = await registerUnlockShortcut(async () => {
    settings.value.locked = false;
    settings.value.form.captionPinned = false;
    await setOverlayLocked(false);
  });
  const launched = await getLaunchDeepLink();
  const params = launched ?? parseLaunchParams();
  await startFromLaunchParams(params);
});

onUnmounted(() => {
  void stopStandalone();
  cleanupDeepLink?.();
  cleanupForwardedDeepLink?.();
  cleanupShortcut?.();
});
</script>

<template>
  <main
    class="desktop-overlay-shell"
    :class="{ pinned: settings.form.captionPinned }"
    :style="shellStyle"
    @pointerdown="startWindowDrag"
    @pointermove="moveWindowDrag"
    @pointerup="endWindowDrag"
    @pointercancel="endWindowDrag"
  >
    <!-- standalone 启动条：透明框自带音源下拉，选源后开始（默认系统音频）。整条可拖动。 -->
    <div
      v-if="mode === 'standalone' && !capturing && !settings.locked"
      class="overlay-launcher"
    >
      <span class="overlay-launcher-title">悬浮同传</span>
      <select v-model="selectedSource" class="overlay-source-select" aria-label="选择音源">
        <option v-for="opt in SOURCE_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
      </select>
      <button class="overlay-start" type="button" :disabled="starting" @click="startStandalone">
        {{ starting ? "连接中…" : "开始" }}
      </button>
      <button class="overlay-close" type="button" aria-label="关闭悬浮窗" title="关闭悬浮窗" @click="closeOverlayWindow">
        ×
      </button>
    </div>

    <div
      v-if="capturing || mode === 'handoff'"
      class="desktop-caption-drag-layer"
    >
      <FloatingCaption
        :pair="pair"
        :form="settings.form"
        :display-mode="displayMode"
        :locked="settings.locked"
        :status="status"
        desktop
        @close="closeOverlayWindow"
      />
    </div>

    <p v-if="errorMessage" class="desktop-overlay-error">{{ errorMessage }}</p>
  </main>
</template>
