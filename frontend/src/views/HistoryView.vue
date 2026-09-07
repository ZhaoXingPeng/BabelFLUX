<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import Icon from "../components/icons/Icon.vue";
import {
  deleteSessionHistory,
  getSessionHistory,
  reportDownloadUrl,
  type ReportFormat,
  type SessionHistoryEntry
} from "../api/client";

const router = useRouter();
const entries = ref<SessionHistoryEntry[]>([]);
const loading = ref(false);
const errorMessage = ref("");
const query = ref("");
type HistoryStatusFilter = "all" | "created" | "running" | "correcting" | "completed" | "fallback" | "failed";
const statusFilter = ref<HistoryStatusFilter>("all");
const HISTORY_REFRESH_INTERVAL_MS = 3000;
let historyRefreshTimer: number | null = null;
let historyRequestInFlight = false;
let historyViewMounted = false;

const statusFilters: Array<{ value: HistoryStatusFilter; label: string }> = [
  { value: "all", label: "全部状态" },
  { value: "completed", label: "已完成" },
  { value: "correcting", label: "纠偏中" },
  { value: "fallback", label: "实时译文" },
  { value: "failed", label: "失败" },
  { value: "created", label: "已创建" },
  { value: "running", label: "进行中" }
];

const hasEntries = computed(() => entries.value.length > 0);

const filteredEntries = computed(() => {
  const normalizedQuery = query.value.trim().toLocaleLowerCase();
  return entries.value.filter((entry) => {
    if (statusFilter.value !== "all" && entry.status !== statusFilter.value) return false;
    if (!normalizedQuery) return true;
    const searchable = [
      sessionName(entry),
      sourceLabel(entry),
      entry.domain,
      entry.modelProfile ?? "",
      languagePairLabel(entry),
      statusLabel(entry)
    ]
      .join(" ")
      .toLocaleLowerCase();
    return searchable.includes(normalizedQuery);
  });
});

const hasFilteredEntries = computed(() => filteredEntries.value.length > 0);
const hasActiveFilters = computed(() => Boolean(query.value.trim()) || statusFilter.value !== "all");

const languageLabelByCode: Record<string, string> = {
  auto: "自动检测",
  zh: "中文",
  en: "英语",
  ja: "日语",
  ko: "韩语",
  fr: "法语",
  de: "德语",
  yue: "粤语"
};

const sourceLabelByCode: Record<string, string> = {
  demo: "演示视频",
  fixture_video: "演示视频",
  fixture_english_video: "英文测试视频",
  url: "网络视频",
  microphone: "麦克风",
  browser_audio: "浏览器音频",
  screen_window: "屏幕窗口",
  media_element_audio: "上传媒体",
  video_file: "上传视频",
  audio_file: "上传音频",
  system_audio: "系统音频"
};

const genericFloatingNames = new Set(["悬浮字幕", "悬浮自采集", "客户端悬浮"]);

function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function lookupLabel(value: string | null | undefined, labels: Record<string, string>): string {
  const normalized = value?.trim();
  if (!normalized) return "未知";
  return labels[normalized.toLowerCase()] ?? normalized;
}

function sourceLabel(entry: SessionHistoryEntry): string {
  return lookupLabel(entry.sourceLabel || entry.inputMode, sourceLabelByCode);
}

function languagePairLabel(entry: SessionHistoryEntry): string {
  return `${lookupLabel(entry.sourceLanguage, languageLabelByCode)} → ${lookupLabel(entry.targetLanguage, languageLabelByCode)}`;
}

function compactStartedAt(value: string): string {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!match) return value.replace(/\D/g, "").slice(0, 14) || "未知时间";
  return `${match[1]}${match[2]}${match[3]}_${match[4]}${match[5]}${match[6] ?? "00"}`;
}

function sessionName(entry: SessionHistoryEntry): string {
  const name = entry.sessionName?.trim();
  if (entry.productMode === "floating" && (!name || genericFloatingNames.has(name))) {
    return `悬浮同传_${sourceLabel(entry)}_${compactStartedAt(entry.startedAt)}`;
  }
  return name || "未命名同传";
}

function statusLabel(entry: SessionHistoryEntry): string {
  if (entry.status === "completed") return "已完成";
  if (entry.status === "correcting" || entry.correctionStatus === "pending") return "纠偏中";
  if (entry.status === "fallback") return "实时译文";
  if (entry.status === "running") return "进行中";
  if (entry.status === "failed") return "失败";
  return "已创建";
}

function statusTone(entry: SessionHistoryEntry): string {
  if (entry.status === "completed") return "ok";
  if (entry.status === "correcting" || entry.correctionStatus === "pending") return "pending";
  if (entry.status === "failed") return "error";
  return "muted";
}

function clearFilters() {
  query.value = "";
  statusFilter.value = "all";
}

function canDownload(entry: SessionHistoryEntry): boolean {
  return Boolean(entry.reportId) && entry.availableFormats.length > 0;
}

