<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import FloatingCaption from "@frontend/components/workbench/FloatingCaption.vue";
import type { SourceSyncState, ServerEvent } from "@frontend/types/events";
import type { TranscriptPair } from "@frontend/types/workflow";
import { claimHandoffToken, connectDesktopSession } from "./api/sessionBridge";
import { listenForDeepLinks, parseLaunchParams, type LaunchParams } from "./launcherBridge";
import { defaultOverlaySettings, loadOverlaySettings, saveOverlaySettings, type OverlaySettings } from "./localSettings";
import { registerUnlockShortcut, setOverlayLocked } from "./overlayWindow";

const settings = ref<OverlaySettings>(loadOverlaySettings());
const pair = ref<TranscriptPair>({
  time: "00:00",
  source: "Waiting for desktop handoff.",
  translation: "等待 Web 工作台投送字幕。",
  state: "partial",
  isActive: true
});
const status = ref<SourceSyncState>({
  status: "listening",
  lagMs: 0,
  message: "等待 handoff token"
});
const errorMessage = ref("");
const displayMode = ref<NonNullable<LaunchParams["displayMode"]>>("bilingual");
let socket: WebSocket | null = null;
let cleanupDeepLink: (() => void) | null = null;
let cleanupShortcut: (() => void) | null = null;

const shellStyle = computed(() => ({ opacity: settings.value.opacity }));

function applyEvent(event: ServerEvent) {
  if (event.type === "session_started") {
    status.value = { status: "syncing", lagMs: 0, message: "桌面悬浮窗已接管" };
    return;
  }

  if (event.type === "source_sync_state") {
    status.value = event.state;
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

function formatTime(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

async function startFromLaunchParams(params: LaunchParams) {
  errorMessage.value = "";
  displayMode.value = params.displayMode ?? "bilingual";

  if (!params.token) {
    status.value = { status: "listening", lagMs: 0, message: "未携带 handoff token" };
    return;
  }

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

watch(
  settings,
  (value) => {
    saveOverlaySettings(value);
  },
  { deep: true }
);

watch(
  () => settings.value.form.captionPinned,
  async (pinned) => {
    settings.value.locked = pinned;
    await setOverlayLocked(pinned);
  }
);

onMounted(async () => {
  cleanupDeepLink = await listenForDeepLinks(startFromLaunchParams);
  cleanupShortcut = await registerUnlockShortcut(async () => {
    settings.value.locked = false;
    settings.value.form.captionPinned = false;
    await setOverlayLocked(false);
  });
  await startFromLaunchParams(parseLaunchParams());
});

onUnmounted(() => {
  socket?.close();
  cleanupDeepLink?.();
  cleanupShortcut?.();
});
</script>

<template>
  <main class="desktop-overlay-shell" :style="shellStyle">
    <FloatingCaption
      :pair="pair"
      :form="settings.form"
      :display-mode="displayMode"
      :locked="settings.locked"
      :status="status"
      desktop
    />
    <p v-if="errorMessage" class="desktop-overlay-error">{{ errorMessage }}</p>
  </main>
</template>
