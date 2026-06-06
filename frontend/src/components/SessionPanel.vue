<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useSessionStore } from "../stores/session";

const sessionStore = useSessionStore();
const { status, sessionId, sourceSyncState, wsConnected, errorMessage } = storeToRefs(sessionStore);
</script>

<template>
  <aside class="rounded-[2rem] border border-white/60 bg-white/75 p-6 shadow-2xl shadow-ink/10 backdrop-blur">
    <p class="text-sm font-semibold uppercase tracking-[0.35em] text-tide">Realtime Console</p>
    <h1 class="mt-3 font-display text-3xl font-black text-ink">LingoSync / 灵犀同传</h1>
    <p class="mt-3 text-sm leading-6 text-ink/65">
      当前骨架使用后端 mock provider，先验证源语言字幕、翻译字幕、同步状态和纠偏事件的前后端通道。
    </p>

    <div class="mt-6 grid gap-3 text-sm">
      <div class="flex items-center justify-between rounded-2xl bg-ink px-4 py-3 text-white">
        <span>会话状态</span>
        <strong>{{ status }}</strong>
      </div>
      <div class="flex items-center justify-between rounded-2xl bg-salt px-4 py-3 text-ink">
        <span>WebSocket</span>
        <strong>{{ wsConnected ? "connected" : "closed" }}</strong>
      </div>
      <div class="rounded-2xl bg-salt px-4 py-3 text-ink">
        <p class="text-xs text-ink/55">Session ID</p>
        <p class="mt-1 break-all font-mono text-xs">{{ sessionId ?? "not started" }}</p>
      </div>
      <div class="rounded-2xl bg-salt px-4 py-3 text-ink">
        <p class="text-xs text-ink/55">同步状态</p>
        <p class="mt-1 font-semibold">{{ sourceSyncState.status }} · {{ sourceSyncState.lagMs }}ms</p>
        <p class="mt-1 text-xs text-ink/60">{{ sourceSyncState.message }}</p>
      </div>
    </div>

    <p v-if="errorMessage" class="mt-4 rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger">
      {{ errorMessage }}
    </p>

    <div class="mt-6 flex gap-3">
      <button
        class="rounded-full bg-tide px-5 py-3 text-sm font-bold text-ink transition hover:-translate-y-0.5 hover:shadow-lg"
        type="button"
        @click="sessionStore.startMode('quick')"
      >
        启动 Demo
      </button>
      <button
        class="rounded-full border border-ink/15 px-5 py-3 text-sm font-bold text-ink transition hover:bg-ink hover:text-white"
        type="button"
        @click="sessionStore.stopSession()"
      >
        停止
      </button>
    </div>
  </aside>
</template>
