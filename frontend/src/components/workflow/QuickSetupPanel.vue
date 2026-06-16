<script setup lang="ts">
import SelectField from "../common/SelectField.vue";
import FlowSteps from "./FlowSteps.vue";
import SourcePreparation from "./SourcePreparation.vue";
import SourceSelector from "./SourceSelector.vue";
import type { QuickFormState, RuntimeState, SourceInputState, SourceOption } from "./types";

defineProps<{
  form: QuickFormState;
  state: RuntimeState;
  statusLabel: string;
  domains: string[];
  languages: string[];
  targetLanguages: string[];
  modelProfiles: string[];
  sources: SourceOption[];
  selectedSource: SourceOption;
  input: SourceInputState;
  urlError: string | null;
  canStart: boolean;
}>();

const emit = defineEmits<{
  start: [];
  selectSource: [source: SourceOption];
  selectFile: [file: File | null];
  updateUrl: [url: string];
  requestPermission: [];
}>();
</script>

<template>
  <aside class="rounded-lg border border-[#d7ddd8] bg-white p-4">
    <div class="flex items-center justify-between gap-3">
      <h2 class="text-base font-bold">快速同传设置</h2>
      <span class="rounded-md bg-[#eef1ee] px-2 py-1 text-xs text-[#526057]">{{ statusLabel }}</span>
    </div>

    <FlowSteps class="mt-4" :state="state" middle-label="同传" report-label="复盘" />

    <div class="mt-4 space-y-4">
      <label class="block">
        <span class="form-label">会话名称</span>
        <input v-model="form.name" class="form-control" type="text" />
      </label>

      <label class="block">
        <span class="form-label">专业领域</span>
        <SelectField v-model="form.domain" name="legacy-domain" label="专业领域" :options="domains" />
      </label>

      <div class="grid grid-cols-2 gap-3">
        <label class="block">
          <span class="form-label">源语言</span>
          <SelectField v-model="form.sourceLanguage" name="legacy-source-language" label="源语言" :options="languages" />
        </label>
        <label class="block">
          <span class="form-label">目标语言</span>
          <SelectField
            v-model="form.targetLanguage"
            name="legacy-target-language"
            label="目标语言"
            :options="targetLanguages"
          />
        </label>
      </div>

      <label class="block">
        <span class="form-label">模型选择</span>
        <SelectField v-model="form.modelProfile" name="legacy-model-profile" label="模型选择" :options="modelProfiles" />
      </label>

      <label class="flex items-center justify-between gap-3 rounded-md border border-[#d7ddd8] bg-[#f7f8f6] px-3 py-2">
        <span>
          <span class="form-label mb-0">语音播报</span>
          <small class="field-hint">开启后播报目标译文，默认关闭</small>
        </span>
        <input v-model="form.ttsEnabled" class="h-4 w-4" type="checkbox" />
      </label>

      <div>
        <span class="form-label">输入声源</span>
        <SourceSelector :sources="sources" :selected-key="form.source" @select="emit('selectSource', $event)" />
      </div>

      <SourcePreparation
        :source="selectedSource"
        :input="input"
        :url-error="urlError"
        @select-file="emit('selectFile', $event)"
        @update-url="emit('updateUrl', $event)"
        @request-permission="emit('requestPermission')"
      />
    </div>

    <div class="mt-5 grid gap-2">
      <button class="primary-button" type="button" :disabled="!canStart" @click="emit('start')">
        {{ state === "connecting" ? "连接中" : "开始同传" }}
      </button>
    </div>
  </aside>
</template>
