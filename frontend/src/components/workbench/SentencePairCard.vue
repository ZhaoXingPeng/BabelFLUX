<script setup lang="ts">
import type { TranscriptPair } from "../workflow/types";
import StreamLine from "./StreamLine.vue";

defineProps<{
  pair: TranscriptPair;
}>();
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
      <span>{{ pair.state === "revised" ? "已修正" : pair.state }}</span>
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
