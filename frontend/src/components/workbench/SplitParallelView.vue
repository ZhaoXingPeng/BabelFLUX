<script setup lang="ts">
import type { TranscriptPair } from "../workflow/types";

defineProps<{
  pairs: TranscriptPair[];
}>();
</script>

<template>
  <div class="split-parallel-view">
    <section>
      <header>
        <span>Source</span>
        <strong>源文 EN</strong>
      </header>
      <div class="stream-list">
        <article v-for="pair in pairs" :key="`src-${pair.segmentId ?? pair.time}`" :class="{ active: pair.isActive }">
          <time>{{ pair.time }}</time>
          <p>{{ pair.source }}</p>
        </article>
      </div>
    </section>
    <section>
      <header>
        <span>Translation</span>
        <strong>译文 ZH</strong>
      </header>
      <div class="stream-list">
        <article
          v-for="pair in pairs"
          :key="`dst-${pair.segmentId ?? pair.time}`"
          :class="{ active: pair.isActive, revised: pair.state === 'revised' }"
        >
          <time>{{ pair.time }}</time>
          <p>{{ pair.translation }}</p>
          <small v-if="pair.revisionReason">{{ pair.revisionReason }}</small>
        </article>
      </div>
    </section>
  </div>
</template>
