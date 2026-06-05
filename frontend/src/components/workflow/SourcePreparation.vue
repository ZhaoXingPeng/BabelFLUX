<script setup lang="ts">
import type { SourceInputState, SourceOption } from "./types";

const props = defineProps<{
  source: SourceOption;
  input: SourceInputState;
  urlError: string | null;
}>();

const emit = defineEmits<{
  selectFile: [file: File | null];
  updateUrl: [url: string];
  requestPermission: [];
}>();

function isFileSource() {
  return props.source.key === "video-file" || props.source.key === "audio-file";
}

function isUrlSource() {
  return props.source.key === "url";
}

function needsPermission() {
  return ["microphone", "browser-tab", "screen-window"].includes(props.source.key);
}

function handleFileChange(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0] ?? null;
  emit("selectFile", file);
}
</script>

<template>
  <div class="source-prep">
    <label v-if="isFileSource()" class="block">
      <span class="form-label">{{ source.key === "video-file" ? "视频文件" : "音频文件" }}</span>
      <input
        class="form-control file-control"
        type="file"
        :accept="source.key === 'video-file' ? 'video/*' : 'audio/*'"
        @change="handleFileChange"
      />
      <span class="source-prep-status">{{ input.fileName || "未选择文件" }}</span>
    </label>

    <label v-else-if="isUrlSource()" class="block">
      <span class="form-label">URL</span>
      <input
        class="form-control"
        type="url"
        :value="input.url"
        placeholder="https://example.com/live"
        @input="emit('updateUrl', ($event.target as HTMLInputElement).value)"
      />
      <span class="source-prep-status" :class="{ error: Boolean(urlError) }">
        {{ urlError ?? "URL 已就绪" }}
      </span>
    </label>

    <div v-else-if="needsPermission()" class="grid gap-2">
      <button
        class="secondary-button"
        type="button"
        :disabled="input.permissionState === 'requesting'"
        @click="emit('requestPermission')"
      >
        {{
          input.permissionState === "requesting"
            ? "请求中"
            : input.permissionState === "granted"
              ? "重新授权"
              : "申请权限"
        }}
      </button>
      <span
        class="source-prep-status"
        :class="{ error: input.permissionState === 'denied', ready: input.permissionState === 'granted' }"
      >
        {{ input.permissionMessage }}
      </span>
    </div>

    <p v-else class="source-prep-status">桌面端能力，当前 Web 版本不可用</p>
  </div>
</template>
