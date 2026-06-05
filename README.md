# AI Product Lab

本仓库用于 **AI 同声传译助手** 项目的方案确认、需求拆解、开发迭代与评审资料沉淀。

## 最终选题

**选题二：AI 同声传译助手**

项目目标：通过 AI 能力，将英语或其他外语的单向音频流实时、流畅地翻译成中文，并以字幕或语音形式呈现，帮助用户跟上演讲、技术分享、国际会议和网课内容节奏。

核心能力：

1. 实时音频采集与流式识别。
2. 外语到中文的上下文翻译。
3. 中文字幕实时展示。
4. 对历史识别或翻译错误进行自动修正。
5. 支持术语表、双语记录和字幕导出等扩展能力。

## 目录结构

```text
frontend/           Vue 3 + Vite 前端控制台，负责视频区、字幕区、纠偏记录和会话控制
backend/            FastAPI 后端，负责 REST、WebSocket、模型 provider 封装和后续数据存储
docs/
  project-selection/ 最终选题确认与决策说明
  project-plans/     三个候选议题的初步方案，保留为调研材料
  requirements/      原始项目要求与评审规范
  process/           开发、提交、PR 相关流程说明
scripts/            本地开发与检查脚本
.env.example        本地环境变量样例
providers.example.yaml 模型供应商路由样例
```

## 本地启动

后端：

```bash
cp .env.example .env
./scripts/dev-backend.sh
```

前端：

```bash
cp frontend/.env.example frontend/.env
./scripts/dev-frontend.sh
```

默认后端地址：

```text
REST: http://localhost:8000/api
WebSocket: ws://localhost:8000/api/ws/sessions/{session_id}
Health: http://localhost:8000/api/health
```

当前脚手架使用 `mock` 模型 provider，先跑通 `session_started`、`source_sync_state`、`transcript_segment`、`translation_segment` 和 `revision_event`。真实 Fun-ASR、千问实时音视频翻译、TTS 和最终纠偏大模型后续通过 `backend/app/services/providers/` 接入。

## 开发原则

1. 主分支 `main` 始终保持可运行或可审阅状态。
2. 新功能通过独立分支开发，并通过 PR 合并。
3. 每个 PR 只做一件事，避免把多个功能混在同一个 PR。
4. PR 描述必须包含功能描述、实现思路和测试方式。
5. README 中需要列明第三方依赖，并说明原创功能部分。

## 推荐分支命名

```text
feat/<short-feature-name>
fix/<short-bug-name>
docs/<short-doc-name>
chore/<short-task-name>
```

示例：

```text
feat/audio-session
feat/subtitle-revision
chore/init-repo
```

## 推荐提交信息

```text
feat: 新增音频会话入口
fix: 修复字幕修正状态更新
docs: 补充同传 MVP 范围说明
chore: 初始化项目结构
```

## 当前状态

当前已确认最终选题为 **AI 同声传译助手**，并已搭建前后端基础结构。下一步按功能拆分 PR，优先完成实时字幕同传 MVP，包括音频输入、流式识别、中文翻译、字幕展示和历史字幕修正机制。
