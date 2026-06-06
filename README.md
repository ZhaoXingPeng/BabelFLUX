# AI 同声传译助手 · AI Product Lab

> 把英语等外语的**单向音频流**实时翻译成中文，以**双语字幕 / 语音**呈现，并能在传译过程中**自动纠正**已经输出的识别/翻译错误。面向演讲、技术分享、国际会议与网课等「跟不上、听不懂、来不及记」的场景。
>
> 黑客松选题二的完整实现：Web 工作台 + 桌面悬浮窗 + FastAPI 后端 + 阿里云百炼真实模型链路。

---

## ✨ 核心特性

| 能力 | 说明 |
| --- | --- |
| 🎙️ **实时识别 + 翻译** | 单条 WebSocket 接入 `qwen3.5-livetranslate-flash-realtime`，服务端 VAD 自动断句，边说边出双语字幕 |
| 🔁 **实时纠偏（在线）** | 传译进行中由 `qwen-flash` 跨句复核，结合后文修正前句的术语/数字/否定/一词多义错误，前端**琥珀高亮**即时展示 |
| 📝 **完整纠偏（会后）** | 结束后 `qwen-plus` 通读全场做全局校正、统一术语、生成摘要；六大领域差异化 PROMPT |
| 🎧 **多源输入** | 在线直链、本地视频/音频上传、麦克风、系统音频、屏幕/窗口、浏览器标签页，以及演示模式 |
| 🪟 **桌面悬浮窗** | Tauri 透明置顶字幕；可自选音源独立采集，或接管 Web 会话；任意位置拖拽、可调透明度与字号 |
| 📄 **会话报告导出** | 双语终稿 + 校正记录 + 摘要，支持 **TXT / SRT / Markdown / JSON** 四种格式下载 |
| 📚 **术语表 / 热词** | 术语经引擎 corpus 注入，纠偏与报告全程优先遵循 |
| 🔌 **可降级** | 模型不可用时优雅降级（mock 事件流 / 纯实时译文报告），保证演示链路始终可跑 |

---

## 🏗️ 系统架构

三端 + 一条真实模型链路，所有服务可同机部署（演示环境为 Windows 单机）：

```
┌──────────────┐   lingosync:// handoff    ┌─────────────────┐
│  Web 工作台   │◄─────────────────────────►│  桌面悬浮窗      │
│ Vue3+Pinia   │                            │ Tauri v2(WebView)│
│ +Vite +GSAP  │                            │ standalone/接管   │
└──────┬───────┘                            └────────┬─────────┘
       │   WebSocket(事件) + REST(会话/报告)          │
       └───────────────────┬──────────────────────────┘
                           ▼
                 ┌────────────────────┐
                 │   FastAPI 后端      │  会话管理 / 音频入口 / 管线编排
                 │   asyncio + ffmpeg  │  双层纠偏 / 报告生成与下载
                 └─────────┬──────────┘
                           ▼  阿里云百炼（标准端点）
   音源→16k PCM→ qwen3.5-livetranslate (ASR+翻译, 服务端 VAD)
        → transcript/translation 事件 → 前端字幕流
        → qwen-flash 跨句实时纠偏 → revision 事件 → 琥珀高亮
   结束 → qwen-plus 会后完整纠偏 → session_report → 四格式下载
```

### 模型链路与选型

> 均经标准端点 `https://dashscope.aliyuncs.com`（HTTP `/api/v1`、WS `/api-ws/v1`）实测连通。

| 环节 | 模型（`.env` 变量） |
| --- | --- |
| 实时识别 + 翻译 | `qwen3.5-livetranslate-flash-realtime`（`LIVE_TRANSLATE_MODEL`） |
| 内嵌 ASR | `qwen3-asr-flash-realtime`（`LIVE_TRANSLATE_ASR_MODEL`） |
| 实时纠偏（低延迟） | `qwen-flash`（`REALTIME_REVISION_MODEL`） |
| 会后完整纠偏（强模型） | `qwen-plus`（`FINAL_CORRECTION_MODEL`，可换 `qwen3-max` / `deepseek-v4-pro`） |
| 语音合成（可选） | `qwen3-tts-flash-realtime`（`TTS_MODEL`，voice `Cherry`） |

---

## 🎧 输入源

后端按会话 `inputMode` 选择音频入口（`backend/app/api/ws.py`）：

| 模式 | 入口 |
| --- | --- |
| `url` | 后端用 ffmpeg 从在线直链解码并喂入 |
| `upload_video` / `upload_audio` | 解码先前上传到 `/sessions/{id}/media` 的本地文件 |
| `microphone` / `system_audio` / `screen_window` / `browser_audio` | 前端 / 桌面用 AudioWorklet 采集为 16k 单声道 PCM，经 WS 二进制帧推送 |
| `demo` | `DEMO_MEDIA_PATH` 指向的样例媒体，或 mock 事件流 |

> 采集类音源在浏览器/WebView 内用 `AudioContext({sampleRate:16000})` 原生重采样到 16k，分帧 ~100ms 推流；前端在后端管线就绪（收到首个 `source_sync_state`）后才开始推送，避免早期帧丢弃。

