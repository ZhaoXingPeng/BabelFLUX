<script setup lang="ts">
import { computed, ref } from "vue";
import { storeToRefs } from "pinia";
import { useRouter } from "vue-router";
import EndSessionDialog from "../components/workflow/EndSessionDialog.vue";
import SettingsDialog from "../components/settings/SettingsDialog.vue";
import MediaPanel from "../components/workbench/MediaPanel.vue";
import SetupBackdrop from "../components/workbench/SetupBackdrop.vue";
import SubtitleColumn from "../components/workbench/SubtitleColumn.vue";
import { withFlipMode } from "../composables/useFlipMode";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const sessionStore = useSessionStore();
const root = ref<HTMLElement | null>(null);
const settingsOpen = ref(false);

const {
  displayModes,
  domains,
  endingMode,
  errorMessage,
  audioUrl,
  floatingForm,
  isLive,
  mediaUrl,
  mediaKind,
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

const shouldShowSettings = computed(
  () => settingsOpen.value || modeStates.value.quick === "setup" || modeStates.value.quick === "error"
);

async function startQuickSession() {
  await sessionStore.startMode("quick");
  settingsOpen.value = false;
}

async function setDisplayMode(mode: string) {
  if (selectedDisplayMode.value === mode) return;
  await withFlipMode(root, ".media-panel, .subtitle-column", () => {
    selectedDisplayMode.value = mode;
  });
}
</script>

<template>
  <main ref="root" class="workbench-shell" :class="{ live: isLive }">
    <SetupBackdrop v-if="!isLive" />

    <template v-if="isLive">
    <header class="workbench-topbar">
      <button class="topbar-link" type="button" @click="router.push('/')">返回主屏</button>
      <div>
        <p>LingoSync Web</p>
        <strong>沉浸式同传工作台</strong>
      </div>
      <button
        v-if="selectedDisplayMode === '悬浮字幕'"
        class="topbar-link"
        type="button"
        @click="setDisplayMode('逐句对照')"
      >
        展开字幕栏
      </button>
      <button v-else class="topbar-link" type="button" @click="settingsOpen = true">同传设置</button>
    </header>

    <p v-if="errorMessage" class="workbench-error">{{ errorMessage }}</p>

    <section class="workbench-grid" :class="{ floating: selectedDisplayMode === '悬浮字幕' }">
      <MediaPanel
        :form="quickForm"
        :floating-form="floatingForm"
        :state="modeStates.quick"
        :source="quickSource"
        :runtime-status="status"
        :ws-connected="wsConnected"
        :source-sync-state="sourceSyncState"
        :media-url="mediaUrl"
        :audio-url="audioUrl"
        :media-kind="mediaKind"
        :current-pair="currentPair"
        :selected-display-mode="selectedDisplayMode"
        @pause="sessionStore.pauseMode('quick')"
        @resume="sessionStore.resumeMode('quick')"
        @end="sessionStore.askEnd('quick')"
        @reset="sessionStore.resetMode('quick')"
        @open-settings="settingsOpen = true"
        @open-desktop="sessionStore.openDesktopFloating"
        @expand-subtitles="setDisplayMode('逐句对照')"
        @sync-playback="sessionStore.syncFixturePlayback"
      />
      <SubtitleColumn
        v-if="selectedDisplayMode !== '悬浮字幕'"
        :display-modes="displayModes"
        :selected-display-mode="selectedDisplayMode"
        :selected-display-description="selectedDisplayDescription"
        :pairs="transcriptPairs"
        @update-display-mode="setDisplayMode"
      />
    </section>

    <section v-if="modeStates.quick === 'report'" class="report-panel">
      <div>
        <p>Session report</p>
        <h2>会议报告</h2>
      </div>
      <div class="report-grid">
        <article v-for="metric in reportMetrics" :key="metric.label">
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
        </article>
      </div>
      <div class="report-actions">
        <button class="secondary-button compact-button" type="button">TXT</button>
        <button class="secondary-button compact-button" type="button">SRT</button>
        <button class="secondary-button compact-button" type="button">MD</button>
      </div>
    </section>
    </template>

    <SettingsDialog
      v-if="shouldShowSettings"
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
      @close="settingsOpen = false"
      @start="startQuickSession"
      @select-source="sessionStore.selectQuickSource"
      @select-file="sessionStore.setQuickSourceFile"
      @update-url="sessionStore.updateQuickSourceUrl"
      @request-permission="sessionStore.requestQuickSourceAccess"
    />

    <EndSessionDialog
      v-if="showEndDialog"
      :mode="endingMode"
      @cancel="sessionStore.cancelEnd"
      @confirm="sessionStore.confirmEnd"
    />
  </main>
</template>
