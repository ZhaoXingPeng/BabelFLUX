<script setup lang="ts">
import { ref } from "vue";
import Icon from "../icons/Icon.vue";
import type { GlossaryTerm } from "../workflow/types";

const props = defineProps<{
  modelValue: GlossaryTerm[];
}>();

const emit = defineEmits<{
  "update:modelValue": [terms: GlossaryTerm[]];
}>();

const sourceTerm = ref("");
const targetTerm = ref("");
const errorMessage = ref("");

function addTerm() {
  const source = sourceTerm.value.trim();
  const target = targetTerm.value.trim();
  if (!source || !target) {
    errorMessage.value = "请填写原文和译法";
    return;
  }
  if (props.modelValue.some((term) => term.sourceTerm.toLocaleLowerCase() === source.toLocaleLowerCase())) {
    errorMessage.value = "该术语已存在";
    return;
  }

  emit("update:modelValue", [...props.modelValue, { sourceTerm: source, targetTerm: target }]);
  sourceTerm.value = "";
  targetTerm.value = "";
  errorMessage.value = "";
}

function removeTerm(index: number) {
  emit(
    "update:modelValue",
    props.modelValue.filter((_term, termIndex) => termIndex !== index)
  );
}
</script>

<template>
  <section class="glossary-editor" aria-labelledby="glossary-editor-title">
    <div class="glossary-editor-header">
      <div>
        <span id="glossary-editor-title" class="form-label">术语表</span>
        <small class="field-hint">{{ modelValue.length }} 条</small>
      </div>
    </div>

    <div class="glossary-editor-form">
      <input
        v-model="sourceTerm"
        class="form-control"
        data-testid="glossary-source"
        type="text"
        placeholder="原文术语"
        @keydown.enter.prevent="addTerm"
      />
      <input
        v-model="targetTerm"
        class="form-control"
        data-testid="glossary-target"
        type="text"
        placeholder="目标译法"
        @keydown.enter.prevent="addTerm"
      />
      <button class="icon-button light" type="button" aria-label="添加术语" @click="addTerm">
        <Icon name="plus" :size="16" />
      </button>
    </div>
    <p v-if="errorMessage" class="glossary-editor-error" role="alert">{{ errorMessage }}</p>

    <ul v-if="modelValue.length" class="glossary-editor-list">
      <li v-for="(term, index) in modelValue" :key="term.sourceTerm">
        <span>{{ term.sourceTerm }} <b aria-hidden="true">→</b> {{ term.targetTerm }}</span>
        <button
          class="icon-button light"
          type="button"
          :aria-label="`删除术语 ${term.sourceTerm}`"
          @click="removeTerm(index)"
        >
          <Icon name="trash-2" :size="15" />
        </button>
      </li>
    </ul>
  </section>
</template>