---

## 🚀 本地启动

> 依赖：Python 3.11、Node 18+、`ffmpeg` 在 PATH 中；桌面端额外需要 Rust + WebView2（Windows）。

### 后端

```bash
cp .env.example .env        # 默认 MODEL_PROVIDER=mock，可零配额跑通全链路
./scripts/dev-backend.sh    # uvicorn app.main:app  ->  http://localhost:8000
```

接入**真实模型**：在 `.env` 设 `MODEL_PROVIDER=real` 并填 `DASHSCOPE_API_KEY`（如用业务空间再填 `DASHSCOPE_WORKSPACE_ID`），其余模型名已给默认值。

### 前端

```bash
cp frontend/.env.example frontend/.env
./scripts/dev-frontend.sh   # vite  ->  http://localhost:5173
```

### 桌面悬浮窗

```bash
cd desktop && npm install
npm run tauri dev           # 开发态 devUrl 5175；npm run tauri build 出安装包
```

默认服务地址：

```text
REST       http://localhost:8000/api
WebSocket  ws://localhost:8000/api/ws/sessions/{session_id}
Health     http://localhost:8000/api/health
```

---

## 🔌 WebSocket 事件协议

路由 `/api/ws/sessions/{sessionId}`，字段统一 camelCase。

- **客户端 → 服务端**：`start_session`（可携带语种/领域/源覆盖项）、二进制 PCM 帧、`audio_end` / `audio_chunk_end`、`stop_session`、`pause_session` / `resume_session`
- **服务端 → 客户端**：`session_started`、`source_sync_state`、`transcript_segment`、`translation_segment`、`revision_event`、`session_report{reportId}`、`error`

DashScope 网关也以 REST 暴露，便于单独调试：

```text
POST /api/models/llm/generate
POST /api/models/asr/transcriptions
POST /api/models/tts/speech
```

---

## 📁 目录结构

```text
frontend/   Vue 3 + Vite + Pinia 前端工作台：输入源配置、双语字幕流、实时纠偏高亮、报告下载
backend/    FastAPI 后端
  app/api/        health / sessions / model_gateway / ws
  app/services/   pipeline(管线) / revision(实时纠偏) / report(会后纠偏+报告)
                  / media / handoff / session_store / model_strategy / providers(dashscope|mock)
  scripts/        prove_realtime_revision.py(纠偏能力证明) / e2e_online_url.py(在线直链联调)
desktop/    Tauri v2 桌面悬浮窗：standalone 自采集 + deep-link 接管
docs/       architecture / backend / design / project-plans / requirements …
scripts/    dev-backend.sh / dev-frontend.sh / check.sh
.env.example / providers.example.yaml
```

---

## 🧰 技术栈

**前端** Vue 3 · Vite · TypeScript · Pinia · Tailwind · GSAP（字幕入场与纠偏高亮动效）· @vueuse/core · @floating-ui/vue · video.js

**桌面** Tauri v2 · @tauri-apps/plugin-deep-link / global-shortcut / store · Vue 3

**后端** FastAPI · uvicorn · pydantic / pydantic-settings · httpx · websockets · aiofiles · sqlmodel · ffmpeg（音频解码）

**模型** 阿里云百炼 DashScope（LiveTranslate 实时音视频翻译 / qwen-flash / qwen-plus / qwen-tts）

---

## ✅ 测试与验证

```bash
cd backend && python -m pytest        # 后端单元/契约测试
cd frontend && npx vue-tsc --noEmit    # 前端类型检查
cd desktop && npx vue-tsc --noEmit     # 桌面类型检查
```

链路联调脚本（`backend/scripts/`，需 `PYTHONPATH=. python3`）：

- `prove_realtime_revision.py` — 用真实模型证明实时纠偏「该纠必纠、干净零误纠」
- `e2e_online_url.py <直链> [秒]` — 在线直链端到端：识别/翻译/纠偏/报告 + 四格式下载

实测要点：在线视频/音频直链全链路通过，实时纠偏在真实内容触发（如量词「几位→几件」），会后报告四格式 200 可下载。完整实现与联调结论见 [`docs/backend/实现总览与联调备份_AI同声传译.md`](docs/backend/实现总览与联调备份_AI同声传译.md)。

---

## 🧭 开发规范

- 主分支 `main` 始终保持可运行 / 可审阅；新功能走独立分支 + PR，单个 PR 只做一件事。
- PR 描述包含：功能描述、实现思路、测试方式。
- 分支命名 `feat/* | fix/* | docs/* | chore/*`；提交信息 `feat: … / fix: … / docs: … / chore: …`。

---

## 📌 当前状态

最终选题 **AI 同声传译助手** 已落地为可演示的端到端系统：真实模型链路打通，实时 + 会后双层纠偏可用，多源输入、桌面悬浮窗、会话报告导出齐备。桌面端与 deep-link 使用产品代号 `lingosync://`（品牌命名待最终确认）。后续可按需扩展：更细的 VAD 分段、多目标语种、TTS 回放与历史会话管理。