function download(entry: SessionHistoryEntry, format: ReportFormat) {
  if (!canDownload(entry)) return;
  const anchor = document.createElement("a");
  anchor.href = reportDownloadUrl(entry.sessionId, format);
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

async function loadHistory() {
  if (historyRequestInFlight) return;
  historyRequestInFlight = true;
  loading.value = true;
  errorMessage.value = "";
  try {
    const nextEntries = await getSessionHistory();
    if (historyViewMounted) entries.value = nextEntries;
  } catch (error) {
    if (!historyViewMounted) return;
    errorMessage.value = error instanceof Error ? error.message : "历史记录加载失败";
  } finally {
    historyRequestInFlight = false;
    if (historyViewMounted) loading.value = false;
    scheduleHistoryRefresh();
  }
}

function hasPendingCorrection(): boolean {
  return entries.value.some(
    (entry) => entry.status === "correcting" || entry.correctionStatus === "pending"
  );
}

function scheduleHistoryRefresh() {
  if (!historyViewMounted || historyRefreshTimer !== null || !hasPendingCorrection()) return;
  historyRefreshTimer = window.setTimeout(() => {
    historyRefreshTimer = null;
    void loadHistory();
  }, HISTORY_REFRESH_INTERVAL_MS);
}

async function removeEntry(entry: SessionHistoryEntry) {
  try {
    await deleteSessionHistory(entry.sessionId);
    entries.value = entries.value.filter((item) => item.sessionId !== entry.sessionId);
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "删除失败";
  }
}

onMounted(() => {
  historyViewMounted = true;
  void loadHistory();
});

onUnmounted(() => {
  historyViewMounted = false;
  if (historyRefreshTimer !== null) {
    window.clearTimeout(historyRefreshTimer);
    historyRefreshTimer = null;
  }
});
</script>

<template>
  <main class="history-shell">
    <header class="history-topbar">
      <button class="topbar-link" type="button" @click="router.push('/')">
        <Icon name="arrow-left" :size="16" />
        <span>返回主屏</span>
      </button>
      <div>
        <p>Reports</p>
        <strong>报告历史</strong>
      </div>
      <button class="topbar-link" type="button" @click="loadHistory">
        <Icon name="refresh-cw" :size="16" />
        <span>刷新</span>
      </button>
    </header>

    <section class="history-panel">
      <div class="history-panel-header">
        <div>
          <p>Session archive</p>
          <h1>会话报告</h1>
        </div>
        <button class="secondary-button compact-button" type="button" @click="router.push('/web')">
          新建同传
        </button>
      </div>

      <p v-if="loading" class="history-message">正在读取历史记录…</p>
      <p v-else-if="errorMessage" class="history-message error">{{ errorMessage }}</p>
      <p v-else-if="!hasEntries" class="history-message">暂无报告历史。结束一次同传后，基础报告会自动出现在这里。</p>

      <div v-else class="history-content">
        <div class="history-toolbar" aria-label="历史筛选">
          <label class="history-filter-field">
            <span>关键词</span>
            <input
              v-model="query"
              data-testid="history-search"
              type="search"
              placeholder="搜索会话、来源或领域"
            />
          </label>
          <label class="history-filter-field">
            <span>状态</span>
            <select v-model="statusFilter" data-testid="history-status-filter">
              <option v-for="option in statusFilters" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>
          <button
            v-if="hasActiveFilters"
            class="icon-button light history-filter-reset"
            type="button"
            aria-label="清除筛选"
            title="清除筛选"
            @click="clearFilters"
          >
            <Icon name="x" :size="15" />
          </button>
        </div>

        <p v-if="!hasFilteredEntries" class="history-message">没有符合当前筛选条件的会话。</p>
        <div v-else class="history-table">
          <div class="history-row history-row-head">
            <span>会话</span>
            <span>来源</span>
            <span>领域</span>
            <span>模型策略</span>
            <span>语种</span>
            <span>时长</span>
            <span>状态</span>
            <span>下载</span>
          </div>
          <article v-for="entry in filteredEntries" :key="entry.sessionId" class="history-row">
            <div class="history-title-cell">
              <strong>{{ sessionName(entry) }}</strong>
              <small>{{ entry.startedAt }} · {{ entry.segmentCount }} 句</small>
            </div>
            <span>{{ sourceLabel(entry) }}</span>
            <span>{{ entry.domain }}</span>
            <span>{{ entry.modelProfile || "智能默认" }}</span>
            <span>{{ languagePairLabel(entry) }}</span>
            <span>{{ formatDuration(entry.durationMs) }}</span>
            <span :class="['history-status', statusTone(entry)]">{{ statusLabel(entry) }}</span>
            <div class="history-actions">
              <button
                v-for="format in (['txt', 'srt', 'md', 'json'] as ReportFormat[])"
                :key="format"
                type="button"
                :disabled="!canDownload(entry)"
                :title="`${format.toUpperCase()} 下载`"
                @click="download(entry, format)"
              >
                {{ format.toUpperCase() }}
              </button>
              <button type="button" title="删除历史记录" @click="removeEntry(entry)">
                <Icon name="trash-2" :size="14" />
              </button>
            </div>
          </article>
        </div>
      </div>
    </section>
  </main>
</template>
