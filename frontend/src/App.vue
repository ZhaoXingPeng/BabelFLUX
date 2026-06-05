<script setup lang="ts">
import { storeToRefs } from "pinia";
import { computed, ref } from "vue";
import { useSessionStore } from "./stores/session";

type ProductMode = "quick" | "floating";
type RuntimeState = "setup" | "running" | "paused" | "report";
type EndTarget = ProductMode | null;

const sessionStore = useSessionStore();
const { errorMessage, revisions, sourceSegments, sourceSyncState, status, translationSegments, wsConnected } =
  storeToRefs(sessionStore);

const productMode = ref<ProductMode>("quick");
const quickState = ref<RuntimeState>("setup");
const floatingState = ref<RuntimeState>("setup");
const showEndDialog = ref(false);
const endTarget = ref<EndTarget>(null);

const quickForm = ref({
  name: "国际技术分享同传",
  domain: "技术",
  sourceLanguage: "英语",
  targetLanguage: "中文",
  modelProfile: "智能默认",
  source: "视频文件"
});

const floatingForm = ref({
  domain: "通用",
  sourceLanguage: "自动检测",
  targetLanguage: "中文",
  modelProfile: "快速低延迟",
  source: "浏览器标签页音频",
  style: "双语字幕"
});

const selectedDisplayMode = ref("逐句对照");

const productModes = [
  { key: "quick" as ProductMode, label: "快速同传", description: "完整工作台" },
  { key: "floating" as ProductMode, label: "悬浮字幕", description: "轻量字幕层" }
];

const modelProfiles = ["智能默认", "快速低延迟", "高准确", "成本优先", "指定供应商"];
const domains = ["通用", "技术", "商务", "教育", "医疗", "法律", "自定义术语表"];
const languages = ["自动检测", "英语", "中文", "日语", "韩语", "法语", "德语"];
const targetLanguages = ["中文", "英语", "日语", "韩语"];
const quickSources = ["视频文件", "音频文件", "URL", "麦克风", "浏览器标签页音频", "屏幕或窗口", "系统音频"];
const floatingSources = ["麦克风", "浏览器标签页音频", "屏幕或窗口音频", "系统音频"];
const displayModes = ["分区对照", "转写翻译", "分区显示", "逐句对照", "按句分段", "语意清晰"];

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

const quickStatusLabel = computed(() => {
  if (quickState.value === "running") return "同传运行中";
  if (quickState.value === "paused") return "已暂停";
  if (quickState.value === "report") return "已生成报告";
  return "待开始";
});

const floatingStatusLabel = computed(() => {
  if (floatingState.value === "running") return "字幕运行中";
  if (floatingState.value === "paused") return "字幕已暂停";
  if (floatingState.value === "report") return "记录已生成";
  return "待开始";
});

function selectMode(mode: ProductMode) {
  productMode.value = mode;
}

function startQuick() {
  quickState.value = "running";
  void sessionStore.startDemoSession();
}

function startFloating() {
  floatingState.value = "running";
  void sessionStore.startDemoSession();
}

function pauseQuick() {
  quickState.value = "paused";
}

function pauseFloating() {
  floatingState.value = "paused";
}

function resumeQuick() {
  quickState.value = "running";
}

function resumeFloating() {
  floatingState.value = "running";
}

function askEnd(target: ProductMode) {
  endTarget.value = target;
  showEndDialog.value = true;
}

function cancelEnd() {
  showEndDialog.value = false;
  endTarget.value = null;
}

function confirmEnd() {
  if (endTarget.value === "quick") quickState.value = "report";
  if (endTarget.value === "floating") floatingState.value = "report";
  showEndDialog.value = false;
  endTarget.value = null;
  sessionStore.stopSession();
}
</script>

