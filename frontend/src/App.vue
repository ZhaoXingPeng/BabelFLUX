<script setup lang="ts">
import { storeToRefs } from "pinia";
import EndSessionDialog from "./components/workflow/EndSessionDialog.vue";
import QuickSetupPanel from "./components/workflow/QuickSetupPanel.vue";
import QuickWorkspace from "./components/workflow/QuickWorkspace.vue";
import { useSessionStore } from "./stores/session";

const sessionStore = useSessionStore();
const {
  displayModes,
  domains,
  endingMode,
  errorMessage,
  languages,
  modeStates,
  modelProfiles,
  quickCanStart,
  quickForm,
  quickInput,
  quickSource,
  quickSources,
  quickStatusLabel,
  quickUrlError,
  reportMetrics,
  selectedDisplayDescription,
  selectedDisplayMode,
  showEndDialog,
  sourceSyncState,
  status,
  targetLanguages,
  transcriptPairs,
  currentPair,
  wsConnected
} = storeToRefs(sessionStore);
</script>

<template>
  <main class="min-h-screen bg-[#f4f6f4] text-[#17212b]">
    <header class="border-b border-[#d7ddd8] bg-white">
      <div class="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p class="text-xs font-semibold text-[#607064]">AI 同声传译助手</p>
          <h1 class="mt-1 text-2xl font-bold text-[#17212b]">实时同传工作台</h1>
        </div>
        <button class="secondary-button compact-button" type="button" @click="sessionStore.openDesktopFloating">
          启动客户端悬浮
        </button>
      </div>
    </header>

    <section
      class="mx-auto grid max-w-7xl gap-4 px-4 py-4"
      :class="modeStates.quick === 'setup' || modeStates.quick === 'error' || modeStates.quick === 'report' ? 'lg:grid-cols-[348px_minmax(0,1fr)]' : 'lg:grid-cols-1'"
    >
      <QuickSetupPanel
        v-if="modeStates.quick === 'setup' || modeStates.quick === 'error' || modeStates.quick === 'report'"
        :form="quickForm"
        :state="modeStates.quick"
        :status-label="quickStatusLabel"
        :domains="domains"
        :languages="languages"
        :target-languages="targetLanguages"
        :model-profiles="modelProfiles"
        :sources="quickSources"
        :selected-source="quickSource"
        :input="quickInput"
        :url-error="quickUrlError"
        :can-start="quickCanStart"
        @start="sessionStore.startMode('quick')"
        @select-source="sessionStore.selectQuickSource"
        @select-file="sessionStore.setQuickSourceFile"
        @update-url="sessionStore.updateQuickSourceUrl"
        @request-permission="sessionStore.requestQuickSourceAccess"
      />
      <QuickWorkspace
        :form="quickForm"
        :state="modeStates.quick"
        :source="quickSource"
        :runtime-status="status"
        :ws-connected="wsConnected"
        :source-sync-state="sourceSyncState"
        :error-message="errorMessage"
        :display-modes="displayModes"
        :selected-display-mode="selectedDisplayMode"
        :selected-display-description="selectedDisplayDescription"
        :current-pair="currentPair"
        :transcript-pairs="transcriptPairs"
        :report-metrics="reportMetrics"
        @pause="sessionStore.pauseMode('quick')"
        @resume="sessionStore.resumeMode('quick')"
        @end="sessionStore.askEnd('quick')"
        @reset="sessionStore.resetMode('quick')"
        @update-display-mode="selectedDisplayMode = $event"
      />
    </section>

    <EndSessionDialog
      v-if="showEndDialog"
      :mode="endingMode"
      @cancel="sessionStore.cancelEnd"
      @confirm="sessionStore.confirmEnd"
    />
  </main>
</template>
