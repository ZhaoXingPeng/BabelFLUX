<script setup lang="ts">
import { computed } from "vue";
import SelectField from "../common/SelectField.vue";

const props = defineProps<{
  sourceLanguage: string;
  targetLanguage: string;
  languages: string[];
  targetLanguages: string[];
}>();

const emit = defineEmits<{
  updateSourceLanguage: [language: string];
  updateTargetLanguage: [language: string];
}>();

const sourceCode = computed(() => toCode(props.sourceLanguage));
const targetCode = computed(() => toCode(props.targetLanguage));
const canSwap = computed(() => props.targetLanguages.includes(props.sourceLanguage) && props.languages.includes(props.targetLanguage));

function toCode(language: string): string {
  const codes: Record<string, string> = {
    自动检测: "AUTO",
    英语: "EN",
    中文: "ZH",
    日语: "JA",
    韩语: "KO",
    法语: "FR",
    德语: "DE"
  };
  return codes[language] ?? language.toUpperCase();
}

function swapLanguages() {
  if (!canSwap.value) return;
  emit("updateSourceLanguage", props.targetLanguage);
  emit("updateTargetLanguage", props.sourceLanguage);
}
</script>

<template>
  <div class="language-pair-field">
    <label>
      <span>源语言</span>
      <SelectField
        :model-value="sourceLanguage"
        name="source-language"
        label="源语言"
        variant="language"
        :options="languages"
        @update:model-value="emit('updateSourceLanguage', $event)"
      />
      <strong class="language-code">{{ sourceCode }}</strong>
    </label>
    <button class="language-swap" type="button" :disabled="!canSwap" aria-label="交换源语言和目标语言" @click="swapLanguages">
      ⇄
    </button>
    <label>
      <span>目标语言</span>
      <SelectField
        :model-value="targetLanguage"
        name="target-language"
        label="目标语言"
        variant="language"
        :options="targetLanguages"
        @update:model-value="emit('updateTargetLanguage', $event)"
      />
      <strong class="language-code">{{ targetCode }}</strong>
    </label>
  </div>
</template>
