<script setup lang="ts">
import type { QuickFormState, ReportMetric, RuntimeState, SourceOption, TranscriptPair } from "./types";
import type { SourceSyncState } from "../../types/events";

defineProps<{
  form: QuickFormState;
  state: RuntimeState;
  source: SourceOption;
  runtimeStatus: string;
  wsConnected: boolean;
  sourceSyncState: SourceSyncState;
  mediaUrl: string | null;
  audioUrl: string | null;
  errorMessage: string | null;
  displayModes: string[];
  selectedDisplayMode: string;
  selectedDisplayDescription: string;
  currentPair: TranscriptPair;
  transcriptPairs: TranscriptPair[];
  reportMetrics: ReportMetric[];
}>();

const emit = defineEmits<{
  pause: [];
  resume: [];
  end: [];
  reset: [];
  updateDisplayMode: [mode: string];
  syncPlayback: [currentTimeSeconds: number];
}>();

function emitPlaybackTime(event: Event) {
  emit("syncPlayback", (event.target as HTMLMediaElement).currentTime);
}
</script>

<template>
  <section class="grid gap-4">
    <div class="workspace-header rounded-lg border border-[#d7ddd8] bg-white p-4">
      <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p class="text-xs text-[#607064]">
            {{ form.name }} · {{ form.sourceLanguage }} -> {{ form.targetLanguage }}
          </p>
          <h2 class="mt-1 text-xl font-bold">同传中</h2>
        </div>
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div class="flex flex-wrap gap-2">
            <span class="status-pill">{{ runtimeStatus }}</span>
            <span class="status-pill">{{ wsConnected ? "已连接" : "未连接" }}</span>
            <span class="status-pill">{{ sourceSyncState.status }} · {{ sourceSyncState.lagMs }}ms</span>
          </div>
          <div class="flex flex-wrap gap-2">
            <button v-if="state === 'running'" class="secondary-button compact-button" type="button" @click="emit('pause')">
              暂停
            </button>
            <button v-if="state === 'paused'" class="primary-button compact-button" type="button" @click="emit('resume')">
              继续
            </button>
            <button
              v-if="state !== 'setup' && state !== 'report'"
              class="danger-button compact-button"
              type="button"
              @click="emit('end')"
            >
              结束同传
            </button>
            <button v-if="state === 'report'" class="secondary-button compact-button" type="button" @click="emit('reset')">
              新建同传
            </button>
          </div>
        </div>
      </div>

      <p v-if="errorMessage" class="mt-3 rounded-md border border-[#d96b6b] bg-[#fff0f0] px-3 py-2 text-sm text-[#a13d3d]">
        {{ errorMessage }}
      </p>

    </div>

    <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(380px,0.78fr)]">
      <section class="rounded-lg border border-[#d7ddd8] bg-white p-4">
        <div class="media-stage">
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
              <span>voice.m4a</span>
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
          <div v-else>
            <p class="text-sm text-[#d8e0da]">{{ source.label }} · {{ form.modelProfile }}</p>
            <p class="mt-2 text-2xl font-bold text-white">原始视频 / 音频</p>
            <p class="mt-3 max-w-xl text-sm leading-6 text-[#bec9c2]">
              {{ currentPair.source }}
            </p>
          </div>
          <div class="media-caption" :class="{ floating: selectedDisplayMode === '悬浮字幕' }">
            {{ currentPair.translation }}
          </div>
        </div>
      </section>

      <section class="rounded-lg border border-[#d7ddd8] bg-white p-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="font-bold">同传显示</h3>
            <p class="mt-1 text-xs text-[#607064]">{{ selectedDisplayDescription }}</p>
          </div>
          <span class="rounded-md bg-[#fff4df] px-2 py-1 text-xs text-[#7a4c00]">{{ selectedDisplayMode }}</span>
        </div>

        <div class="mt-3 grid grid-cols-3 gap-2">
          <button
            v-for="mode in displayModes"
            :key="mode"
            class="rounded-md border px-2 py-2 text-sm"
            :class="
              selectedDisplayMode === mode
                ? 'border-[#245eaa] bg-[#e9f1ff] text-[#17457c]'
                : 'border-[#d7ddd8] bg-white text-[#4a5a50]'
            "
            type="button"
            @click="emit('updateDisplayMode', mode)"
          >
            {{ mode }}
          </button>
        </div>

        <div class="mt-4 max-h-[520px] space-y-3 overflow-auto pr-1">
          <article
            v-for="pair in transcriptPairs"
            :key="`${pair.time}-${pair.source}`"
            class="transcript-row"
            :class="{
              compact: selectedDisplayMode === '分区对照',
              active: pair.isActive,
              revised: pair.state === 'revised'
            }"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="text-xs text-[#69776e]">{{ pair.time }}</span>
              <div class="flex flex-wrap justify-end gap-1">
                <span class="rounded-md bg-[#eef1ee] px-2 py-1 text-xs text-[#526057]">{{ pair.state }}</span>
                <span v-if="pair.state === 'revised'" class="rounded-md bg-[#e7f4ec] px-2 py-1 text-xs font-bold text-[#12462f]">
                  已修正
                </span>
              </div>
            </div>
            <div
              class="mt-2 grid gap-2"
              :class="selectedDisplayMode === '分区对照' ? 'md:grid-cols-2' : 'grid-cols-1'"
            >
              <p class="text-sm leading-6 text-[#4a5a50]">{{ pair.source }}</p>
              <p class="text-base font-semibold leading-7 text-[#17212b]">{{ pair.translation }}</p>
            </div>
            <p v-if="pair.originalTranslation" class="mt-2 text-xs leading-5 text-[#69776e]">
              原译：{{ pair.originalTranslation }}
            </p>
            <p v-if="pair.revisionReason" class="mt-1 text-xs leading-5 text-[#1c7c54]">
              {{ pair.revisionReason }}
            </p>
          </article>
        </div>
      </section>
    </div>

    <section v-if="state === 'report'" class="rounded-lg border border-[#d7ddd8] bg-white p-4">
      <div class="flex items-center justify-between gap-3">
        <h3 class="font-bold">同传报告</h3>
        <div class="flex gap-2">
          <button class="secondary-button compact-button" type="button">TXT</button>
          <button class="secondary-button compact-button" type="button">SRT</button>
          <button class="secondary-button compact-button" type="button">MD</button>
        </div>
      </div>
      <div class="mt-3 grid gap-3 md:grid-cols-4">
        <div v-for="metric in reportMetrics" :key="metric.label" class="report-metric">
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
        </div>
      </div>
    </section>
  </section>
</template>
