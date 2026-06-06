<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { gsap } from "gsap";
import { Draggable } from "gsap/Draggable";
import type { SourceSyncState } from "../../types/events";
import Icon from "../icons/Icon.vue";
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
let dragging = false;

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

function syncCaptionPosition() {
  if (!root.value) return;
  if (props.desktop) {
    gsap.set(root.value, { clearProps: "transform" });
    return;
  }
  gsap.set(root.value, { xPercent: -50, y: props.form.captionOffsetY });
}

function setupDrag() {
  drag.forEach((item) => item.kill());
  drag = [];
  syncCaptionPosition();
  if (!root.value || props.form.captionPinned || props.locked || props.desktop) return;
  drag = Draggable.create(root.value, {
    type: "y",
    bounds: root.value.parentElement ?? undefined,
    onDragStart() {
      dragging = true;
    },
    onDrag() {
      props.form.captionOffsetY = this.y;
    },
    onDragEnd() {
      props.form.captionOffsetY = this.y;
      dragging = false;
      syncCaptionPosition();
    }
  });
}

onMounted(setupDrag);
onUnmounted(() => drag.forEach((item) => item.kill()));

watch([() => props.form.captionPinned, () => props.locked, () => props.desktop], setupDrag);
watch(
  () => props.form.captionOffsetY,
  () => {
    if (!dragging) syncCaptionPosition();
  }
);
</script>

<template>
  <section
    ref="root"
    class="floating-caption-panel"
    :class="[sizeClass, { 'desktop-overlay': desktop, locked, compact: isCompact }]"
    :data-tauri-drag-region="desktop ? true : undefined"
    :style="{ opacity }"
  >
    <div v-if="!locked" class="floating-caption-toolbar">
      <span v-if="status" class="floating-caption-status">
        <span :class="['sync-dot', status.status]" />
        {{ status.status === "lagging" ? "延迟" : status.status === "missing" ? "重连" : "LIVE" }}
      </span>
      <button
        type="button"
        :aria-label="form.style === '仅译文' ? '显示双语字幕' : '仅显示译文'"
        :title="form.style === '仅译文' ? '显示双语字幕' : '仅显示译文'"
        @click="toggleStyle"
      >
        <Icon :name="form.style === '仅译文' ? 'type' : 'languages'" :size="15" />
      </button>
      <button
        type="button"
        :aria-label="form.captionPinned ? '取消固定悬浮字幕' : '固定悬浮字幕'"
        :title="form.captionPinned ? '取消固定悬浮字幕' : '固定悬浮字幕'"
        @click="togglePinned"
      >
        <Icon :name="form.captionPinned ? 'pin-off' : 'pin'" :size="15" />
      </button>
      <div class="floating-size-switch" role="group" aria-label="字幕字号">
        <button type="button" :class="{ active: form.size === '小' }" aria-label="小字号" title="小字号" @click="setSize('小')">
          A-
        </button>
        <button
          type="button"
          :class="{ active: form.size === '标准' }"
          aria-label="标准字号"
          title="标准字号"
          @click="setSize('标准')"
        >
          A
        </button>
        <button type="button" :class="{ active: form.size === '大' }" aria-label="大字号" title="大字号" @click="setSize('大')">
          A+
        </button>
      </div>
      <label class="floating-opacity" title="透明度">
        <Icon name="blinds" :size="15" />
        <input type="range" min="55" max="100" step="5" :value="Number.parseInt(form.opacity, 10)" @input="setOpacity" />
      </label>
      <button type="button" aria-label="关闭悬浮字幕" title="关闭悬浮字幕" @click="emit('close')">
        <Icon name="x" :size="15" />
      </button>
    </div>
    <p
      v-if="showSource"
      class="floating-source"
      :data-tauri-drag-region="desktop ? true : undefined"
    >
      {{ pair.source }}
    </p>
    <p class="floating-translation" :data-tauri-drag-region="desktop ? true : undefined">
      {{ pair.translation }}
    </p>
  </section>
</template>
