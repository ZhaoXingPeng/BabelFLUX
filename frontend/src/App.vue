<script setup lang="ts">
import { storeToRefs } from "pinia";
import { computed, reactive, ref } from "vue";
import { useSessionStore } from "./stores/session";

type ProductMode = "quick" | "floating";
type RuntimeState = "setup" | "connecting" | "running" | "paused" | "report" | "error";

interface SourceOption {
  key: string;
  label: string;
  channel: string;
  availability: "web" | "desktop";
  disabled?: boolean;
}

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

const quickForm = reactive({
  name: "国际技术分享同传",
  domain: "技术",
  sourceLanguage: "英语",
  targetLanguage: "中文",
  modelProfile: "智能默认",
  source: "video-file"
});

const floatingForm = reactive({
  domain: "通用",
  sourceLanguage: "自动检测",
  targetLanguage: "中文",
  modelProfile: "快速低延迟",
  source: "browser-tab",
  style: "双语字幕",
  size: "标准",
  opacity: "90%"
});

const productModes = [
  { key: "quick" as ProductMode, label: "快速同传", description: "完整工作台" },
  { key: "floating" as ProductMode, label: "悬浮字幕", description: "轻量字幕层" }
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
  {
    key: "system-audio",
    label: "系统音频",
    channel: "桌面端能力",
    availability: "desktop",
    disabled: true
  }
];

const floatingSources: SourceOption[] = [
  { key: "microphone", label: "麦克风", channel: "外放或会议室", availability: "web" },
  { key: "browser-tab", label: "浏览器标签页音频", channel: "网页视频和网课", availability: "web" },
  { key: "screen-window", label: "屏幕或窗口音频", channel: "浏览器权限能力", availability: "web" },
  {
    key: "system-audio",
    label: "系统音频",
    channel: "桌面端能力",
    availability: "desktop",
    disabled: true
  }
];

