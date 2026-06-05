<script setup lang="ts">
import type { FloatingFormState, RuntimeState, SourceOption, TranscriptPair } from "./types";

defineProps<{
  form: FloatingFormState;
  state: RuntimeState;
  source: SourceOption;
  statusLabel: string;
  currentPair: TranscriptPair;
}>();

const emit = defineEmits<{
  pause: [];
  resume: [];
  end: [];
  reset: [];
}>();
</script>

<template>
  <section class="relative min-h-[680px] rounded-lg border border-[#d7ddd8] bg-[#dfe4df] p-4">
    <div class="grid h-full grid-rows-[auto_minmax(0,1fr)] gap-4">
      <div class="rounded-lg border border-[#c9d1cb] bg-white p-4">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p class="text-xs text-[#607064]">{{ source.label }} · {{ form.modelProfile }}</p>
            <h2 class="mt-1 text-xl font-bold">悬浮字幕运行窗</h2>
          </div>
          <div class="flex flex-wrap gap-2">
            <button class="secondary-button compact-button" type="button">锁定</button>
            <button class="secondary-button compact-button" type="button">A-</button>
            <button class="secondary-button compact-button" type="button">A+</button>
            <button class="secondary-button compact-button" type="button">设置</button>
            <button
              v-if="state !== 'setup' && state !== 'report'"
              class="danger-button compact-button"
              type="button"
              @click="emit('end')"
            >
              关闭
            </button>
          </div>
        </div>
      </div>

      <div class="relative rounded-lg border border-[#c9d1cb] bg-[#f8faf8] p-4">
        <div class="grid h-full place-items-center rounded-lg border border-dashed border-[#b7c1ba] bg-white">
          <div class="text-center">
            <p class="text-sm font-semibold text-[#607064]">浏览器字幕层</p>
            <p class="mt-2 text-lg font-bold text-[#17212b]">{{ form.style }} · {{ form.size }}</p>
          </div>
        </div>

        <div class="floating-window">
          <div class="flex items-center justify-between gap-3 border-b border-white/10 pb-2">
            <span>{{ statusLabel }}</span>
            <span>{{ form.sourceLanguage }} -> {{ form.targetLanguage }}</span>
          </div>
          <p class="mt-4 text-sm leading-6 text-white/72">{{ currentPair.source }}</p>
          <p class="mt-2 text-xl font-bold leading-8 text-white">{{ currentPair.translation }}</p>
          <div class="mt-4 flex justify-center gap-2">
            <button v-if="state === 'running'" class="floating-button" type="button" @click="emit('pause')">
              暂停
            </button>
            <button v-if="state === 'paused'" class="floating-button" type="button" @click="emit('resume')">
              继续
            </button>
            <button
              v-if="state !== 'setup' && state !== 'report'"
              class="floating-button danger"
              type="button"
              @click="emit('end')"
            >
              结束
            </button>
          </div>
        </div>
      </div>
    </div>

    <section v-if="state === 'report'" class="absolute inset-x-4 bottom-4 rounded-lg border border-[#d7ddd8] bg-white p-4">
      <div class="flex items-center justify-between gap-3">
        <div>
          <h3 class="font-bold">字幕记录</h3>
          <p class="mt-2 text-sm text-[#4a5a50]">已生成转写、译文、修正记录和导出入口。</p>
        </div>
        <button class="secondary-button compact-button" type="button" @click="emit('reset')">
          新建字幕
        </button>
      </div>
    </section>
  </section>
</template>
