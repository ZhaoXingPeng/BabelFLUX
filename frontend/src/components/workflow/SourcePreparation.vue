<script setup lang="ts">
import { computed } from "vue";
import Icon from "../icons/Icon.vue";
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

const fileActionLabel = computed(() => (props.source.key === "video-file" ? "选择视频" : "选择音频"));

function isFixtureSource() {
  return props.source.key === "fixture-video";
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
    <div v-if="isFixtureSource()" class="grid gap-1">
      <span class="form-label">本地测试素材</span>
      <span class="source-prep-status ready">video.mp4 / voice.mp3 / source.zh.txt / target.en.txt 已就绪</span>
    </div>

    <label v-else-if="isFileSource()" class="block file-picker">
      <span class="form-label">{{ source.key === "video-file" ? "视频文件" : "音频文件" }}</span>
      <input
        class="file-control"
        type="file"
        :accept="source.key === 'video-file' ? 'video/*' : 'audio/*'"
        @change="handleFileChange"
      />
      <span class="file-picker-row">
        <span class="secondary-button file-picker-button">
          <Icon name="upload" :size="16" />
          <span>{{ fileActionLabel }}</span>
        </span>
        <span class="file-picker-name" :class="{ empty: !input.fileName }">
          {{ input.fileName || "未选择文件" }}
        </span>
      </span>
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
