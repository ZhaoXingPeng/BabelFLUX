<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow, PhysicalPosition } from "@tauri-apps/api/window";
import FloatingCaption from "@frontend/components/workbench/FloatingCaption.vue";
import type { SourceSyncState, ServerEvent } from "@frontend/types/events";
import type { TranscriptPair } from "@frontend/types/workflow";
import { createSession } from "@frontend/api/client";
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

const SOURCE_OPTIONS: { value: CaptureSourceKind; label: string }[] = [
  { value: "system_audio", label: "Windows 系统音频" },
  { value: "screen_window", label: "屏幕 / 窗口" },
  { value: "browser_audio", label: "标签页音频" },
  { value: "microphone", label: "麦克风" }
];
const selectedSource = ref<CaptureSourceKind>("system_audio");

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

function formatTime(ms: number): string {
  const total = Math.floor(ms / 1000);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

function applyEvent(event: ServerEvent) {
  if (event.type === "session_started") {
    status.value = { status: "syncing", lagMs: 0, message: "悬浮窗已接管" };
    return;
  }
  if (event.type === "source_sync_state") {
    status.value = event.state;
    // standalone：后端管线就绪后再开始推流，避免早期帧被丢弃。
    if (mode.value === "standalone" && capturing.value && !captureStarted) {
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
  if (event.type === "error") {
    errorMessage.value = event.message;
    status.value = { status: "missing", lagMs: 0, message: event.message };
  }
}

// ---- handoff 模式（由 Web 工作台投送，仅显示）----
async function startFromLaunchParams(params: LaunchParams) {
  errorMessage.value = "";
  if (!params.token) return; // 无 token：保持 standalone 模式
  mode.value = "handoff";
  displayMode.value = params.displayMode ?? "bilingual";
  try {
    const claim = await claimHandoffToken(params.token);
    displayMode.value = claim.displayMode;
    socket?.close();
    socket = connectDesktopSession(claim.wsUrl, applyEvent);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "桌面接管失败";
    status.value = { status: "missing", lagMs: 0, message: errorMessage.value };
  }
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
    capturing.value = true;
    status.value = {
      status: "syncing",
      lagMs: 0,
      message: kind === "system_audio" ? "正在读取 Windows 系统音频" : "正在连接同传引擎…"
    };
    socket?.close();
    socket = connectDesktopSession(`/api/ws/sessions/${session.sessionId}`, applyEvent);
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
    const sendChunk = (chunk: ArrayBuffer) => {
      if (socket && socket.readyState === WebSocket.OPEN) socket.send(chunk);
    };
    const handleEnded = () => {
      if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "audio_end" }));
      void stopStandalone();
    };
    const handleError = (message: string) => {
      errorMessage.value = message;
    };

    if (selectedSource.value === "system_audio") {
      capture = await startNativeSystemAudioCapture({
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
  capturing.value = false;
  captureStarted = false;
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
  status.value = { status: "listening", lagMs: 0, message: "已停止，可重新选择音源" };
}

function startWindowDrag(event: PointerEvent) {
  if (event.button !== 0) return;
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
  async (pinned) => {
    settings.value.locked = pinned;
    await setOverlayLocked(pinned);
  }
);

onMounted(async () => {
  cleanupDeepLink = await listenForDeepLinks(startFromLaunchParams);
  cleanupForwardedDeepLink = await listenForForwardedDeepLinks(startFromLaunchParams);
  cleanupShortcut = await registerUnlockShortcut(async () => {
    settings.value.locked = false;
    settings.value.form.captionPinned = false;
    await setOverlayLocked(false);
  });
  const launched = await getLaunchDeepLink();
  const params = launched?.token ? launched : parseLaunchParams();
  if (params.token) await startFromLaunchParams(params);
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
        @close="stopStandalone"
      />
    </div>

    <p v-if="errorMessage" class="desktop-overlay-error">{{ errorMessage }}</p>
  </main>
</template>
