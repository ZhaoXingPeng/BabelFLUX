<script setup lang="ts">
defineProps<{
  index: string;
  badge: string;
  title: string;
  subtitle: string;
  features: string[];
  cta: string;
  variant?: "primary" | "neutral";
}>();

const emit = defineEmits<{
  activate: [];
}>();
</script>

<template>
  <button
    class="entry-card group"
    :class="{ primary: variant === 'primary' }"
    type="button"
    @click="emit('activate')"
  >
    <span class="entry-card-top">
      <span>{{ index }}</span>
      <span class="entry-card-icon" aria-hidden="true">
        <slot name="icon" />
      </span>
    </span>
    <span class="entry-card-copy">
      <span class="entry-card-badge">{{ badge }}</span>
      <strong>{{ title }}</strong>
      <span>{{ subtitle }}</span>
    </span>
    <span class="entry-card-features">
      <span v-for="feature in features" :key="feature">{{ feature }}</span>
    </span>
    <span class="entry-card-cta">
      {{ cta }}
      <span aria-hidden="true">→</span>
    </span>
  </button>
</template>
