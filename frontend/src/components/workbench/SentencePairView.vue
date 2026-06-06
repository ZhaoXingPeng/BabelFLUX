<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { gsap } from "gsap";
import { DUR, EASE, shouldReduceMotion } from "../../composables/motion";
import { useStickyFollow } from "../../composables/useStickyFollow";
import type { TranscriptPair } from "../workflow/types";
import SentencePairCard from "./SentencePairCard.vue";

const props = defineProps<{
  pairs: TranscriptPair[];
}>();

const root = ref<HTMLElement | null>(null);
let ctx: ReturnType<typeof gsap.context> | null = null;
const seenCards = new Set<string>();
const animatedRevisions = new Set<string>();

const signature = computed(() =>
  props.pairs
    .map((pair) => `${pair.segmentId ?? pair.time}:${pair.state}:${pair.translation}:${pair.isActive ? "1" : "0"}`)
    .join("|")
);

const follow = useStickyFollow(root, () => signature.value, { block: "center" });

function pairKey(pair: TranscriptPair): string {
  return pair.segmentId ?? pair.time;
}

function findCard(key: string): HTMLElement | null {
  return Array.from(root.value?.querySelectorAll<HTMLElement>(".sentence-pair-card") ?? []).find(
    (card) => card.dataset.pairKey === key
  ) ?? null;
}

function animateNewCard(card: HTMLElement) {
  gsap.fromTo(card, { autoAlpha: 0, y: 12 }, { autoAlpha: 1, y: 0, duration: DUR.base, ease: EASE });
}

function animateRevision(card: HTMLElement) {
  const oldTranslation = card.querySelector(".old-translation");
  const translation = card.querySelector(".translation-line");
  const badge = card.querySelector(".revision-float");
  const timeline = gsap.timeline();

  if (oldTranslation) {
    timeline.to(oldTranslation, { opacity: 0.38, y: -2, duration: DUR.micro, ease: EASE }, 0);
  }

  if (translation) {
    timeline.fromTo(translation, { autoAlpha: 0, y: 6 }, { autoAlpha: 1, y: 0, duration: 0.35, ease: EASE }, 0.05);
    // 译文文本本身做一次琥珀高亮扫过，让“这句被自动纠偏了”在文字层面即刻可见。
    timeline.fromTo(
      translation,
      { backgroundColor: "rgba(224, 164, 88, 0.34)", borderRadius: "6px" },
      { backgroundColor: "rgba(224, 164, 88, 0)", duration: 1.2, ease: "power2.out", clearProps: "backgroundColor,borderRadius" },
      0.05
    );
  }

  timeline.fromTo(
    card,
    { boxShadow: "0 0 0 0 rgba(224, 164, 88, 0)" },
    {
      boxShadow: "0 0 0 2px rgba(224, 164, 88, 0.58)",
      duration: 0.3,
      ease: EASE,
      repeat: 1,
      yoyo: true
    },
    0.04
  );

  if (badge) {
    timeline
      .fromTo(badge, { autoAlpha: 0, scale: 0.92, y: 4 }, { autoAlpha: 1, scale: 1, y: 0, duration: 0.24, ease: EASE }, 0.06)
      .to(badge, { autoAlpha: 0, duration: 0.34, delay: 1.35 });
  }
}

onMounted(() => {
  if (!root.value) return;
  ctx = gsap.context(() => {}, root.value);
  props.pairs.forEach((pair) => {
    const key = pairKey(pair);
    seenCards.add(key);
    if (pair.state === "revised") animatedRevisions.add(key);
  });
});

onUnmounted(() => {
  ctx?.revert();
});

watch(
  () => signature.value,
  async () => {
    await nextTick();
    if (!root.value || shouldReduceMotion()) return;

    ctx?.add(() => {
      props.pairs.forEach((pair) => {
        const key = pairKey(pair);
        const card = findCard(key);
        if (!card) return;

        if (!seenCards.has(key)) {
          seenCards.add(key);
          animateNewCard(card);
        }

        if (pair.state === "revised" && !animatedRevisions.has(key)) {
          animatedRevisions.add(key);
          animateRevision(card);
        }
      });
    });
  },
  { flush: "post" }
);
</script>

<template>
  <div ref="root" class="sentence-pair-view">
    <SentencePairCard v-for="pair in pairs" :key="pair.segmentId ?? `${pair.time}-${pair.source}`" :pair="pair" />
    <button v-if="!follow.following.value" class="follow-latest" type="button" @click="follow.followLatest">
      回到最新
    </button>
  </div>
</template>
