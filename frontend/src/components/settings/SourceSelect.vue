<script setup lang="ts">
import { computed } from "vue";
import type { SourceOption } from "../workflow/types";

const props = defineProps<{
  sources: SourceOption[];
  selectedKey: string;
}>();

const emit = defineEmits<{
  select: [source: SourceOption];
}>();

const groups = computed(() => [
  {
    label: "本地文件",
    keys: ["fixture-video", "video-file", "audio-file"]
  },
  {
    label: "网页音频",
    keys: ["url", "browser-tab", "screen-window"]
  },
  {
    label: "麦克风",
    keys: ["microphone"]
  },
  {
    label: "桌面端",
    keys: ["system-audio"]
  }
]);

const selectedSource = computed(() => props.sources.find((source) => source.key === props.selectedKey) ?? props.sources[0]);

function handleChange(event: Event) {
  const source = props.sources.find((item) => item.key === (event.target as HTMLSelectElement).value);
  if (source && !source.disabled) emit("select", source);
}

function sourcesFor(keys: string[]) {
  return keys.map((key) => props.sources.find((source) => source.key === key)).filter((source): source is SourceOption => Boolean(source));
}
</script>

<template>
  <label class="source-select">
    <span class="form-label">输入声源</span>
    <select class="form-control" :value="selectedKey" @change="handleChange">
      <optgroup v-for="group in groups" :key="group.label" :label="group.label">
        <option v-for="source in sourcesFor(group.keys)" :key="source.key" :value="source.key" :disabled="source.disabled">
          {{ source.label }} · {{ source.channel }}
        </option>
      </optgroup>
    </select>
    <small>{{ selectedSource.availability === "desktop" ? "需客户端能力" : selectedSource.channel }}</small>
  </label>
</template>
