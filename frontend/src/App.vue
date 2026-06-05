<script setup lang="ts">
import SessionPanel from "./components/SessionPanel.vue";
import SubtitleStage from "./components/SubtitleStage.vue";
</script>

<template>
  <main class="min-h-screen overflow-hidden bg-[radial-gradient(circle_at_top_left,#dff8ee,transparent_30%),linear-gradient(135deg,#f7fbf8_0%,#e8f0ef_45%,#d7ebe6_100%)] px-5 py-6 text-ink lg:px-10">
    <div class="mx-auto grid max-w-7xl gap-6 lg:grid-cols-[380px_1fr]">
      <SessionPanel />
      <SubtitleStage />
    </div>
  </main>
</template>
