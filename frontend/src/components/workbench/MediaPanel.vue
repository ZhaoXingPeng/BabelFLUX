<script setup lang="ts">
import type { SourceSyncState } from "../../types/events";
import type { QuickFormState, RuntimeState, SourceOption, TranscriptPair } from "../workflow/types";

defineProps<{
  form: QuickFormState;
  state: RuntimeState;
  source: SourceOption;
  runtimeStatus: string;
  wsConnected: boolean;
  sourceSyncState: SourceSyncState;
  mediaUrl: string | null;
  audioUrl: string | null;
  currentPair: TranscriptPair;
  selectedDisplayMode: string;
}>();

const emit = defineEmits<{
  pause: [];
  resume: [];
  end: [];
  reset: [];
  openSettings: [];
  openDesktop: [];
  syncPlayback: [currentTimeSeconds: number];
}>();

function emitPlaybackTime(event: Event) {
  emit("syncPlayback", (event.target as HTMLMediaElement).currentTime);
}
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
      <div v-if="mediaUrl" class="media-player-stack">
        <video
          class="fixture-video"
          :src="mediaUrl"
          controls
          playsinline
          preload="metadata"
          data-testid="fixture-video"
          @timeupdate="emitPlaybackTime"
          @seeked="emitPlaybackTime"
        />
        <div v-if="audioUrl" class="fixture-audio-row">
          <span>测试音频</span>
          <audio
            class="fixture-audio"
            :src="audioUrl"
            controls
            preload="metadata"
            data-testid="fixture-audio"
            @timeupdate="emitPlaybackTime"
            @seeked="emitPlaybackTime"
          />
        </div>
      </div>
      <div v-else class="empty-media">
        <p>{{ source.label }} · {{ form.modelProfile }}</p>
        <strong>等待音源输入</strong>
        <span>{{ currentPair.source }}</span>
      </div>

      <div class="floating-caption" :class="{ detached: selectedDisplayMode === '悬浮字幕' }">
        {{ currentPair.translation }}
      </div>
    </div>

    <footer class="media-panel-footer">
      <div class="media-meta">
        <span>{{ runtimeStatus }}</span>
        <span>{{ source.channel }}</span>
        <span>{{ sourceSyncState.message }}</span>
      </div>
      <div class="media-actions">
        <button class="stage-button" type="button" @click="emit('openSettings')">设置</button>
        <button class="stage-button" type="button" @click="emit('openDesktop')">悬浮</button>
        <button v-if="state === 'running'" class="stage-button" type="button" @click="emit('pause')">暂停</button>
        <button v-if="state === 'paused'" class="stage-button primary" type="button" @click="emit('resume')">继续</button>
        <button v-if="state !== 'setup' && state !== 'report'" class="stage-button danger" type="button" @click="emit('end')">
          结束
        </button>
        <button v-if="state === 'report'" class="stage-button" type="button" @click="emit('reset')">新建同传</button>
      </div>
    </footer>
  </section>
</template>
