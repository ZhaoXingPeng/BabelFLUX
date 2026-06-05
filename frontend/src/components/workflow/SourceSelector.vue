<script setup lang="ts">
import type { SourceOption } from "./types";

defineProps<{
  sources: SourceOption[];
  selectedKey: string;
}>();

const emit = defineEmits<{
  select: [source: SourceOption];
}>();
</script>

<template>
  <div class="mt-2 grid gap-2">
    <button
      v-for="source in sources"
      :key="source.key"
      class="source-card"
      :class="{ selected: selectedKey === source.key, disabled: source.disabled }"
      :disabled="source.disabled"
      type="button"
      @click="emit('select', source)"
    >
      <span class="font-bold">{{ source.label }}</span>
      <span>{{ source.channel }}</span>
      <strong>{{ source.availability === "web" ? "Web" : "桌面端" }}</strong>
    </button>
  </div>
</template>
