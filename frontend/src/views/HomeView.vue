<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import EntryCard from "../components/home/EntryCard.vue";
import { useGsapReveal } from "../composables/useGsapReveal";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const sessionStore = useSessionStore();
const root = ref<HTMLElement | null>(null);

useGsapReveal(root, { stagger: 0.09, y: 18 });

function enterWeb() {
  router.push({ path: "/web", query: { setup: "1" } });
}

function activateDesktop() {
  sessionStore.openDesktopFloating();
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
        面向技术分享、国际会议和网课内容，实时生成双语字幕，并在上下文到达后自动校正历史译文。
      </p>

      <div class="entry-grid">
        <EntryCard
          data-reveal
          badge="In browser"
          title="Web 端同传"
          subtitle="浏览器内音视频工作台"
          :features="['音视频播放 + 双栏字幕', '分区 / 逐句对照', '自动纠偏可视化']"
          cta="进入工作台"
          variant="primary"
          @activate="enterWeb"
        >
          <template #mark>WEB</template>
        </EntryCard>
        <EntryCard
          data-reveal
          badge="Desktop"
          title="客户端悬浮框"
          subtitle="全局置顶字幕窗"
          :features="['系统 / 应用音频采集', '置顶与托盘能力', 'lingosync:// 唤起']"
          cta="激活客户端"
          @activate="activateDesktop"
        >
          <template #mark>DESK</template>
        </EntryCard>
      </div>

      <p class="home-footnote" data-reveal>英 / 日 / 韩 到中文 · 实时自动纠偏 · 双语记录导出</p>
    </section>
  </main>
</template>