<template>
  <main class="min-h-screen bg-[#f4f6f4] text-[#17212b]">
    <header class="border-b border-[#d7ddd8] bg-white">
      <div class="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p class="text-xs font-semibold text-[#607064]">AI 同声传译助手</p>
          <h1 class="mt-1 text-2xl font-bold text-[#17212b]">实时同传工作台草稿</h1>
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

    <section v-if="productMode === 'quick'" class="mx-auto grid max-w-7xl gap-4 px-4 py-4 lg:grid-cols-[340px_minmax(0,1fr)]">
      <aside class="rounded-lg border border-[#d7ddd8] bg-white p-4">
        <div class="flex items-center justify-between">
          <h2 class="text-base font-bold">快速同传设置</h2>
          <span class="rounded-md bg-[#eef1ee] px-2 py-1 text-xs text-[#526057]">{{ quickStatusLabel }}</span>
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
            <div class="mt-2 grid grid-cols-2 gap-2">
              <button
                v-for="source in quickSources"
                :key="source"
                class="rounded-md border px-3 py-2 text-left text-sm"
                :class="
                  quickForm.source === source
                    ? 'border-[#1c7c54] bg-[#e7f4ec] text-[#12462f]'
                    : 'border-[#d7ddd8] bg-white text-[#4a5a50]'
                "
                type="button"
                @click="quickForm.source = source"
              >
                {{ source }}
              </button>
            </div>
          </div>
        </div>

        <div class="mt-5 grid gap-2">
          <button class="primary-button" type="button" @click="startQuick">
            开始同传
          </button>
          <button class="secondary-button" type="button" @click="productMode = 'floating'">
            切到悬浮字幕
          </button>
        </div>
      </aside>

      <section class="grid gap-4">
        <div class="rounded-lg border border-[#d7ddd8] bg-white p-4">
          <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p class="text-xs text-[#607064]">{{ quickForm.name }} · {{ quickForm.sourceLanguage }} -> {{ quickForm.targetLanguage }}</p>
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
            <button v-if="quickState === 'running'" class="secondary-button compact-button" type="button" @click="pauseQuick">
              暂停
            </button>
            <button v-if="quickState === 'paused'" class="primary-button compact-button" type="button" @click="resumeQuick">
              继续
            </button>
            <button class="danger-button compact-button" type="button" @click="askEnd('quick')">
              结束
            </button>
          </div>
        </div>

        <div class="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.75fr)]">
          <section class="rounded-lg border border-[#d7ddd8] bg-white p-4">
            <div class="media-stage">
              <div>
                <p class="text-sm text-[#d8e0da]">{{ quickForm.source }}</p>
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
              <div class="workspace-tile">
                <p class="tile-label">源文实时转写</p>
                <p class="tile-text">{{ currentPair.source }}</p>
              </div>
              <div class="workspace-tile">
                <p class="tile-label">译文实时输出</p>
                <p class="tile-text">{{ currentPair.translation }}</p>
              </div>
              <div class="workspace-tile">
                <p class="tile-label">修正记录</p>
                <p class="tile-text">
                  {{ revisions[0] ? `${revisions[0].beforeText} -> ${revisions[0].afterText}` : "等待修正事件" }}
                </p>
              </div>
              <div class="workspace-tile">
                <p class="tile-label">术语与摘要</p>
                <p class="tile-text">AI translation · 实时 AI 翻译 · 术语命中</p>
              </div>
            </div>
          </section>

          <section class="rounded-lg border border-[#d7ddd8] bg-white p-4">
            <div class="flex items-center justify-between gap-3">
              <h3 class="font-bold">同传显示</h3>
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

        <section v-if="quickState === 'report'" class="rounded-lg border border-[#d7ddd8] bg-white p-4">
          <h3 class="font-bold">会议报告</h3>
          <div class="mt-3 grid gap-3 md:grid-cols-4">
            <div class="report-metric">
              <span>时长</span>
              <strong>18:24</strong>
            </div>
            <div class="report-metric">
              <span>语言</span>
              <strong>{{ quickForm.sourceLanguage }} -> {{ quickForm.targetLanguage }}</strong>
            </div>
            <div class="report-metric">
              <span>修正</span>
              <strong>{{ revisions.length || 1 }} 条</strong>
            </div>
            <div class="report-metric">
              <span>导出</span>
              <strong>TXT / SRT / MD</strong>
            </div>
          </div>
        </section>
      </section>
    </section>

    <section v-else class="mx-auto grid max-w-7xl gap-4 px-4 py-4 lg:grid-cols-[360px_minmax(0,1fr)]">
      <aside class="rounded-lg border border-[#d7ddd8] bg-white p-4">
        <div class="flex items-center justify-between">
          <h2 class="text-base font-bold">悬浮字幕设置</h2>
          <span class="rounded-md bg-[#eef1ee] px-2 py-1 text-xs text-[#526057]">{{ floatingStatusLabel }}</span>
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
                :key="source"
                class="rounded-md border px-3 py-2 text-left text-sm"
                :class="
                  floatingForm.source === source
                    ? 'border-[#1c7c54] bg-[#e7f4ec] text-[#12462f]'
                    : 'border-[#d7ddd8] bg-white text-[#4a5a50]'
                "
                type="button"
                @click="floatingForm.source = source"
              >
                {{ source }}
              </button>
            </div>
          </div>

          <label class="block">
            <span class="form-label">字幕样式</span>
            <select v-model="floatingForm.style" class="form-control">
              <option>双语字幕</option>
              <option>仅译文</option>
              <option>原文优先</option>
            </select>
          </label>
        </div>

        <div class="mt-5 grid gap-2">
          <button class="primary-button" type="button" @click="startFloating">
            开始使用
          </button>
          <button class="secondary-button" type="button" @click="productMode = 'quick'">
            返回快速同传
          </button>
        </div>
      </aside>

      <section class="relative min-h-[680px] rounded-lg border border-[#d7ddd8] bg-[#dfe4df] p-4">
        <div class="grid h-full grid-rows-[auto_minmax(0,1fr)] gap-4">
          <div class="rounded-lg border border-[#c9d1cb] bg-white p-4">
            <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p class="text-xs text-[#607064]">{{ floatingForm.source }} · {{ floatingForm.modelProfile }}</p>
                <h2 class="mt-1 text-xl font-bold">悬浮字幕运行草稿</h2>
              </div>
              <div class="flex flex-wrap gap-2">
                <button class="secondary-button compact-button" type="button">锁定</button>
                <button class="secondary-button compact-button" type="button">A-</button>
                <button class="secondary-button compact-button" type="button">A+</button>
                <button class="secondary-button compact-button" type="button">设置</button>
                <button class="danger-button compact-button" type="button" @click="askEnd('floating')">关闭</button>
              </div>
            </div>
          </div>

          <div class="relative rounded-lg border border-[#c9d1cb] bg-[#f8faf8] p-4">
            <div class="grid h-full place-items-center rounded-lg border border-dashed border-[#b7c1ba] bg-white">
              <div class="text-center">
                <p class="text-sm text-[#607064]">浏览器内悬浮字幕预览</p>
                <p class="mt-2 text-lg font-semibold text-[#17212b]">后续桌面端承接系统级置顶与系统音频</p>
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
                <button v-if="floatingState === 'running'" class="floating-button" type="button" @click="pauseFloating">暂停</button>
                <button v-if="floatingState === 'paused'" class="floating-button" type="button" @click="resumeFloating">继续</button>
                <button class="floating-button danger" type="button" @click="askEnd('floating')">结束</button>
              </div>
            </div>
          </div>
        </div>

        <section v-if="floatingState === 'report'" class="absolute inset-x-4 bottom-4 rounded-lg border border-[#d7ddd8] bg-white p-4">
          <h3 class="font-bold">字幕记录</h3>
          <p class="mt-2 text-sm text-[#4a5a50]">已生成转写、译文、修正记录和导出入口。</p>
        </section>
      </section>
    </section>

    <div v-if="showEndDialog" class="fixed inset-0 z-50 grid place-items-center bg-black/40 px-4">
      <section class="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
        <h2 class="text-lg font-bold">结束本次{{ endTarget === "floating" ? "字幕" : "同传" }}？</h2>
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
