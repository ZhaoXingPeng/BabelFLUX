<script setup lang="ts">
import type { TranscriptPair } from "../workflow/types";

defineProps<{
  pair: TranscriptPair;
}>();
</script>

<template>
  <article
    class="sentence-pair-card"
    :class="{ active: pair.isActive, revised: pair.state === 'revised' }"
    :data-revision-pulse="pair.state === 'revised' ? 'true' : undefined"
  >
    <header>
      <time>{{ pair.time }}</time>
      <span>{{ pair.state === "revised" ? "已修正" : pair.state }}</span>
    </header>
    <p class="source-line">{{ pair.source }}</p>
    <p class="translation-line">{{ pair.translation }}</p>
    <div v-if="pair.originalTranslation || pair.revisionReason" class="revision-block">
      <p v-if="pair.originalTranslation">
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
