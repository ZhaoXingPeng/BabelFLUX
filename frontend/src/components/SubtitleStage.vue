<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useSessionStore } from "../stores/session";

const sessionStore = useSessionStore();
const { activeSourceSegment, activeTranslationSegment, revisions, sourceSegments, translationSegments } =
  storeToRefs(sessionStore);
</script>

<template>
  <section class="min-h-[620px] rounded-[2.5rem] bg-ink p-6 text-white shadow-2xl shadow-ink/30">
    <div class="flex items-center justify-between">
      <div>
        <p class="text-xs font-semibold uppercase tracking-[0.35em] text-tide">Subtitle Preview</p>
        <h2 class="mt-2 font-display text-2xl font-black">实时字幕同传工作台</h2>
      </div>
      <span class="rounded-full bg-white/10 px-4 py-2 text-xs text-white/75">Mock Stream</span>
    </div>

    <div class="mt-8 grid min-h-[300px] place-items-end rounded-[2rem] bg-gradient-to-br from-[#122b40] via-[#18344b] to-[#0b1722] p-8">
      <div class="w-full max-w-3xl rounded-[1.5rem] border border-white/10 bg-black/35 p-6 text-center backdrop-blur">
        <p class="text-xl font-semibold leading-relaxed text-white">
          {{ activeSourceSegment?.text ?? "等待源语言字幕..." }}
        </p>
        <p class="mt-4 text-3xl font-black leading-relaxed text-tide">
          {{ activeTranslationSegment?.text ?? "等待中文字幕..." }}
        </p>
      </div>
    </div>

    <div class="mt-6 grid gap-4 lg:grid-cols-2">
      <div class="rounded-3xl bg-white/8 p-5">
        <h3 class="font-semibold text-white">双语记录</h3>
        <div class="mt-4 max-h-52 space-y-3 overflow-auto pr-2 text-sm">
          <div
            v-for="segment in sourceSegments"
            :key="segment.segmentId"
            class="rounded-2xl bg-white/8 p-3"
          >
            <p class="text-white/55">{{ segment.startMs }}ms - {{ segment.endMs }}ms · {{ segment.status }}</p>
            <p class="mt-1">{{ segment.text }}</p>
          </div>
          <p v-if="sourceSegments.length === 0" class="text-white/45">暂无源语言记录</p>
        </div>
      </div>

      <div class="rounded-3xl bg-white/8 p-5">
        <h3 class="font-semibold text-white">中文翻译与纠偏</h3>
        <div class="mt-4 max-h-52 space-y-3 overflow-auto pr-2 text-sm">
          <div
            v-for="segment in translationSegments"
            :key="segment.segmentId"
            class="rounded-2xl bg-white/8 p-3"
          >
            <p class="text-white/55">{{ segment.startMs }}ms - {{ segment.endMs }}ms · {{ segment.status }}</p>
            <p class="mt-1">{{ segment.text }}</p>
          </div>
          <p v-if="translationSegments.length === 0" class="text-white/45">暂无翻译记录</p>
        </div>

        <div class="mt-5 rounded-2xl border border-tide/30 bg-tide/10 p-4">
          <p class="text-sm font-semibold text-tide">最近纠偏</p>
          <p v-if="revisions.length === 0" class="mt-2 text-sm text-white/55">暂无 RevisionEvent</p>
          <p v-else class="mt-2 text-sm text-white/75">
            {{ revisions[0].reason }}：{{ revisions[0].beforeText }} -> {{ revisions[0].afterText }}
          </p>
        </div>
      </div>
    </div>
  </section>
</template>
