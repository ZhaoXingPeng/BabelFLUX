<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import type { SourceSyncState } from "../../types/events";
import Icon from "../icons/Icon.vue";
import type {
  DesktopLaunchState,
  FloatingFormState,
  QuickFormState,
  RuntimeState,
  SourceOption,
  TranscriptPair
} from "../workflow/types";
import FloatingCaption from "./FloatingCaption.vue";

const props = defineProps<{
  form: QuickFormState;
  floatingForm: FloatingFormState;
  state: RuntimeState;
  source: SourceOption;
  runtimeStatus: string;
  wsConnected: boolean;
  sourceSyncState: SourceSyncState;
  mediaUrl: string | null;
  audioUrl: string | null;
  mediaKind: "video" | "audio";
  currentPair: TranscriptPair;
  desktopLaunchState: DesktopLaunchState;
  desktopLaunchMessage: string;
  selectedDisplayMode: string;
  ttsMuted: boolean;
  ttsVolume: number;
  ttsErrorMessage: string | null;
}>();

const emit = defineEmits<{
  end: [];
  reset: [];
  openDesktop: [];
  toggleFloatingCaptions: [];
  mediaReady: [element: HTMLMediaElement | null];
  syncPlayback: [currentTimeSeconds: number];
  playbackPause: [];
  playbackPlay: [];
  ended: [];
  updateTtsMuted: [muted: boolean];
  updateTtsVolume: [volume: number];
}>();

const videoEl = ref<HTMLVideoElement | null>(null);
const audioEl = ref<HTMLAudioElement | null>(null);
const suppressPauseEvent = ref(false);
const userPaused = ref(false);
let pausingFromWatch = false;
let lastPauseIntentAt = Number.NEGATIVE_INFINITY;
let lastPlayIntentAt = Number.NEGATIVE_INFINITY;
let initializedMediaElement: HTMLMediaElement | null = null;

const PLAYBACK_INTENT_DEBOUNCE_MS = 160;
const DEFAULT_MEDIA_VOLUME = 0.5;

function currentMediaElement() {
  return props.mediaKind === "video" ? videoEl.value : audioEl.value;
}

function isMediaElementCaptureSource() {
  return props.source.key === "video-file" || props.source.key === "audio-file";
}

function canAutoPlay() {
  const mediaElementReady =
    props.sourceSyncState.status === "ready" ||
    props.sourceSyncState.message.startsWith("媒体同步") ||
    props.sourceSyncState.message === "会话已继续";
  return props.state === "running" && (!isMediaElementCaptureSource() || mediaElementReady);
}

async function emitMediaElement() {
  await nextTick();
  const element = currentMediaElement();
  applyMediaDefaults(element);
  emit("mediaReady", element);
}

async function tryAutoPlay() {
  await nextTick();
  const element = currentMediaElement();
  if (!element || !canAutoPlay() || !element.paused || userPaused.value) return;
  try {
    await element.play();
  } catch {
    // Browsers may block autoplay with sound. Controls remain available for a manual start.
  }
}

function pauseMedia(silent = false) {
  const element = currentMediaElement();
  if (element && !element.paused) {
    suppressPauseEvent.value = silent;
    pausingFromWatch = silent;
    element.pause();
  }
}

function emitPlaybackTime(event: Event) {
  emit("syncPlayback", (event.target as HTMLMediaElement).currentTime);
}

function handlePause(event: Event) {
  if (suppressPauseEvent.value) {
    suppressPauseEvent.value = false;
    pausingFromWatch = false;
    return;
  }
  if (pausingFromWatch) {
    pausingFromWatch = false;
    return;
  }
  const element = event.target as HTMLMediaElement;
  const now = window.performance.now();
  if (!element.ended && now - lastPauseIntentAt > PLAYBACK_INTENT_DEBOUNCE_MS) {
    lastPauseIntentAt = now;
    userPaused.value = true;
    emit("playbackPause");
  }
}

function applyMediaDefaults(element: HTMLMediaElement | null) {
  if (!element || initializedMediaElement === element) return;
  element.volume = DEFAULT_MEDIA_VOLUME;
  initializedMediaElement = element;
}

function handlePlay() {
  const now = window.performance.now();
  if (!userPaused.value && now - lastPlayIntentAt <= PLAYBACK_INTENT_DEBOUNCE_MS) return;
  lastPlayIntentAt = now;
  userPaused.value = false;
  emit("playbackPlay");
}

function handleTtsVolumeInput(event: Event) {
  emit("updateTtsVolume", Number((event.target as HTMLInputElement).value));
}

function handleLoadedMetadata() {
  const element = currentMediaElement();
  applyMediaDefaults(element);
  void emitMediaElement();
  void tryAutoPlay();
}

watch(
  () => [
    props.state,
    props.mediaUrl,
    props.audioUrl,
    props.mediaKind,
    props.source.key
  ],
  (values, oldValues) => {
    const [state, mediaUrl, audioUrl, mediaKind, sourceKey] = values;
    const [oldState, oldMediaUrl, oldAudioUrl, oldMediaKind, oldSourceKey] = oldValues ?? [];
    const mediaChanged =
      mediaUrl !== oldMediaUrl ||
      audioUrl !== oldAudioUrl ||
      mediaKind !== oldMediaKind ||
      sourceKey !== oldSourceKey;
    if (mediaChanged || state === "setup" || state === "report" || oldState === "setup") {
      userPaused.value = false;
      initializedMediaElement = null;
    }
    void emitMediaElement();
    if (state === "running") {
      if (canAutoPlay()) void tryAutoPlay();
    } else {
      pauseMedia(true);
    }
  },
  { flush: "post", immediate: true }
);
</script>