const samplePairs = [
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

const transcriptPairs = computed(() => {
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

const workspaceTiles = computed(() => [
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

const reportMetrics = computed(() => [
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

        <div class="grid gap-2 sm:grid-cols-2">
          <button
            v-for="mode in productModes"
            :key="mode.key"
            class="min-w-[180px] rounded-lg border px-4 py-3 text-left transition"
            :class="
              productMode === mode.key
                ? 'border-[#1c7c54] bg-[#e7f4ec] text-[#12462f]'
                : 'border-[#d7ddd8] bg-white text-[#4a5a50] hover:border-[#8bb89b]'
            "
            type="button"
            @click="selectMode(mode.key)"
          >
            <span class="block text-sm font-bold">{{ mode.label }}</span>
            <span class="mt-1 block text-xs">{{ mode.description }}</span>
          </button>
        </div>
      </div>
    </header>

    <section
      v-if="productMode === 'quick'"
      class="mx-auto grid max-w-7xl gap-4 px-4 py-4 lg:grid-cols-[348px_minmax(0,1fr)]"
    >
      <aside class="rounded-lg border border-[#d7ddd8] bg-white p-4">
        <div class="flex items-center justify-between gap-3">
          <h2 class="text-base font-bold">快速同传设置</h2>
          <span class="rounded-md bg-[#eef1ee] px-2 py-1 text-xs text-[#526057]">{{ quickStatusLabel }}</span>
        </div>

        <div class="mt-4 grid grid-cols-3 gap-2">
          <div class="flow-step" :class="{ active: modeStates.quick === 'setup' }">配置</div>
          <div
            class="flow-step"
            :class="{ active: modeStates.quick === 'connecting' || modeStates.quick === 'running' || modeStates.quick === 'paused' }"
          >
            同传
          </div>
          <div class="flow-step" :class="{ active: modeStates.quick === 'report' }">复盘</div>
        </div>

        <div class="mt-4 space-y-4">
          <label class="block">
            <span class="form-label">会话名称</span>
            <input v-model="quickForm.name" class="form-control" type="text" />
          </label>

          <label class="block">
            <span class="form-label">专业领域</span>
            <select v-model="quickForm.domain" class="form-control">
              <option v-for="domain in domains" :key="domain">{{ domain }}</option>
            </select>
          </label>

          <div class="grid grid-cols-2 gap-3">
            <label class="block">
              <span class="form-label">源语言</span>
              <select v-model="quickForm.sourceLanguage" class="form-control">
                <option v-for="language in languages" :key="language">{{ language }}</option>
              </select>
            </label>
            <label class="block">
              <span class="form-label">目标语言</span>
              <select v-model="quickForm.targetLanguage" class="form-control">
                <option v-for="language in targetLanguages" :key="language">{{ language }}</option>
              </select>
            </label>
          </div>

          <label class="block">
            <span class="form-label">模型选择</span>
            <select v-model="quickForm.modelProfile" class="form-control">
              <option v-for="profile in modelProfiles" :key="profile">{{ profile }}</option>
            </select>
          </label>

          <div>
            <span class="form-label">输入声源</span>
            <div class="mt-2 grid gap-2">
              <button
                v-for="source in quickSources"
                :key="source.key"
                class="source-card"
                :class="{ selected: quickForm.source === source.key, disabled: source.disabled }"
                :disabled="source.disabled"
                type="button"
                @click="selectQuickSource(source)"
              >
                <span class="font-bold">{{ source.label }}</span>
                <span>{{ source.channel }}</span>
                <strong>{{ source.availability === "web" ? "Web" : "桌面端" }}</strong>
              </button>
            </div>
          </div>
        </div>

        <div class="mt-5 grid gap-2">
          <button class="primary-button" type="button" :disabled="!quickCanStart" @click="startMode('quick')">
            {{ modeStates.quick === "connecting" ? "连接中" : "开始同传" }}
          </button>
          <button class="secondary-button" type="button" @click="selectMode('floating')">
            切到悬浮字幕
          </button>
        </div>
      </aside>

      <section class="grid gap-4">
        <div class="rounded-lg border border-[#d7ddd8] bg-white p-4">
          <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p class="text-xs text-[#607064]">
                {{ quickForm.name }} · {{ quickForm.sourceLanguage }} -> {{ quickForm.targetLanguage }}
              </p>
              <h2 class="mt-1 text-xl font-bold">快速同传工作台</h2>
            </div>
            <div class="flex flex-wrap gap-2">
              <span class="status-pill">{{ status }}</span>
              <span class="status-pill">{{ wsConnected ? "WebSocket 已连接" : "WebSocket 未连接" }}</span>
              <span class="status-pill">{{ sourceSyncState.status }} · {{ sourceSyncState.lagMs }}ms</span>
            </div>
          </div>

          <p v-if="errorMessage" class="mt-3 rounded-md border border-[#d96b6b] bg-[#fff0f0] px-3 py-2 text-sm text-[#a13d3d]">
            {{ errorMessage }}
          </p>

          <div class="mt-4 flex flex-wrap gap-2">
            <button
              v-if="modeStates.quick === 'running'"
              class="secondary-button compact-button"
              type="button"
              @click="pauseMode('quick')"
            >
              暂停
            </button>
            <button
              v-if="modeStates.quick === 'paused'"
              class="primary-button compact-button"
              type="button"
              @click="resumeMode('quick')"
            >
              继续
            </button>
            <button
              v-if="modeStates.quick !== 'setup' && modeStates.quick !== 'report'"
              class="danger-button compact-button"
              type="button"
              @click="askEnd('quick')"
            >
              结束
            </button>
            <button v-if="modeStates.quick === 'report'" class="secondary-button compact-button" type="button" @click="resetMode('quick')">
              新建同传
            </button>
          </div>
        </div>

        <div class="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.75fr)]">
          <section class="rounded-lg border border-[#d7ddd8] bg-white p-4">
            <div class="media-stage">
              <div>
                <p class="text-sm text-[#d8e0da]">{{ quickSource.label }} · {{ quickForm.modelProfile }}</p>
                <p class="mt-2 text-2xl font-bold text-white">视频 / 音频展示区</p>
                <p class="mt-3 max-w-xl text-sm leading-6 text-[#bec9c2]">
                  {{ currentPair.source }}
                </p>
              </div>
              <div class="media-caption">
                {{ currentPair.translation }}
              </div>
            </div>

            <div class="mt-4 grid gap-3 md:grid-cols-2">
              <div v-for="tile in workspaceTiles" :key="tile.label" class="workspace-tile">
                <p class="tile-label">{{ tile.label }}</p>
                <p class="tile-text">{{ tile.value }}</p>
              </div>
            </div>
          </section>

          <section class="rounded-lg border border-[#d7ddd8] bg-white p-4">
            <div class="flex items-start justify-between gap-3">
              <div>
                <h3 class="font-bold">同传显示</h3>
                <p class="mt-1 text-xs text-[#607064]">{{ selectedDisplayDescription }}</p>
              </div>
              <span class="rounded-md bg-[#fff4df] px-2 py-1 text-xs text-[#7a4c00]">{{ selectedDisplayMode }}</span>
            </div>

            <div class="mt-3 grid grid-cols-2 gap-2">
              <button
                v-for="mode in displayModes"
                :key="mode"
                class="rounded-md border px-2 py-2 text-sm"
                :class="
                  selectedDisplayMode === mode
                    ? 'border-[#245eaa] bg-[#e9f1ff] text-[#17457c]'
                    : 'border-[#d7ddd8] bg-white text-[#4a5a50]'
                "
                type="button"
                @click="selectedDisplayMode = mode"
              >
                {{ mode }}
              </button>
            </div>

            <div class="mt-4 max-h-[520px] space-y-3 overflow-auto pr-1">
              <article v-for="pair in transcriptPairs" :key="`${pair.time}-${pair.source}`" class="transcript-row">
                <div class="flex items-center justify-between gap-2">
                  <span class="text-xs text-[#69776e]">{{ pair.time }}</span>
                  <span class="rounded-md bg-[#eef1ee] px-2 py-1 text-xs text-[#526057]">{{ pair.state }}</span>
                </div>
                <p class="mt-2 text-sm leading-6 text-[#4a5a50]">{{ pair.source }}</p>
                <p class="mt-2 text-base font-semibold leading-7 text-[#17212b]">{{ pair.translation }}</p>
              </article>
            </div>
          </section>
        </div>

        <section v-if="modeStates.quick === 'report'" class="rounded-lg border border-[#d7ddd8] bg-white p-4">
          <div class="flex items-center justify-between gap-3">
            <h3 class="font-bold">会议报告</h3>
            <div class="flex gap-2">
              <button class="secondary-button compact-button" type="button">TXT</button>
              <button class="secondary-button compact-button" type="button">SRT</button>
              <button class="secondary-button compact-button" type="button">MD</button>
            </div>
          </div>
          <div class="mt-3 grid gap-3 md:grid-cols-4">
            <div v-for="metric in reportMetrics" :key="metric.label" class="report-metric">
              <span>{{ metric.label }}</span>
              <strong>{{ metric.value }}</strong>
            </div>
          </div>
        </section>
      </section>
    </section>

    <section v-else class="mx-auto grid max-w-7xl gap-4 px-4 py-4 lg:grid-cols-[360px_minmax(0,1fr)]">
      <aside class="rounded-lg border border-[#d7ddd8] bg-white p-4">
        <div class="flex items-center justify-between gap-3">
          <h2 class="text-base font-bold">悬浮字幕设置</h2>
          <span class="rounded-md bg-[#eef1ee] px-2 py-1 text-xs text-[#526057]">{{ floatingStatusLabel }}</span>
        </div>

        <div class="mt-4 grid grid-cols-3 gap-2">
          <div class="flow-step" :class="{ active: modeStates.floating === 'setup' }">配置</div>
          <div
            class="flow-step"
            :class="{ active: modeStates.floating === 'connecting' || modeStates.floating === 'running' || modeStates.floating === 'paused' }"
          >
            字幕
          </div>
          <div class="flow-step" :class="{ active: modeStates.floating === 'report' }">记录</div>
        </div>

        <div class="mt-4 space-y-4">
          <label class="block">
            <span class="form-label">模型选择</span>
            <select v-model="floatingForm.modelProfile" class="form-control">
              <option v-for="profile in modelProfiles" :key="profile">{{ profile }}</option>
            </select>
          </label>

          <div class="grid grid-cols-2 gap-3">
            <label class="block">
              <span class="form-label">源语言</span>
              <select v-model="floatingForm.sourceLanguage" class="form-control">
                <option v-for="language in languages" :key="language">{{ language }}</option>
              </select>
            </label>
            <label class="block">
              <span class="form-label">目标语言</span>
              <select v-model="floatingForm.targetLanguage" class="form-control">
                <option v-for="language in targetLanguages" :key="language">{{ language }}</option>
              </select>
            </label>
          </div>

          <label class="block">
            <span class="form-label">专业领域</span>
            <select v-model="floatingForm.domain" class="form-control">
              <option v-for="domain in domains" :key="domain">{{ domain }}</option>
            </select>
          </label>

          <div>
            <span class="form-label">声源</span>
            <div class="mt-2 grid gap-2">
              <button
                v-for="source in floatingSources"
                :key="source.key"
                class="source-card"
                :class="{ selected: floatingForm.source === source.key, disabled: source.disabled }"
                :disabled="source.disabled"
                type="button"
                @click="selectFloatingSource(source)"
              >
                <span class="font-bold">{{ source.label }}</span>
                <span>{{ source.channel }}</span>
                <strong>{{ source.availability === "web" ? "Web" : "桌面端" }}</strong>
              </button>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <label class="block">
              <span class="form-label">字幕样式</span>
              <select v-model="floatingForm.style" class="form-control">
                <option>双语字幕</option>
                <option>仅译文</option>
                <option>原文优先</option>
              </select>
            </label>
            <label class="block">
              <span class="form-label">字号</span>
              <select v-model="floatingForm.size" class="form-control">
                <option>紧凑</option>
                <option>标准</option>
                <option>大号</option>
              </select>
            </label>
          </div>

          <label class="block">
            <span class="form-label">透明度</span>
            <select v-model="floatingForm.opacity" class="form-control">
              <option>70%</option>
              <option>80%</option>
              <option>90%</option>
              <option>100%</option>
            </select>
          </label>
        </div>

        <div class="mt-5 grid gap-2">
          <button class="primary-button" type="button" :disabled="!floatingCanStart" @click="startMode('floating')">
            {{ modeStates.floating === "connecting" ? "连接中" : "开始使用" }}
          </button>
          <button class="secondary-button" type="button" @click="selectMode('quick')">
            返回快速同传
          </button>
        </div>
      </aside>

      <section class="relative min-h-[680px] rounded-lg border border-[#d7ddd8] bg-[#dfe4df] p-4">
        <div class="grid h-full grid-rows-[auto_minmax(0,1fr)] gap-4">
          <div class="rounded-lg border border-[#c9d1cb] bg-white p-4">
            <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p class="text-xs text-[#607064]">{{ floatingSource.label }} · {{ floatingForm.modelProfile }}</p>
                <h2 class="mt-1 text-xl font-bold">悬浮字幕运行窗</h2>
              </div>
              <div class="flex flex-wrap gap-2">
                <button class="secondary-button compact-button" type="button">锁定</button>
                <button class="secondary-button compact-button" type="button">A-</button>
                <button class="secondary-button compact-button" type="button">A+</button>
                <button class="secondary-button compact-button" type="button">设置</button>
                <button
                  v-if="modeStates.floating !== 'setup' && modeStates.floating !== 'report'"
                  class="danger-button compact-button"
                  type="button"
                  @click="askEnd('floating')"
                >
                  关闭
                </button>
              </div>
            </div>
          </div>

          <div class="relative rounded-lg border border-[#c9d1cb] bg-[#f8faf8] p-4">
            <div class="grid h-full place-items-center rounded-lg border border-dashed border-[#b7c1ba] bg-white">
              <div class="text-center">
                <p class="text-sm font-semibold text-[#607064]">浏览器字幕层</p>
                <p class="mt-2 text-lg font-bold text-[#17212b]">{{ floatingForm.style }} · {{ floatingForm.size }}</p>
              </div>
            </div>

            <div class="floating-window">
              <div class="flex items-center justify-between gap-3 border-b border-white/10 pb-2">
                <span>{{ floatingStatusLabel }}</span>
                <span>{{ floatingForm.sourceLanguage }} -> {{ floatingForm.targetLanguage }}</span>
              </div>
              <p class="mt-4 text-sm leading-6 text-white/72">{{ currentPair.source }}</p>
              <p class="mt-2 text-xl font-bold leading-8 text-white">{{ currentPair.translation }}</p>
              <div class="mt-4 flex justify-center gap-2">
                <button
                  v-if="modeStates.floating === 'running'"
                  class="floating-button"
                  type="button"
                  @click="pauseMode('floating')"
                >
                  暂停
                </button>
                <button
                  v-if="modeStates.floating === 'paused'"
                  class="floating-button"
                  type="button"
                  @click="resumeMode('floating')"
                >
                  继续
                </button>
                <button
                  v-if="modeStates.floating !== 'setup' && modeStates.floating !== 'report'"
                  class="floating-button danger"
                  type="button"
                  @click="askEnd('floating')"
                >
                  结束
                </button>
              </div>
            </div>
          </div>
        </div>

        <section v-if="modeStates.floating === 'report'" class="absolute inset-x-4 bottom-4 rounded-lg border border-[#d7ddd8] bg-white p-4">
          <div class="flex items-center justify-between gap-3">
            <div>
              <h3 class="font-bold">字幕记录</h3>
              <p class="mt-2 text-sm text-[#4a5a50]">已生成转写、译文、修正记录和导出入口。</p>
            </div>
            <button class="secondary-button compact-button" type="button" @click="resetMode('floating')">
              新建字幕
            </button>
          </div>
        </section>
      </section>
    </section>

    <div v-if="showEndDialog" class="fixed inset-0 z-50 grid place-items-center bg-black/40 px-4">
      <section class="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
        <h2 class="text-lg font-bold">结束本次{{ endingMode === "floating" ? "字幕" : "同传" }}？</h2>
        <p class="mt-3 text-sm leading-6 text-[#4a5a50]">
          结束后将停止识别和翻译，并生成本次转写、翻译和修正记录。
        </p>
        <div class="mt-5 grid grid-cols-2 gap-3">
          <button class="secondary-button" type="button" @click="cancelEnd">暂不结束</button>
          <button class="danger-button" type="button" @click="confirmEnd">结束会议</button>
        </div>
      </section>
    </div>
  </main>
</template>
