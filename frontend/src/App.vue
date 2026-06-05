<script setup lang="ts">
import { storeToRefs } from "pinia";
import EndSessionDialog from "./components/workflow/EndSessionDialog.vue";
import FloatingSetupPanel from "./components/workflow/FloatingSetupPanel.vue";
import FloatingSubtitlePreview from "./components/workflow/FloatingSubtitlePreview.vue";
import ModeSwitch from "./components/workflow/ModeSwitch.vue";
import QuickSetupPanel from "./components/workflow/QuickSetupPanel.vue";
import QuickWorkspace from "./components/workflow/QuickWorkspace.vue";
import { useSessionStore } from "./stores/session";

const sessionStore = useSessionStore();
const {
  displayModes,
  domains,
  endingMode,
  errorMessage,
  floatingCanStart,
  floatingForm,
  floatingSource,
  floatingSources,
  floatingStatusLabel,
  languages,
  modeStates,
  modelProfiles,
  productMode,
  productModes,
  quickCanStart,
  quickForm,
  quickSource,
  quickSources,
  quickStatusLabel,
  reportMetrics,
  selectedDisplayDescription,
  selectedDisplayMode,
  showEndDialog,
  sourceSyncState,
  status,
  targetLanguages,
  transcriptPairs,
  currentPair,
  workspaceTiles,
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
        <ModeSwitch
          :modes="productModes"
          :selected-mode="productMode"
          @select="sessionStore.selectMode"
        />
      </div>
    </header>

    <section
      v-if="productMode === 'quick'"
      class="mx-auto grid max-w-7xl gap-4 px-4 py-4 lg:grid-cols-[348px_minmax(0,1fr)]"
    >
      <QuickSetupPanel
        :form="quickForm"
        :state="modeStates.quick"
        :status-label="quickStatusLabel"
        :domains="domains"
        :languages="languages"
        :target-languages="targetLanguages"
        :model-profiles="modelProfiles"
        :sources="quickSources"
        :can-start="quickCanStart"
        @start="sessionStore.startMode('quick')"
        @switch-floating="sessionStore.selectMode('floating')"
        @select-source="sessionStore.selectQuickSource"
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
        :workspace-tiles="workspaceTiles"
        :report-metrics="reportMetrics"
        @pause="sessionStore.pauseMode('quick')"
        @resume="sessionStore.resumeMode('quick')"
        @end="sessionStore.askEnd('quick')"
        @reset="sessionStore.resetMode('quick')"
        @update-display-mode="selectedDisplayMode = $event"
      />
    </section>

    <section v-else class="mx-auto grid max-w-7xl gap-4 px-4 py-4 lg:grid-cols-[360px_minmax(0,1fr)]">
      <FloatingSetupPanel
        :form="floatingForm"
        :state="modeStates.floating"
        :status-label="floatingStatusLabel"
        :domains="domains"
        :languages="languages"
        :target-languages="targetLanguages"
        :model-profiles="modelProfiles"
        :sources="floatingSources"
        :can-start="floatingCanStart"
        @start="sessionStore.startMode('floating')"
        @switch-quick="sessionStore.selectMode('quick')"
        @select-source="sessionStore.selectFloatingSource"
      />
      <FloatingSubtitlePreview
        :form="floatingForm"
        :state="modeStates.floating"
        :source="floatingSource"
        :status-label="floatingStatusLabel"
        :current-pair="currentPair"
        @pause="sessionStore.pauseMode('floating')"
        @resume="sessionStore.resumeMode('floating')"
        @end="sessionStore.askEnd('floating')"
        @reset="sessionStore.resetMode('floating')"
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
