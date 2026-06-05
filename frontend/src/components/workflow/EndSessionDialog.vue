<script setup lang="ts">
import type { ProductMode } from "./types";

defineProps<{
  mode: ProductMode | null;
}>();

const emit = defineEmits<{
  cancel: [];
  confirm: [];
}>();
</script>

<template>
  <div class="fixed inset-0 z-50 grid place-items-center bg-black/40 px-4">
    <section class="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
      <h2 class="text-lg font-bold">结束本次{{ mode === "floating" ? "字幕" : "同传" }}？</h2>
      <p class="mt-3 text-sm leading-6 text-[#4a5a50]">
        结束后将停止识别和翻译，并生成本次转写、翻译和修正记录。
      </p>
      <div class="mt-5 grid grid-cols-2 gap-3">
        <button class="secondary-button" type="button" @click="emit('cancel')">暂不结束</button>
        <button class="danger-button" type="button" @click="emit('confirm')">结束会议</button>
      </div>
    </section>
  </div>
</template>
