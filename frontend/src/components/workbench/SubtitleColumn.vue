<script setup lang="ts">
import type { TranscriptPair } from "../workflow/types";
import ModeSwitch from "./ModeSwitch.vue";
import SentencePairView from "./SentencePairView.vue";
import SplitParallelView from "./SplitParallelView.vue";

defineProps<{
  displayModes: string[];
  selectedDisplayMode: string;
  selectedDisplayDescription: string;
  pairs: TranscriptPair[];
}>();

const emit = defineEmits<{
  updateDisplayMode: [mode: string];
}>();
</script>

<template>
  <aside class="subtitle-column">
    <header class="subtitle-column-header">
      <div>
        <p>Live transcript</p>
        <h2>同传显示</h2>
        <span>{{ selectedDisplayDescription }}</span>
      </div>
      <ModeSwitch :modes="displayModes" :selected="selectedDisplayMode" @update="emit('updateDisplayMode', $event)" />
    </header>

    <SplitParallelView v-if="selectedDisplayMode === '分区对照'" :pairs="pairs" />
    <SentencePairView v-else :pairs="pairs" />
  </aside>
</template>
