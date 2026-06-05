<script setup lang="ts">
import type { ProductMode, ProductModeOption } from "./types";

defineProps<{
  modes: ProductModeOption[];
  selectedMode: ProductMode;
}>();

const emit = defineEmits<{
  select: [mode: ProductMode];
}>();
</script>

<template>
  <div class="grid gap-2 sm:grid-cols-2">
    <button
      v-for="mode in modes"
      :key="mode.key"
      class="min-w-[180px] rounded-lg border px-4 py-3 text-left transition"
      :class="
        selectedMode === mode.key
          ? 'border-[#1c7c54] bg-[#e7f4ec] text-[#12462f]'
          : 'border-[#d7ddd8] bg-white text-[#4a5a50] hover:border-[#8bb89b]'
      "
      type="button"
      @click="emit('select', mode.key)"
    >
      <span class="block text-sm font-bold">{{ mode.label }}</span>
      <span class="mt-1 block text-xs">{{ mode.description }}</span>
    </button>
  </div>
</template>
