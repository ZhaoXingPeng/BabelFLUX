<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { gsap } from "gsap";
import type { TranscriptPair } from "../workflow/types";
import SentencePairCard from "./SentencePairCard.vue";

const props = defineProps<{
  pairs: TranscriptPair[];
}>();

const root = ref<HTMLElement | null>(null);
let ctx: ReturnType<typeof gsap.context> | null = null;

onMounted(() => {
  if (!root.value) return;
  ctx = gsap.context(() => {}, root.value);
});

onUnmounted(() => {
  ctx?.revert();
});

watch(
  () => props.pairs.map((pair) => `${pair.segmentId ?? pair.time}:${pair.state}:${pair.translation}`).join("|"),
  async () => {
    await nextTick();
    if (!root.value || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    ctx?.add(() => {
      gsap.fromTo(
        "[data-revision-pulse='true']",
        { scale: 0.985, backgroundColor: "rgba(224, 164, 88, 0.18)" },
        { scale: 1, backgroundColor: "rgba(255, 255, 255, 0.055)", duration: 0.8, ease: "power2.out" }
      );
    });
  },
  { flush: "post" }
);
</script>

<template>
  <div ref="root" class="sentence-pair-view">
    <SentencePairCard v-for="pair in pairs" :key="pair.segmentId ?? `${pair.time}-${pair.source}`" :pair="pair" />
  </div>
</template>
