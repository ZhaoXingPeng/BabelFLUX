<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";

const props = defineProps<{
  text: string;
  state?: string;
  strong?: boolean;
}>();

// 只有「正在识别中」的当前句需要逐单元入场动画；已定稿/已校正的句子是稳定文本，
// 直接渲染纯文本节点，既无意义也避免被反复重挂载。
const isStreaming = computed(() => props.state === "partial");
const visibleText = ref(props.text);
let revealTimer: number | null = null;

function clearRevealTimer() {
  if (revealTimer !== null) {
    window.clearInterval(revealTimer);
    revealTimer = null;
  }
}

function revealStepSize(remaining: number): number {
  if (remaining > 48) return 8;
  if (remaining > 24) return 5;
  if (remaining > 12) return 3;
  return 2;
}

function updateVisibleText(nextText: string, streaming: boolean) {
  clearRevealTimer();
  if (!streaming || !nextText || !nextText.startsWith(visibleText.value)) {
    visibleText.value = nextText;
    return;
  }
  const from = visibleText.value.length;
  if (from >= nextText.length) {
    visibleText.value = nextText;
    return;
  }
  let index = from;
  revealTimer = window.setInterval(() => {
    const remaining = nextText.length - index;
    index = Math.min(nextText.length, index + revealStepSize(remaining));
    visibleText.value = nextText.slice(0, index);
    if (index >= nextText.length) clearRevealTimer();
  }, 45);
}

watch(
  () => [props.text, props.state] as const,
  ([nextText, nextState]) => updateVisibleText(nextText, nextState === "partial"),
  { immediate: true }
);

onUnmounted(clearRevealTimer);

// CJK 没有空格，旧实现 `text.split(/\s+/)` 会把整句中文当成单个 token，
// 每次 partial 文本变化 → token 内容变 → key 变 → Vue 重挂载 → 整行重放入场动画 = 「顿/闪」。
// 这里改成「中文按字、拉丁文按词、空白单独成块」切分，并用索引作为 key：
// 已显示的单元原地复用（不重挂载、不重放动画），只有新增的尾部单元淡入。
const CJK = "\\u3040-\\u30ff\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff\\uff00-\\uffef";
const SEGMENTER = new RegExp(`\\s+|[${CJK}]|[^\\s${CJK}]+`, "gu");

type StreamUnit = { value: string; space: boolean };

const units = computed<StreamUnit[]>(() => {
  if (!isStreaming.value) return [];
  const matches = visibleText.value.match(SEGMENTER);
  if (!matches) return [];
  return matches.map((value) => ({ value, space: /^\s+$/.test(value) }));
});
</script>

<template>
  <span class="stream-line" :class="{ partial: isStreaming, strong }">
    <template v-if="isStreaming">
      <template v-for="(unit, index) in units" :key="index">
        <span v-if="unit.space" class="stream-space">{{ unit.value }}</span>
        <span v-else class="stream-token">{{ unit.value }}</span>
      </template>
      <span class="stream-caret" aria-hidden="true">▍</span>
    </template>
    <template v-else>{{ text }}</template>
  </span>
</template>
