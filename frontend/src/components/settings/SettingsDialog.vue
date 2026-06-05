<script setup lang="ts">
import LanguagePairField from "./LanguagePairField.vue";
import SourceSelect from "./SourceSelect.vue";
import SourcePreparation from "../workflow/SourcePreparation.vue";
import type { QuickFormState, RuntimeState, SourceInputState, SourceOption } from "../workflow/types";

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
  close: [];
  start: [];
  selectSource: [source: SourceOption];
  selectFile: [file: File | null];
  updateUrl: [url: string];
  requestPermission: [];
}>();
</script>

<template>
  <div class="settings-backdrop" role="presentation">
    <section class="settings-dialog" role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <header class="settings-header">
        <div>
          <p>Session setup</p>
          <h2 id="settings-title">同声传译设置</h2>
        </div>
        <div class="settings-actions">
          <span>{{ statusLabel }}</span>
          <button class="icon-button light" type="button" aria-label="关闭设置" @click="emit('close')">×</button>
        </div>
      </header>

      <div class="settings-body">
        <section class="settings-group">
          <div class="settings-group-title">
            <span>01</span>
            <strong>基本信息</strong>
          </div>
          <div class="settings-two">
            <label class="block">
              <span class="form-label">会话名称</span>
              <input v-model="form.name" class="form-control" type="text" />
              <small class="field-hint">用于会话报告与导出文件命名</small>
            </label>

            <label class="block">
              <span class="form-label">专业领域</span>
              <select v-model="form.domain" class="form-control">
                <option v-for="domain in domains" :key="domain">{{ domain }}</option>
              </select>
              <small class="field-hint">决定术语风格，参与实时与会后纠偏</small>
            </label>
          </div>
        </section>

        <section class="settings-group">
          <div class="settings-group-title">
            <span>02</span>
            <strong>音源与方向</strong>
          </div>
          <LanguagePairField
            :source-language="form.sourceLanguage"
            :target-language="form.targetLanguage"
            :languages="languages"
            :target-languages="targetLanguages"
            @update-source-language="form.sourceLanguage = $event"
            @update-target-language="form.targetLanguage = $event"
          />
          <SourceSelect :sources="sources" :selected-key="form.source" @select="emit('selectSource', $event)" />
          <SourcePreparation
            :source="selectedSource"
            :input="input"
            :url-error="urlError"
            @select-file="emit('selectFile', $event)"
            @update-url="emit('updateUrl', $event)"
            @request-permission="emit('requestPermission')"
          />
        </section>

        <section class="settings-group">
          <div class="settings-group-title">
            <span>03</span>
            <strong>模型策略</strong>
          </div>
          <label class="block">
            <span class="form-label">模型选择</span>
            <select v-model="form.modelProfile" class="form-control">
              <option v-for="profile in modelProfiles" :key="profile">{{ profile }}</option>
            </select>
          </label>
          <p class="settings-note">使用后端模型策略统一路由，前端不接触供应商密钥。</p>
        </section>
      </div>

      <footer class="settings-footer">
        <button class="secondary-button" type="button" @click="emit('close')">取消</button>
        <button class="primary-button" type="button" :disabled="!canStart" @click="emit('start')">
          {{ state === "connecting" ? "连接中" : "开始同传" }}
        </button>
      </footer>
    </section>
  </div>
</template>
