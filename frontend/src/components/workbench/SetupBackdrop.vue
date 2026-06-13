<script setup lang="ts">
import { ref } from "vue";
import { useGsapReveal } from "../../composables/useGsapReveal";

const root = ref<HTMLElement | null>(null);
useGsapReveal(root, { y: 10, stagger: 0.08 });
</script>

<template>
  <section ref="root" class="setup-backdrop" aria-hidden="true">
    <p data-reveal>BabelFlux Web</p>
    <h1 data-reveal>巴别流 同传</h1>
    <span data-reveal>设置音源、语言与模型后进入沉浸式同传工作台</span>
  </section>
</template>
