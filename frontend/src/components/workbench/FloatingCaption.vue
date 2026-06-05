<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { gsap } from "gsap";
import { Draggable } from "gsap/Draggable";
import type { SourceSyncState } from "../../types/events";
import type { FloatingFormState, TranscriptPair } from "../workflow/types";

gsap.registerPlugin(Draggable);

const props = defineProps<{
  pair: TranscriptPair;
  form: FloatingFormState;
  desktop?: boolean;
  locked?: boolean;
  displayMode?: "bilingual" | "translation-only" | "floating" | "compact";
  status?: SourceSyncState;
}>();

const emit = defineEmits<{
  close: [];
}>();

const root = ref<HTMLElement | null>(null);
let drag: Draggable[] = [];

const opacity = computed(() => {
  const value = Number.parseInt(props.form.opacity, 10);
  return Number.isFinite(value) ? value / 100 : 0.9;
});

const sizeClass = computed(() => {
  const sizes: Record<string, string> = {
    小: "size-small",
    标准: "size-medium",
    大: "size-large"
  };
  return sizes[props.form.size] ?? "size-medium";
});
const isCompact = computed(() => props.displayMode === "floating" || props.displayMode === "compact");
const showSource = computed(() => !isCompact.value && props.displayMode !== "translation-only" && props.form.style !== "仅译文");

function toggleStyle() {
  props.form.style = props.form.style === "仅译文" ? "双语字幕" : "仅译文";
}

function togglePinned() {
  props.form.captionPinned = !props.form.captionPinned;
}

function setOpacity(event: Event) {
  props.form.opacity = `${(event.target as HTMLInputElement).value}%`;
}

function setSize(size: string) {
  props.form.size = size;
}

function setupDrag() {
  drag.forEach((item) => item.kill());
  drag = [];
  if (!root.value || props.form.captionPinned || props.locked || props.desktop) return;
  drag = Draggable.create(root.value, {
    type: "y",
    bounds: root.value.parentElement ?? undefined,
    onDragEnd() {
      props.form.captionOffsetY = this.y;
    }
  });
}

onMounted(setupDrag);
onUnmounted(() => drag.forEach((item) => item.kill()));

watch([() => props.form.captionPinned, () => props.locked, () => props.desktop], setupDrag);
</script>

<template>
  <section
    ref="root"
    class="floating-caption-panel"
    :class="[sizeClass, { 'desktop-overlay': desktop, locked, compact: isCompact }]"
    :data-tauri-drag-region="desktop ? true : undefined"
    :style="{ opacity, transform: `translateY(${form.captionOffsetY}px)` }"
  >
    <div v-if="!locked" class="floating-caption-toolbar">
      <span v-if="status" class="floating-caption-status">
        <span :class="['sync-dot', status.status]" />
        {{ status.status === "lagging" ? "延迟" : status.status === "missing" ? "重连" : "LIVE" }}
      </span>
      <button type="button" @click="toggleStyle">{{ form.style === "仅译文" ? "仅译文" : "源+译" }}</button>
      <button type="button" @click="togglePinned">{{ form.captionPinned ? "已固定" : "固定" }}</button>
      <button type="button" @click="setSize('小')">小</button>
      <button type="button" @click="setSize('标准')">中</button>
      <button type="button" @click="setSize('大')">大</button>
      <label>
        <span>透明度</span>
        <input type="range" min="55" max="100" step="5" :value="Number.parseInt(form.opacity, 10)" @input="setOpacity" />
      </label>
      <button type="button" aria-label="关闭悬浮字幕" @click="emit('close')">×</button>
    </div>
    <p v-if="showSource" class="floating-source">{{ pair.source }}</p>
    <p class="floating-translation">{{ pair.translation }}</p>
  </section>
</template>
