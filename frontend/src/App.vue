<script setup lang="ts">
import { storeToRefs } from "pinia";
import { computed, reactive, ref } from "vue";
import EndSessionDialog from "./components/workflow/EndSessionDialog.vue";
import FloatingSetupPanel from "./components/workflow/FloatingSetupPanel.vue";
import FloatingSubtitlePreview from "./components/workflow/FloatingSubtitlePreview.vue";
import ModeSwitch from "./components/workflow/ModeSwitch.vue";
import QuickSetupPanel from "./components/workflow/QuickSetupPanel.vue";
import QuickWorkspace from "./components/workflow/QuickWorkspace.vue";
import { useSessionStore } from "./stores/session";
import type {
  FloatingFormState,
  ProductMode,
  ProductModeOption,
  QuickFormState,
  ReportMetric,
  RuntimeState,
  SourceOption,
  TranscriptPair,
  WorkspaceTile
} from "./components/workflow/types";

const sessionStore = useSessionStore();
const { errorMessage, revisions, sourceSegments, sourceSyncState, status, translationSegments, wsConnected } =
  storeToRefs(sessionStore);

const productMode = ref<ProductMode>("quick");
const activeMode = ref<ProductMode | null>(null);
const endingMode = ref<ProductMode | null>(null);
const showEndDialog = ref(false);
const selectedDisplayMode = ref("逐句对照");
const modeStates = reactive<Record<ProductMode, RuntimeState>>({
  quick: "setup",
  floating: "setup"
});

const quickForm = reactive<QuickFormState>({
  name: "国际技术分享同传",
  domain: "技术",
  sourceLanguage: "英语",
  targetLanguage: "中文",
  modelProfile: "智能默认",
  source: "video-file"
});

const floatingForm = reactive<FloatingFormState>({
  domain: "通用",
  sourceLanguage: "自动检测",
  targetLanguage: "中文",
  modelProfile: "快速低延迟",
  source: "browser-tab",
  style: "双语字幕",
  size: "标准",
  opacity: "90%"
});

const productModes: ProductModeOption[] = [
  { key: "quick", label: "快速同传", description: "完整工作台" },
  { key: "floating", label: "悬浮字幕", description: "轻量字幕层" }
];

const modelProfiles = ["智能默认", "快速低延迟", "高准确", "成本优先", "指定供应商"];
const domains = ["通用", "技术", "商务", "教育", "医疗", "法律", "自定义术语表"];
const languages = ["自动检测", "英语", "中文", "日语", "韩语", "法语", "德语"];
const targetLanguages = ["中文", "英语", "日语", "韩语"];
const displayModes = ["分区对照", "转写翻译", "分区显示", "逐句对照", "按句分段", "语意清晰"];
const displayModeCopy: Record<string, string> = {
  分区对照: "原文和译文分栏审阅",
  转写翻译: "按时间流展示处理过程",
  分区显示: "媒体、转写、翻译和修正分屏",
  逐句对照: "一句原文对应一句译文",
  按句分段: "严格句级段落，适合字幕导出",
  语意清晰: "按语义块聚合，译文更自然"
};

const quickSources: SourceOption[] = [
  { key: "video-file", label: "视频文件", channel: "mp4 / mov / webm", availability: "web" },
  { key: "audio-file", label: "音频文件", channel: "mp3 / wav / m4a", availability: "web" },
  { key: "url", label: "URL", channel: "网页视频或直播链接", availability: "web" },
  { key: "microphone", label: "麦克风", channel: "外放或线下讲座兜底", availability: "web" },
  { key: "browser-tab", label: "浏览器标签页音频", channel: "网课、网页视频", availability: "web" },
  { key: "screen-window", label: "屏幕或窗口", channel: "浏览器权限能力", availability: "web" },
  { key: "system-audio", label: "系统音频", channel: "桌面端能力", availability: "desktop", disabled: true }
];

const floatingSources: SourceOption[] = [
  { key: "microphone", label: "麦克风", channel: "外放或会议室", availability: "web" },
  { key: "browser-tab", label: "浏览器标签页音频", channel: "网页视频和网课", availability: "web" },
  { key: "screen-window", label: "屏幕或窗口音频", channel: "浏览器权限能力", availability: "web" },
  { key: "system-audio", label: "系统音频", channel: "桌面端能力", availability: "desktop", disabled: true }
];

const samplePairs: TranscriptPair[] = [
  {
    time: "00:00:04",
    source: "Today we are going to talk about real-time AI translation.",
    translation: "今天我们要讨论实时 AI 翻译。",
    state: "final"
  },
  {
    time: "00:00:11",
    source: "The system should balance latency, accuracy and stability.",
    translation: "系统需要在延迟、准确率和稳定性之间取得平衡。",
    state: "translated"
  },
  {
    time: "00:00:18",
    source: "When more context arrives, earlier subtitles can be revised.",
    translation: "当后续上下文到达时，前面的字幕可以被自动修正。",
    state: "revised"
  }
];

const transcriptPairs = computed<TranscriptPair[]>(() => {
  if (sourceSegments.value.length === 0 && translationSegments.value.length === 0) return samplePairs;

  const maxLength = Math.max(sourceSegments.value.length, translationSegments.value.length);
  return Array.from({ length: maxLength }, (_, index) => {
    const source = sourceSegments.value[index];
    const translation = translationSegments.value[index];
    return {
      time: source ? `${Math.round(source.startMs / 1000)}s` : "--",
      source: source?.text ?? "等待源语言转写...",
      translation: translation?.text ?? "等待译文...",
      state: translation?.status ?? source?.status ?? "partial"
    };
  });
});

