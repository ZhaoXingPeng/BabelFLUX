<script setup lang="ts">
import { computed, ref } from "vue";
import { useStickyFollow } from "../../composables/useStickyFollow";
import type { TranscriptPair } from "../workflow/types";
import StreamLine from "./StreamLine.vue";

const props = defineProps<{
  pairs: TranscriptPair[];
}>();

const sourceList = ref<HTMLElement | null>(null);
const translationList = ref<HTMLElement | null>(null);
const signature = computed(() =>
  props.pairs
    .map((pair) => `${pair.segmentId ?? pair.time}:${pair.state}:${pair.source}:${pair.translation}:${pair.isActive ? "1" : "0"}`)
    .join("|")
);

const sourceFollow = useStickyFollow(sourceList, () => signature.value, { block: "start" });
const translationFollow = useStickyFollow(translationList, () => signature.value, { block: "start" });
</script>

<template>
  <div class="split-parallel-view">
    <section>
      <header>
        <span>Source</span>
        <strong>源文 EN</strong>
      </header>
      <div ref="sourceList" class="stream-list">
        <article
          v-for="pair in pairs"
          :key="`src-${pair.segmentId ?? pair.time}`"
          :class="{ active: pair.isActive }"
          :data-active="pair.isActive ? 'true' : undefined"
        >
          <time>{{ pair.time }}</time>
          <p><StreamLine :text="pair.source" :state="pair.state" /></p>
        </article>
        <button v-if="!sourceFollow.following.value" class="follow-latest" type="button" @click="sourceFollow.followLatest">
          回到最新
        </button>
      </div>
    </section>
    <section>
      <header>
        <span>Translation</span>
        <strong>译文 ZH</strong>
      </header>
      <div ref="translationList" class="stream-list">
        <article
          v-for="pair in pairs"
          :key="`dst-${pair.segmentId ?? pair.time}`"
          :class="{ active: pair.isActive, revised: pair.state === 'revised' }"
          :data-active="pair.isActive ? 'true' : undefined"
        >
          <time>{{ pair.time }}</time>
          <p><StreamLine :text="pair.translation" :state="pair.state" strong /></p>
          <small v-if="pair.revisionReason">{{ pair.revisionReason }}</small>
        </article>
        <button
          v-if="!translationFollow.following.value"
          class="follow-latest"
          type="button"
          @click="translationFollow.followLatest"
        >
          回到最新
        </button>
      </div>
    </section>
  </div>
</template>
