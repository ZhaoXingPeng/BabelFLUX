<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, useId } from "vue";
import { gsap } from "gsap";
import { shouldReduceMotion } from "../../composables/motion";
import Icon from "../icons/Icon.vue";

interface SelectOption {
  value: string;
  label: string;
  meta?: string;
  disabled?: boolean;
  group?: string;
}

type SelectOptionInput = string | SelectOption;

const props = withDefaults(
  defineProps<{
    modelValue: string;
    options: SelectOptionInput[];
    placeholder?: string;
    label?: string;
    name?: string;
    variant?: "default" | "language";
  }>(),
  {
    placeholder: "请选择",
    label: "下拉选择",
    name: undefined,
    variant: "default"
  }
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();

const root = ref<HTMLElement | null>(null);
const trigger = ref<HTMLButtonElement | null>(null);
const panel = ref<HTMLElement | null>(null);
const open = ref(false);
const activeIndex = ref(0);
const listboxId = `select-field-${useId()}`;
let tween: gsap.core.Tween | null = null;

const normalizedOptions = computed<SelectOption[]>(() =>
  props.options.map((option) =>
    typeof option === "string"
      ? {
          value: option,
          label: option
        }
      : option
  )
);

const enabledOptions = computed(() => normalizedOptions.value.filter((option) => !option.disabled));
const selectedOption = computed(() => normalizedOptions.value.find((option) => option.value === props.modelValue));
const activeOptionId = computed(() => `${listboxId}-option-${activeIndex.value}`);

function firstEnabledIndex() {
  const index = normalizedOptions.value.findIndex((option) => !option.disabled);
  return index >= 0 ? index : 0;
}

function setActiveToSelected() {
  const selectedIndex = normalizedOptions.value.findIndex((option) => option.value === props.modelValue && !option.disabled);
  activeIndex.value = selectedIndex >= 0 ? selectedIndex : firstEnabledIndex();
}

function shouldShowGroup(index: number) {
  const group = normalizedOptions.value[index]?.group;
  if (!group) return false;
  return index === 0 || normalizedOptions.value[index - 1]?.group !== group;
}

function animatePanel() {
  tween?.kill();
  if (!panel.value || shouldReduceMotion()) return;
  tween = gsap.fromTo(
    panel.value,
    { autoAlpha: 0, y: -4 },
    { autoAlpha: 1, y: 0, duration: 0.14, ease: "power2.out", clearProps: "opacity,visibility,transform" }
  );
}

async function openPanel() {
  if (open.value || enabledOptions.value.length === 0) return;
  setActiveToSelected();
  open.value = true;
  await nextTick();
  animatePanel();
}

function closePanel() {
  if (!open.value) return;
  tween?.kill();
  open.value = false;
}

function togglePanel() {
  if (open.value) {
    closePanel();
  } else {
    openPanel();
  }
}

function selectOption(option: SelectOption) {
  if (option.disabled) return;
  emit("update:modelValue", option.value);
  closePanel();
  trigger.value?.focus();
}

function moveActive(direction: 1 | -1) {
  const options = normalizedOptions.value;
  if (options.length === 0) return;

  let nextIndex = activeIndex.value;
  for (let step = 0; step < options.length; step += 1) {
    nextIndex = (nextIndex + direction + options.length) % options.length;
    if (!options[nextIndex].disabled) {
      activeIndex.value = nextIndex;
      return;
    }
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    if (!open.value) {
      openPanel();
      return;
    }
    moveActive(event.key === "ArrowDown" ? 1 : -1);
  }

  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    if (!open.value) {
      openPanel();
      return;
    }
    const option = normalizedOptions.value[activeIndex.value];
    if (option) selectOption(option);
  }

  if (event.key === "Escape") {
    event.preventDefault();
    closePanel();
  }
}

function handleDocumentPointerDown(event: PointerEvent) {
  const target = event.target;
  if (!(target instanceof Node)) return;
  if (!root.value?.contains(target)) closePanel();
}

onMounted(() => {
  document.addEventListener("pointerdown", handleDocumentPointerDown);
});

onUnmounted(() => {
  tween?.kill();
  document.removeEventListener("pointerdown", handleDocumentPointerDown);
});
</script>

<template>
  <div
    ref="root"
    class="select-field"
    :class="[`select-field-${variant}`, { open }]"
    :data-select-id="name"
  >
    <button
      ref="trigger"
      class="select-trigger"
      type="button"
      role="combobox"
      :aria-label="label"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :aria-controls="listboxId"
      :aria-activedescendant="open ? activeOptionId : undefined"
      @click="togglePanel"
      @keydown="handleKeydown"
    >
      <span class="select-trigger-copy">
        <span class="select-value" :class="{ placeholder: !selectedOption }">
          {{ selectedOption?.label ?? placeholder }}
        </span>
        <small v-if="selectedOption?.meta">{{ selectedOption.meta }}</small>
      </span>
      <Icon class="select-chevron" name="chevron-down" :size="17" />
    </button>

    <div
      v-if="open"
      :id="listboxId"
      ref="panel"
      class="select-popover"
      role="listbox"
      :aria-label="label"
      @keydown="handleKeydown"
    >
      <template v-for="(option, index) in normalizedOptions" :key="option.value">
        <div v-if="shouldShowGroup(index)" class="select-group">{{ option.group }}</div>
        <button
          class="select-option"
          :id="`${listboxId}-option-${index}`"
          type="button"
          role="option"
          :class="{ active: activeIndex === index, selected: option.value === modelValue }"
          :disabled="option.disabled"
          :aria-selected="option.value === modelValue"
          :data-select-option="option.value"
          @mouseenter="activeIndex = index"
          @click="selectOption(option)"
        >
          <span>
            <strong>{{ option.label }}</strong>
            <small v-if="option.meta">{{ option.meta }}</small>
          </span>
          <Icon v-if="option.value === modelValue" name="check" :size="16" />
        </button>
      </template>
    </div>
  </div>
</template>
