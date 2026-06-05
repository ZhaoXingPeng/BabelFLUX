<script setup lang="ts">
import type { QuickFormState, ReportMetric, RuntimeState, SourceOption, TranscriptPair, WorkspaceTile } from "./types";
import type { SourceSyncState } from "../../types/events";

defineProps<{
  form: QuickFormState;
  state: RuntimeState;
  source: SourceOption;
  runtimeStatus: string;
  wsConnected: boolean;
  sourceSyncState: SourceSyncState;
  errorMessage: string | null;
  displayModes: string[];
  selectedDisplayMode: string;
  selectedDisplayDescription: string;
  currentPair: TranscriptPair;
  transcriptPairs: TranscriptPair[];
  workspaceTiles: WorkspaceTile[];
  reportMetrics: ReportMetric[];
}>();

const emit = defineEmits<{
  pause: [];
  resume: [];
  end: [];
  reset: [];
  updateDisplayMode: [mode: string];
}>();
</script>

<template>
  <section class="grid gap-4">
    <div class="rounded-lg border border-[#d7ddd8] bg-white p-4">
      <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p class="text-xs text-[#607064]">
            {{ form.name }} · {{ form.sourceLanguage }} -> {{ form.targetLanguage }}
          </p>
          <h2 class="mt-1 text-xl font-bold">快速同传工作台</h2>
        </div>
        <div class="flex flex-wrap gap-2">
          <span class="status-pill">{{ runtimeStatus }}</span>
          <span class="status-pill">{{ wsConnected ? "WebSocket 已连接" : "WebSocket 未连接" }}</span>
          <span class="status-pill">{{ sourceSyncState.status }} · {{ sourceSyncState.lagMs }}ms</span>
        </div>
      </div>

      <p v-if="errorMessage" class="mt-3 rounded-md border border-[#d96b6b] bg-[#fff0f0] px-3 py-2 text-sm text-[#a13d3d]">
        {{ errorMessage }}
      </p>

      <div class="mt-4 flex flex-wrap gap-2">
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
          结束
        </button>
        <button v-if="state === 'report'" class="secondary-button compact-button" type="button" @click="emit('reset')">
          新建同传
        </button>
      </div>
    </div>

    <div class="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.75fr)]">
      <section class="rounded-lg border border-[#d7ddd8] bg-white p-4">
        <div class="media-stage">
          <div>
            <p class="text-sm text-[#d8e0da]">{{ source.label }} · {{ form.modelProfile }}</p>
            <p class="mt-2 text-2xl font-bold text-white">视频 / 音频展示区</p>
            <p class="mt-3 max-w-xl text-sm leading-6 text-[#bec9c2]">
              {{ currentPair.source }}
            </p>
          </div>
          <div class="media-caption">
            {{ currentPair.translation }}
          </div>
        </div>

        <div class="mt-4 grid gap-3 md:grid-cols-2">
          <div v-for="tile in workspaceTiles" :key="tile.label" class="workspace-tile">
            <p class="tile-label">{{ tile.label }}</p>
            <p class="tile-text">{{ tile.value }}</p>
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

        <div class="mt-3 grid grid-cols-2 gap-2">
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
          <article v-for="pair in transcriptPairs" :key="`${pair.time}-${pair.source}`" class="transcript-row">
            <div class="flex items-center justify-between gap-2">
              <span class="text-xs text-[#69776e]">{{ pair.time }}</span>
              <span class="rounded-md bg-[#eef1ee] px-2 py-1 text-xs text-[#526057]">{{ pair.state }}</span>
            </div>
            <p class="mt-2 text-sm leading-6 text-[#4a5a50]">{{ pair.source }}</p>
            <p class="mt-2 text-base font-semibold leading-7 text-[#17212b]">{{ pair.translation }}</p>
          </article>
        </div>
      </section>
    </div>

    <section v-if="state === 'report'" class="rounded-lg border border-[#d7ddd8] bg-white p-4">
      <div class="flex items-center justify-between gap-3">
        <h3 class="font-bold">会议报告</h3>
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
