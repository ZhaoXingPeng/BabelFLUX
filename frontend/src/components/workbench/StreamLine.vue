<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  text: string;
  state?: string;
  strong?: boolean;
}>();

const tokens = computed(() => props.text.split(/(\s+)/).filter((token) => token.length > 0));

function isSpace(token: string) {
  return /^\s+$/.test(token);
}
</script>

<template>
  <span class="stream-line" :class="{ partial: state === 'partial', strong }">
    <template v-for="(part, index) in tokens" :key="`${part}-${index}`">
      <span v-if="isSpace(part)" class="stream-space">{{ part }}</span>
      <span v-else class="stream-token">{{ part }}</span>
    </template>
    <span v-if="state === 'partial'" class="stream-caret" aria-hidden="true">▍</span>
  </span>
</template>
