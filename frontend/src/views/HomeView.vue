<script setup lang="ts">
import { ref } from "vue";
import { storeToRefs } from "pinia";
import { useRouter } from "vue-router";
import EntryCard from "../components/home/EntryCard.vue";
import DesktopLaunchPrompt from "../components/workbench/DesktopLaunchPrompt.vue";
import { useGsapReveal } from "../composables/useGsapReveal";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const sessionStore = useSessionStore();
const root = ref<HTMLElement | null>(null);
const { desktopDownloadPromptOpen, desktopHandoffUrl, desktopLaunchMessage, desktopLaunchState } =
  storeToRefs(sessionStore);

useGsapReveal(root, { stagger: 0.09, y: 18 });

function enterWeb() {
  router.push({ path: "/web", query: { setup: "1" } });
}

function activateDesktop() {
  sessionStore.openDesktopFloating();
}

function continueWithWebFloating() {
  sessionStore.continueWithWebFloating();
  router.push({ path: "/web" });
}
</script>

<template>
  <main ref="root" class="home-shell">
    <header class="home-nav" data-reveal>
      <div>
        <p>LingoSync</p>
        <strong>灵犀同传</strong>
      </div>
      <nav aria-label="主导航">
        <a href="/docs/design/前端布局重构设计方案_v1.md">设计方案</a>
        <a href="https://gitee.com/RedamancyZXP/ai-product-lab" target="_blank" rel="noreferrer">仓库</a>
      </nav>
    </header>

    <section class="home-hero">
      <p class="home-kicker" data-reveal>Real-time interpretation</p>
      <h1 data-reveal>
        实时外语音频
        <span>流畅中文同传</span>
      </h1>
      <p class="home-subtitle" data-reveal>
        实时双语字幕，随上下文自动校正历史译文
      </p>

      <div class="entry-grid">
        <EntryCard
          data-reveal
          index="01"
          badge="In browser"
          title="Web 端同传"
          subtitle="浏览器内音视频工作台"
          :features="['音视频播放 + 双栏字幕', '分区 / 逐句对照', '自动纠偏可视化']"
          cta="进入工作台"
          variant="primary"
          @activate="enterWeb"
        >
          <template #icon>
            <svg viewBox="0 0 36 36" role="img" aria-label="Web 端">
              <rect x="6" y="8" width="24" height="20" rx="3" />
              <path d="M6 14h24M12 11h.01M16 11h.01" />
            </svg>
          </template>
        </EntryCard>
        <EntryCard
          data-reveal
          index="02"
          badge="Desktop"
          title="客户端悬浮框"
          subtitle="全局置顶字幕窗"
          :features="['系统 / 应用音频采集', '置顶与托盘能力', 'lingosync:// 唤起']"
          cta="激活客户端"
          @activate="activateDesktop"
        >
          <template #icon>
            <svg viewBox="0 0 36 36" role="img" aria-label="客户端悬浮框">
              <rect x="5" y="9" width="20" height="16" rx="3" />
              <rect x="17" y="17" width="14" height="10" rx="2" />
              <path d="M9 28h11" />
            </svg>
          </template>
        </EntryCard>
      </div>

      <p class="home-footnote" data-reveal>多语种音视频 → 中文实时字幕 · 上下文自动纠偏 · 可选中文语音 · 双语稿导出</p>
    </section>

    <DesktopLaunchPrompt
      v-if="desktopDownloadPromptOpen || desktopLaunchState === 'launching'"
      :state="desktopLaunchState"
      :message="desktopLaunchMessage"
      :deep-link-url="desktopHandoffUrl"
      @retry="sessionStore.openDesktopFloating"
      @continue-web="continueWithWebFloating"
      @close="sessionStore.dismissDesktopDownloadPrompt"
    />
  </main>
</template>
