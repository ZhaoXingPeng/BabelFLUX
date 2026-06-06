<script setup lang="ts">
import { computed, ref } from "vue";
import { storeToRefs } from "pinia";
import { useRouter } from "vue-router";
import Icon from "../components/icons/Icon.vue";
import EndSessionDialog from "../components/workflow/EndSessionDialog.vue";
import SettingsDialog from "../components/settings/SettingsDialog.vue";
import DesktopLaunchPrompt from "../components/workbench/DesktopLaunchPrompt.vue";
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
  desktopDownloadPromptOpen,
  desktopHandoffUrl,
  desktopLaunchMessage,
  desktopLaunchState,
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
  report,
  reportLoading,
  reportError,
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

function returnHome() {
  // 返回主屏即结束本次任务：清掉报告/字幕/进度并回到待开始态，
  // 下次进入工作台就是一次全新的同传任务，而不是停留在上一次的报告界面。
  sessionStore.resetMode("quick");
  settingsOpen.value = false;
  router.push("/");
}

async function setDisplayMode(mode: string) {
  if (selectedDisplayMode.value === mode) return;
  await withFlipMode(root, ".media-panel, .subtitle-column", () => {
    selectedDisplayMode.value = mode;
  });
}

function toggleFloatingCaptions() {
  setDisplayMode(selectedDisplayMode.value === "悬浮字幕" ? "逐句对照" : "悬浮字幕");
}
</script>

<template>
  <main ref="root" class="workbench-shell" :class="{ live: isLive }">
    <SetupBackdrop v-if="!isLive && !shouldShowSettings" />

    <template v-if="isLive">
    <header class="workbench-topbar">
      <button class="topbar-link" type="button" @click="returnHome">返回主屏</button>
      <div>
        <p>BabelFlux Web</p>
        <strong>沉浸式同传工作台</strong>
      </div>
      <button class="topbar-link icon-link" type="button" @click="settingsOpen = true">
        <Icon name="sliders-horizontal" :size="16" />
        <span>同传设置</span>
      </button>
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
        :desktop-launch-state="desktopLaunchState"
        :desktop-launch-message="desktopLaunchMessage"
        :selected-display-mode="selectedDisplayMode"
        @end="sessionStore.askEnd('quick')"
        @reset="sessionStore.resetMode('quick')"
        @open-desktop="sessionStore.openDesktopFloating"
        @toggle-floating-captions="toggleFloatingCaptions"
        @media-ready="sessionStore.setMediaElement"
        @sync-playback="sessionStore.syncPlayback"
        @playback-pause="sessionStore.handleMediaPlaybackPaused"
        @playback-play="sessionStore.handleMediaPlaybackPlayed"
        @ended="sessionStore.handleFixtureEnded"
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
        <h2>同传报告</h2>
      </div>
      <div class="report-grid">
        <article v-for="metric in reportMetrics" :key="metric.label">
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
        </article>
      </div>
      <p v-if="reportLoading" class="report-summary report-summary-loading">
        正在生成会后完整纠偏报告…
      </p>
      <p v-else-if="reportError" class="report-summary report-summary-error">{{ reportError }}</p>
      <p v-else-if="report?.summary" class="report-summary">{{ report.summary }}</p>
      <div class="report-actions">
        <button
          class="secondary-button compact-button"
          type="button"
          :disabled="reportLoading"
          @click="sessionStore.downloadReport('txt')"
        >
          TXT
        </button>
        <button
          class="secondary-button compact-button"
          type="button"
          :disabled="reportLoading"
          @click="sessionStore.downloadReport('srt')"
        >
          SRT
        </button>
        <button
          class="secondary-button compact-button"
          type="button"
          :disabled="reportLoading"
          @click="sessionStore.downloadReport('md')"
        >
          MD
        </button>
        <button
          class="secondary-button compact-button"
          type="button"
          :disabled="reportLoading"
          @click="sessionStore.downloadReport('json')"
        >
          JSON
        </button>
      </div>
    </section>
    </template>

    <DesktopLaunchPrompt
      v-if="desktopDownloadPromptOpen"
      :state="desktopLaunchState"
      :message="desktopLaunchMessage"
      :deep-link-url="desktopHandoffUrl"
      @retry="sessionStore.openDesktopFloating"
      @reopen="sessionStore.reopenDesktop"
      @continue-web="sessionStore.continueWithWebFloating"
      @close="sessionStore.dismissDesktopDownloadPrompt"
    />

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
