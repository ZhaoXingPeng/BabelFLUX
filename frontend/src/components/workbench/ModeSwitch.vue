<script setup lang="ts">
defineProps<{
  modes: string[];
  selected: string;
}>();

const emit = defineEmits<{
  update: [mode: string];
}>();
</script>

<template>
  <div class="mode-switch" role="tablist" aria-label="字幕显示模式">
    <button
      v-for="mode in modes"
      :key="mode"
      type="button"
      role="tab"
      :aria-selected="selected === mode"
      :class="{ active: selected === mode }"
      @click="emit('update', mode)"
    >
      {{ mode }}
    </button>
  </div>
</template>
