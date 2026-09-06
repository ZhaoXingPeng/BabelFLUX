<script setup lang="ts">
import { computed } from "vue";
import SelectField from "../common/SelectField.vue";
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
    keys: [
      ...props.sources.filter((source) => source.fixture).map((source) => source.key),
      "video-file",
      "audio-file"
    ]
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

function sourcesFor(keys: string[]) {
  return keys.map((key) => props.sources.find((source) => source.key === key)).filter((source): source is SourceOption => Boolean(source));
}

const sourceOptions = computed(() =>
  groups.value.flatMap((group) =>
    sourcesFor(group.keys).map((source) => ({
      value: source.key,
      label: source.label,
      meta: source.channel,
      disabled: source.disabled,
      group: group.label
    }))
  )
);

function handleSelect(value: string) {
  const source = props.sources.find((item) => item.key === value);
  if (source && !source.disabled) emit("select", source);
}
</script>

<template>
  <label class="source-select">
    <span class="form-label">输入声源</span>
    <SelectField
      :model-value="selectedKey"
      name="source-select"
      label="输入声源"
      :options="sourceOptions"
      @update:model-value="handleSelect"
    />
  </label>
</template>
