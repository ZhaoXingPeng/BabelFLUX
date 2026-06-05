<script setup lang="ts">
defineProps<{
  text: string;
  state?: string;
  strong?: boolean;
}>();
</script>

<template>
  <span class="stream-line" :class="{ partial: state === 'partial', strong }">
    <span v-for="(part, index) in text.split('')" :key="`${part}-${index}`" class="stream-token">{{ part }}</span>
    <span v-if="state === 'partial'" class="stream-caret" aria-hidden="true">▍</span>
  </span>
</template>