<template>
  <section class="media-panel">
    <header class="media-panel-header">
      <div>
        <p>{{ form.name }}</p>
        <h1>{{ form.sourceLanguage }} -> {{ form.targetLanguage }}</h1>
      </div>
      <div class="runtime-cluster">
        <span :class="['sync-dot', sourceSyncState.status]" />
        <span>{{ sourceSyncState.status }} · {{ sourceSyncState.lagMs }}ms</span>
        <span>{{ wsConnected ? "已连接" : "未连接" }}</span>
      </div>
    </header>

    <div class="media-screen">
      <div v-if="mediaKind === 'video' && mediaUrl" class="media-player-stack">
        <video
          ref="videoEl"
          class="fixture-video"
          :src="mediaUrl"
          controls
          playsinline
          autoplay
          preload="metadata"
          data-testid="fixture-video"
          @loadedmetadata="handleLoadedMetadata"
          @play="handlePlay"
          @pause="handlePause"
          @timeupdate="emitPlaybackTime"
          @seeked="emitPlaybackTime"
          @ended="emit('ended')"
        />
      </div>
      <div v-else-if="mediaKind === 'audio' && audioUrl" class="audio-stage">
        <div>
          <p>{{ source.label }} · {{ form.modelProfile }}</p>
          <strong>音频同传</strong>
          <span>{{ currentPair.source }}</span>
        </div>
        <audio
          ref="audioEl"
          class="fixture-audio"
          :src="audioUrl"
          controls
          autoplay
          preload="metadata"
          data-testid="fixture-audio"
          @loadedmetadata="handleLoadedMetadata"
          @play="handlePlay"
          @pause="handlePause"
          @timeupdate="emitPlaybackTime"
          @seeked="emitPlaybackTime"
          @ended="emit('ended')"
        />
      </div>
      <div v-else class="empty-media">
        <p>{{ source.label }} · {{ form.modelProfile }}</p>
        <strong>等待音源输入</strong>
        <span>{{ currentPair.source }}</span>
      </div>

      <FloatingCaption
        v-if="selectedDisplayMode === '悬浮字幕'"
        :pair="currentPair"
        :form="floatingForm"
        @close="emit('toggleFloatingCaptions')"
      />
    </div>

    <footer class="media-panel-footer">
      <div class="media-meta">
        <span>{{ runtimeStatus }}</span>
        <span>{{ source.channel }}</span>
        <span>{{ sourceSyncState.message }}</span>
        <span v-if="ttsErrorMessage">{{ ttsErrorMessage }}</span>
        <span v-if="desktopLaunchState !== 'idle'">{{ desktopLaunchMessage }}</span>
      </div>
      <div class="media-actions">
        <div v-if="form.ttsEnabled" class="tts-controls">
          <button
            class="stage-button icon-stage-button"
            type="button"
            :aria-label="ttsMuted ? '取消静音语音播报' : '静音语音播报'"
            :title="ttsMuted ? '取消静音语音播报' : '静音语音播报'"
            @click="emit('updateTtsMuted', !ttsMuted)"
          >
            <Icon :name="ttsMuted ? 'volume-x' : 'volume-2'" :size="17" />
          </button>
          <input
            class="tts-volume"
            type="range"
            min="0"
            max="1"
            step="0.05"
            :value="ttsVolume"
            aria-label="语音播报音量"
            @input="handleTtsVolumeInput"
          />
        </div>
        <button
          class="stage-button icon-stage-button"
          type="button"
          :disabled="desktopLaunchState === 'launching'"
          :aria-label="desktopLaunchState === 'launching' ? '正在唤起桌面悬浮窗' : '投送桌面悬浮窗'"
          :title="desktopLaunchState === 'launching' ? '正在唤起桌面悬浮窗' : '投送桌面悬浮窗'"
          @click="emit('openDesktop')"
        >
          <Icon name="monitor-up" :size="18" />
        </button>
        <button
          v-if="state !== 'report'"
          class="stage-button icon-stage-button"
          type="button"
          :class="{ active: selectedDisplayMode === '悬浮字幕' }"
          :aria-label="selectedDisplayMode === '悬浮字幕' ? '展开字幕栏' : '切换悬浮字幕'"
          :title="selectedDisplayMode === '悬浮字幕' ? '展开字幕栏' : '切换悬浮字幕'"
          @click="emit('toggleFloatingCaptions')"
        >
          <Icon name="picture-in-picture-2" :size="18" />
        </button>
        <button
          v-if="state !== 'setup' && state !== 'report'"
          class="stage-button icon-stage-button danger"
          type="button"
          aria-label="结束同传"
          title="结束同传"
          @click="emit('end')"
        >
          <Icon name="square" :size="15" />
        </button>
        <button
          v-if="state === 'report'"
          class="stage-button icon-stage-button"
          type="button"
          aria-label="新建同传"
          title="新建同传"
          @click="emit('reset')"
        >
          <Icon name="plus" :size="18" />
        </button>
      </div>
    </footer>
  </section>
</template>
