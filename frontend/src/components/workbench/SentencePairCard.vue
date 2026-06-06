<script setup lang="ts">
import type { TranscriptPair } from "../workflow/types";
import StreamLine from "./StreamLine.vue";

defineProps<{
  pair: TranscriptPair;
}>();

// 把内部字幕状态映射成可读中文，贴近真实"识别中 → 定稿 → 校正"的同传节奏。
const STATE_LABELS: Record<string, string> = {
  partial: "识别中",
  final: "已定稿",
  revised: "已修正"
};
</script>

<template>
  <article
    class="sentence-pair-card"
    :class="{ active: pair.isActive, revised: pair.state === 'revised' }"
    :data-active="pair.isActive ? 'true' : undefined"
    :data-pair-key="pair.segmentId ?? pair.time"
    :data-revision-pulse="pair.state === 'revised' ? 'true' : undefined"
  >
    <header>
      <time>{{ pair.time }}</time>
      <span>{{ STATE_LABELS[pair.state] ?? pair.state }}</span>
    </header>
    <span v-if="pair.state === 'revised'" class="revision-float" aria-hidden="true">↺ 已校正</span>
    <p class="source-line"><StreamLine :text="pair.source" :state="pair.state" /></p>
    <p class="translation-line"><StreamLine :text="pair.translation" :state="pair.state" strong /></p>
    <div v-if="pair.originalTranslation || pair.revisionReason" class="revision-block">
      <p v-if="pair.originalTranslation" class="old-translation">
        <span>原译</span>
        <del>{{ pair.originalTranslation }}</del>
      </p>
      <p v-if="pair.revisionReason">
        <span>原因</span>
        <strong>{{ pair.revisionReason }}</strong>
      </p>
    </div>
  </article>
</template>
