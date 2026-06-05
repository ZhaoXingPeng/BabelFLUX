<script setup lang="ts">
import type { DesktopLaunchState } from "../workflow/types";

defineProps<{
  state: DesktopLaunchState;
  message: string;
  deepLinkUrl: string | null;
}>();

const emit = defineEmits<{
  retry: [];
  reopen: [];
  continueWeb: [];
  close: [];
}>();
</script>

<template>
  <section class="desktop-launch-prompt" role="status" aria-live="polite">
    <div>
      <p>Desktop handoff</p>
      <strong>{{ message }}</strong>
      <span v-if="state === 'fallback'">桌面端未响应，可以继续使用网页悬浮字幕。</span>
      <span v-else-if="state === 'error'">请确认后端已启动，或稍后重试。</span>
      <span v-else>正在等待系统协议响应。</span>
    </div>
    <div class="desktop-launch-actions">
      <button class="stage-button" type="button" @click="emit('retry')">重试唤起</button>
      <button v-if="state === 'fallback'" class="stage-button" type="button" @click="emit('reopen')">
        我已安装，直接打开
      </button>
      <button class="stage-button primary" type="button" @click="emit('continueWeb')">继续网页悬浮</button>
      <a v-if="deepLinkUrl" class="stage-button" :href="deepLinkUrl">打开协议</a>
      <button class="stage-button" type="button" aria-label="关闭桌面唤起提示" @click="emit('close')">×</button>
    </div>
  </section>
</template>
