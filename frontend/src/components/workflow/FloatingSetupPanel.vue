<script setup lang="ts">
import FlowSteps from "./FlowSteps.vue";
import SourceSelector from "./SourceSelector.vue";
import type { FloatingFormState, RuntimeState, SourceOption } from "./types";

defineProps<{
  form: FloatingFormState;
  state: RuntimeState;
  statusLabel: string;
  domains: string[];
  languages: string[];
  targetLanguages: string[];
  modelProfiles: string[];
  sources: SourceOption[];
  canStart: boolean;
}>();

const emit = defineEmits<{
  start: [];
  switchQuick: [];
  selectSource: [source: SourceOption];
}>();
</script>

<template>
  <aside class="rounded-lg border border-[#d7ddd8] bg-white p-4">
    <div class="flex items-center justify-between gap-3">
      <h2 class="text-base font-bold">悬浮字幕设置</h2>
      <span class="rounded-md bg-[#eef1ee] px-2 py-1 text-xs text-[#526057]">{{ statusLabel }}</span>
    </div>

    <FlowSteps class="mt-4" :state="state" middle-label="字幕" report-label="记录" />

    <div class="mt-4 space-y-4">
      <label class="block">
        <span class="form-label">模型选择</span>
        <select v-model="form.modelProfile" class="form-control">
          <option v-for="profile in modelProfiles" :key="profile">{{ profile }}</option>
        </select>
      </label>

      <div class="grid grid-cols-2 gap-3">
        <label class="block">
          <span class="form-label">源语言</span>
          <select v-model="form.sourceLanguage" class="form-control">
            <option v-for="language in languages" :key="language">{{ language }}</option>
          </select>
        </label>
        <label class="block">
          <span class="form-label">目标语言</span>
          <select v-model="form.targetLanguage" class="form-control">
            <option v-for="language in targetLanguages" :key="language">{{ language }}</option>
          </select>
        </label>
      </div>

      <label class="block">
        <span class="form-label">专业领域</span>
        <select v-model="form.domain" class="form-control">
          <option v-for="domain in domains" :key="domain">{{ domain }}</option>
        </select>
      </label>

      <div>
        <span class="form-label">声源</span>
        <SourceSelector :sources="sources" :selected-key="form.source" @select="emit('selectSource', $event)" />
      </div>

      <div class="grid grid-cols-2 gap-3">
        <label class="block">
          <span class="form-label">字幕样式</span>
          <select v-model="form.style" class="form-control">
            <option>双语字幕</option>
            <option>仅译文</option>
            <option>原文优先</option>
          </select>
        </label>
        <label class="block">
          <span class="form-label">字号</span>
          <select v-model="form.size" class="form-control">
            <option>紧凑</option>
            <option>标准</option>
            <option>大号</option>
          </select>
        </label>
      </div>

      <label class="block">
        <span class="form-label">透明度</span>
        <select v-model="form.opacity" class="form-control">
          <option>70%</option>
          <option>80%</option>
          <option>90%</option>
          <option>100%</option>
        </select>
      </label>
    </div>

    <div class="mt-5 grid gap-2">
      <button class="primary-button" type="button" :disabled="!canStart" @click="emit('start')">
        {{ state === "connecting" ? "连接中" : "开始使用" }}
      </button>
      <button class="secondary-button" type="button" @click="emit('switchQuick')">
        返回快速同传
      </button>
    </div>
  </aside>
</template>