const currentPair = computed(() => transcriptPairs.value[transcriptPairs.value.length - 1] ?? samplePairs[0]);
const quickSource = computed(() => quickSources.find((source) => source.key === quickForm.source) ?? quickSources[0]);
const floatingSource = computed(
  () => floatingSources.find((source) => source.key === floatingForm.source) ?? floatingSources[0]
);
const quickStatusLabel = computed(() => formatRuntimeState(modeStates.quick));
const floatingStatusLabel = computed(() => formatRuntimeState(modeStates.floating));
const selectedDisplayDescription = computed(() => displayModeCopy[selectedDisplayMode.value]);
const quickCanStart = computed(() => modeStates.quick !== "connecting" && !quickSource.value.disabled);
const floatingCanStart = computed(() => modeStates.floating !== "connecting" && !floatingSource.value.disabled);

const workspaceTiles = computed<WorkspaceTile[]>(() => [
  { label: "源文实时转写", value: currentPair.value.source },
  { label: "译文实时输出", value: currentPair.value.translation },
  {
    label: "修正记录",
    value: revisions.value[0]
      ? `${revisions.value[0].beforeText} -> ${revisions.value[0].afterText}`
      : "等待修正事件"
  },
  { label: "术语与摘要", value: "AI translation · 实时 AI 翻译 · 术语命中" }
]);

const reportMetrics = computed<ReportMetric[]>(() => [
  { label: "时长", value: "18:24" },
  { label: "语言", value: `${quickForm.sourceLanguage} -> ${quickForm.targetLanguage}` },
  { label: "修正", value: `${revisions.value.length || 1} 条` },
  { label: "导出", value: "TXT / SRT / MD" }
]);

function formatRuntimeState(state: RuntimeState): string {
  const labels: Record<RuntimeState, string> = {
    setup: "待开始",
    connecting: "连接中",
    running: "运行中",
    paused: "已暂停",
    report: "已生成报告",
    error: "启动失败"
  };
  return labels[state];
}

function selectMode(mode: ProductMode) {
  productMode.value = mode;
}

function selectQuickSource(source: SourceOption) {
  if (!source.disabled) quickForm.source = source.key;
}

function selectFloatingSource(source: SourceOption) {
  if (!source.disabled) floatingForm.source = source.key;
}

async function startMode(mode: ProductMode) {
  const blockedSource = mode === "quick" ? quickSource.value.disabled : floatingSource.value.disabled;
  if (blockedSource || modeStates[mode] === "connecting") return;

  const previousMode = activeMode.value;
  if (previousMode && previousMode !== mode) {
    modeStates[previousMode] = "setup";
    sessionStore.stopSession("idle");
  }

  activeMode.value = mode;
  productMode.value = mode;
  modeStates.quick = mode === "quick" ? "connecting" : "setup";
  modeStates.floating = mode === "floating" ? "connecting" : "setup";

  const started = await sessionStore.startDemoSession();
  if (activeMode.value !== mode) return;

  if (started) {
    modeStates[mode] = "running";
  } else {
    modeStates[mode] = "error";
    activeMode.value = null;
  }
}

function pauseMode(mode: ProductMode) {
  if (activeMode.value !== mode || modeStates[mode] !== "running") return;
  modeStates[mode] = "paused";
  sessionStore.pauseSession();
}

function resumeMode(mode: ProductMode) {
  if (activeMode.value !== mode || modeStates[mode] !== "paused") return;
  modeStates[mode] = "running";
  sessionStore.resumeSession();
}

function askEnd(mode: ProductMode) {
  endingMode.value = mode;
  showEndDialog.value = true;
}

function cancelEnd() {
  showEndDialog.value = false;
  endingMode.value = null;
}

function confirmEnd() {
  if (!endingMode.value) return;
  modeStates[endingMode.value] = "report";
  if (activeMode.value === endingMode.value) activeMode.value = null;
  showEndDialog.value = false;
  endingMode.value = null;
  sessionStore.stopSession("stopped");
}

function resetMode(mode: ProductMode) {
  if (activeMode.value === mode) {
    activeMode.value = null;
    sessionStore.stopSession("idle");
    sessionStore.resetSessionData();
  }
  modeStates[mode] = "setup";
}
</script>

<template>
  <main class="min-h-screen bg-[#f4f6f4] text-[#17212b]">
    <header class="border-b border-[#d7ddd8] bg-white">
      <div class="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p class="text-xs font-semibold text-[#607064]">AI 同声传译助手</p>
          <h1 class="mt-1 text-2xl font-bold text-[#17212b]">实时同传工作台</h1>
        </div>
        <ModeSwitch :modes="productModes" :selected-mode="productMode" @select="selectMode" />
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
        @start="startMode('quick')"
        @switch-floating="selectMode('floating')"
        @select-source="selectQuickSource"
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
        @pause="pauseMode('quick')"
        @resume="resumeMode('quick')"
        @end="askEnd('quick')"
        @reset="resetMode('quick')"
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
        @start="startMode('floating')"
        @switch-quick="selectMode('quick')"
        @select-source="selectFloatingSource"
      />
      <FloatingSubtitlePreview
        :form="floatingForm"
        :state="modeStates.floating"
        :source="floatingSource"
        :status-label="floatingStatusLabel"
        :current-pair="currentPair"
        @pause="pauseMode('floating')"
        @resume="resumeMode('floating')"
        @end="askEnd('floating')"
        @reset="resetMode('floating')"
      />
    </section>

    <EndSessionDialog
      v-if="showEndDialog"
      :mode="endingMode"
      @cancel="cancelEnd"
      @confirm="confirmEnd"
    />
  </main>
</template>
