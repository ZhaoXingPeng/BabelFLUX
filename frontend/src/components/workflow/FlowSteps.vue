<script setup lang="ts">
import type { RuntimeState } from "./types";

const props = defineProps<{
  state: RuntimeState;
  middleLabel: string;
  reportLabel: string;
}>();

function isRuntimeActive() {
  return props.state === "connecting" || props.state === "running" || props.state === "paused";
}
</script>

<template>
  <div class="grid grid-cols-3 gap-2">
    <div class="flow-step" :class="{ active: state === 'setup' }">配置</div>
    <div class="flow-step" :class="{ active: isRuntimeActive() }">{{ middleLabel }}</div>
    <div class="flow-step" :class="{ active: state === 'report' }">{{ reportLabel }}</div>
  </div>
</template>
