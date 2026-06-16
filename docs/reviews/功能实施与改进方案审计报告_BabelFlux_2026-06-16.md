# 功能实施与改进方案审计报告（7 日冲刺）· BabelFlux / 巴别流 同传

> 编制日期：2026-06-16 ｜ 距面试约 7 天
> 代码版本：`origin/main` = `297c58f`（!52）
> 定位：在《项目改进审计报告》（问题清单）与《项目汇报审计报告》（汇报结构）之上，给出**可落地的实施蓝图**。**本报告全程只读分析，未修改任何代码**；其中代码片段均为「示意设计，非已落地」，供实施时参考。
> 决策依据：用户确认有 7 天窗口，**可做真功能修正（TTS 优先真正实现）**，其余改动优先级由本报告判定。

---

## 0. 总体策略

7 天的目标不是"全做完"，而是**让面试 Demo 更有冲击力、让代码经得起追问**。据此把工作分三档：

| 档位 | 目标 | 项目 |
| --- | --- | --- |
| **必做（demo+防穿帮）** | 一个新亮点 + 不被现场抓包 | ① TTS 双语语音播报（旗舰）② 上传死代码/sqlmodel 清理 + 文档据实 |
| **应做（经得起追问）** | 安全/正确性硬伤补齐 | ③ 主 WS 鉴权 ④ 纠偏并发幂等 |
| **选做（有时间再上）** | 体验/生产化加分 | ⑤ 客户端真双向时钟 ⑥ 长会话虚拟滚动 ⑦ 持久化+断线重连 ⑧ 多语种/modelProfile 接线 |

> 排序原则：**Demo 可见价值 > 面试可被追问的正确性/安全 > 生产化后劲**。TTS 排第一，因为它是**竞品都在主打（讯飞"真声播报"、字节"声音复刻"）而我们尚缺的能力**，且其启用链路后端已就位，性价比最高。

---

## 1. 旗舰功能：TTS 双语语音播报 —— 端到端实施方案 ⭐

### 1.1 现状（七成管线已就位）
- **启用开关链路后端已全通**：`CreateSessionRequest.tts_enabled`（`sessions.py:51`）→ `_register_session`（`sessions.py:108`）→ `SessionRecord.tts_enabled`（`session_store.py:55`）→ `pipeline` 传入 `LiveTranslateSession`（`pipeline.py:156/195`）→ `realtime.py:191` 配 `modalities:["text","audio"]` + `voice`。
- **模型已会回吐音频**：`realtime.py:168` 把 `response.audio.delta`（base64 PCM）归一化为 `NormalizedEvent(kind="audio", audio=bytes)`。
- **三处缺口（要做的）**：
  1. 前端 `CreateSessionPayload`（`client.ts:5`）**无 `ttsEnabled` 字段**、UI 也无开关 → 前端永远不发 → 后端恒 `False`。
  2. `pipeline._handle`（`pipeline.py:275`）**没有 `kind=="audio"` 分支** → 模型回吐的音频被丢弃。
  3. 前端**无 TTS 音频播放**（现仅 `mediaElement.play()` 播放源视频，无 Web Audio 播放模型音频）。

### 1.2 目标
开启「语音」后，每句译文确定时，前端用合成语音播报中文译文，与字幕同步；可一键静音/调音量。让 README 的「双语字幕 / **语音** 呈现」名副其实。

### 1.3 实施步骤

**① 前端开关与透传（约 0.3 人天）**
- `client.ts` `CreateSessionPayload` 增 `ttsEnabled?: boolean`；`session.ts buildSessionPayload`（`:1187`）带上 `ttsEnabled`（取自表单）；`SettingsDialog`/`QuickSetupPanel` 增一个「语音播报」开关写入 `quickForm/floatingForm`。
- *后端无需改*：`tts_enabled` 已贯通。

**② 后端接收并下发音频（约 1 人天）**
- `pipeline._handle` 增分支：`elif kind == "audio": await self._on_audio(ev)`。
- 新增 `_on_audio`：把音频按 `response_id` 关联到对应段，经 WS 下发。两种下发方式（择一）：
  - *推荐*：新事件 `audio_segment`（JSON），载 `segmentId` + base64 PCM 分片 + `sampleRate`，与现有事件协议一致、最易接。
  - 备选：WS 二进制帧（更省带宽，但要在前端区分"这是 TTS 回放"而非别的二进制）。
- 在 `realtime.py _session_update_event` 明确**输出采样率**（qwen3-tts 常见 24kHz；当前只设了 `sample_rate:16000`，需确认是否要 `output_sample_rate` 或单独字段，**实施前用真实链路抓一帧确认**）。

```python
# 示意（非落地）：pipeline.py _handle 增补
elif kind == "audio":
    await self._on_audio(ev)        # 累积/分片 → emit audio_segment

async def _on_audio(self, ev) -> None:
    seg = self._by_response.get(ev.response_id)
    if seg is None or not ev.audio:
        return
    await self.emit({
        "type": "audio_segment",
        "segmentId": seg.segment_id,
        "audio": base64.b64encode(ev.audio).decode(),
        "sampleRate": self._tts_sample_rate,   # 实测确认
    })
```

**③ 前端播放与同步（约 1.5 人天）**
- 新建 `composables/useTtsPlayback.ts`：维护一个 `AudioContext` + 播放队列，收到 `audio_segment` 就把 PCM 包成 `AudioBuffer` 用 `AudioBufferSourceNode` 顺序排播（`when` 用 `context.currentTime` 累加，避免拼接爆音）。
- `applyServerEvent`（`session.ts:1544`）增 `audio_segment` 分支 → 入队播放；与 `translation_segment` 的"当前句高亮"对齐。
- UI：静音/音量开关；遵守浏览器自动播放策略（会话由用户点击启动 = 已有手势，OK；但首次 `AudioContext.resume()` 要挂在该手势上）。

### 1.4 风险与对策
| 风险 | 对策 |
| --- | --- |
| **计费**：开 audio 模态会增 TTS 费用 | 默认关闭，UI 显式开启；可只对 final 段播报、不播 partial |
| **延迟**：语音比字幕慢 | 以字幕为主、语音为辅；语音滞后属正常同传体验 |
| **采样率/格式不符** → 爆音 | 实施前用真实链路确认输出 PCM 采样率，前端按实际值建 AudioBuffer |
| **移动端自动播放限制** | resume 绑定到 start 手势；失败则降级为"仅字幕" |
| **与降级冲突** | mock 模式不产音频 → 自然不播；保持可降级 |

### 1.5 验收标准
- 开「语音」后，真实链路下能听到与译文一致的中文播报，且可静音；关闭时行为与现状完全一致（零回归）。
- `MODEL_PROVIDER=mock` 下不报错、不尝试播放。
- 回归：pytest / vue-tsc / vitest / build 全绿。

> **工作量合计：约 2.5–3 人天**（7 天窗口内安全），是单项 ROI 最高的新亮点。

---

## 2. 安全与正确性（应做，经得起追问）

### 2.1 主 WebSocket 鉴权（#1，约 1 人天）
- **现状**：`ws.py:58` 主路径 `get_or_create(session_id)` 直接放行；仅 handoff 路径校验 token。
- **方案**：复用已很完整的 `handoff_tokens` 机制思路——`create_session` 时签发一个**会话级 ws_token**，主路径连接也校验 `?token=`（与 `_serve_handoff_socket` 同源）。或加环境开关 `REQUIRE_WS_TOKEN`，demo 关、生产开。
- **验收**：无 token / 错 token 被 4401 拒；前端 `createSessionSocket` 带上 token；测试补一条拒绝用例。
- **加分话术**：现场可讲"我们把 handoff 的 token 设计推广到主路径，鉴权从一处复用到全局"。

### 2.2 纠偏并发幂等（#3，约 0.5 人天）
- **现状**：`_apply_revision`（`pipeline.py:986`）无 `status=="revised"` 校验；窗口重叠时同句可被多任务重复改写。
- **方案**：`_apply_revision` 入口加幂等——若 `seg.status=="revised"` 且 `after==seg.translation_text` 则跳过；或给段加 `revision_version`，复核结果带基线版本、不匹配则丢弃。对同一 segment 串行化。
- **验收**：构造"窗口重叠 + 同句多次命中"用例，断言只产生一条 `RevisionRecord`、无振荡。

---

## 3. 同步与性能（选做，体验加分）

### 3.1 客户端时钟真双向（#2，约 1.5 人天）
- **现状**：`elapsed_ms` 按喂入字节累加（`pipeline.py:210`），`playback_ms` 只用于发 lag 状态（`pipeline.py:1074`），不回写时间码；丢帧下漂移。
- **方案**：用 `_client_playback_ms` 周期性**校准段落时间码基准**（如对 `_estimate_display_bounds` 引入 playback 锚点），让字幕 `startMs/endMs` 跟随真实播放。注意**只在采集/上传媒体路径**生效（这些才有真实 playback）。
- **风险**：动时延/同步核心，可能回退既有"贴近真实"的观感 → 需真实链路验证，建议**放最后做或留作"路线图"讲**。

### 3.2 长会话前端虚拟滚动（#7，约 1 人天）
- **现状**：`transcriptPairs`（`session.ts:707`）每事件全量重建、`combinedTimeline`（`:443`）O(n²)、DOM 全量渲染。
- **方案**：用 Map 增量维护配对索引（id→pair）；字幕列表接虚拟滚动（仅渲染可视窗口）。
- **验收**：注入 1000 句压力下，每事件更新耗时与滚动帧率稳定。

---

## 4. 整洁与可信（必做，低风险）

### 4.1 上传死代码清理（#5，约 0.5 人天）
- **删**：`upload_video`/`upload_audio` 跨 5 文件 + `App.test.ts`（详见 `docs/reviews/项目改进审计报告` #5 与计划文件 `clever-leaping-hamming.md` 改动集）。
- **保留**：`media.py`/ffmpeg/`url` 模式（真实在用，非死代码）。
- **注意**：`App.test.ts:591` 断言 `uploadSessionMedia` 未被调用——删函数需同步删该断言（其意图已由 584-589 的 `media_element_audio` 断言覆盖）。

### 4.2 移除冗余依赖 sqlmodel（#10，约 0.1 人天）
- `pyproject.toml:14` 删 `sqlmodel`（全仓零使用）。

### 4.3 文档据实（对应过度声明，约 0.3 人天）
- README：`:41` 上传措辞、`:75-76` 删 upload 行、`:166` 技术栈去 sqlmodel、`:167` 媒体解码理由去"上传"。
- **TTS 措辞**：本轮**真正实现 TTS** 后，README `:28`「双语字幕 / 语音」可**如实保留**（无需软化）——这是把"过度声明"转成"已兑现"的最佳路径。
- **更正**：审计原列的"客户端时钟双向同步"措辞**并不在 README/代码**（`useAudioCapture.ts:63` 已写"同步观测"），无需改文档。

---

## 5. 生产化（选做，讲路线图即可，不一定动手）
- **持久化**（#6）：会话/事件/handoff 由内存换 Redis/SQLite（`session_store.py` 已自注释预留）→ 解锁多机与重启容错。约 2 人天。
- **断线重连**（#8）：`connectSocket` 加指数退避重连（依赖 #6 才能真正续接）。约 0.5 人天。
- **多语种 / modelProfile 接线**（#9）：把装饰性 UI 真正驱动后端选型（`modelProfile` 当前在 `sessions.py:99` 未透传）。约 1.5 人天。
- 这些**面试"讲清楚有规划"比"改完"更划算**，列入路线图即可。

---

## 6. 七日逐日排期（建议）

| 日 | 任务 | 产出 |
| --- | --- | --- |
| **D1** | §4 全部：删上传死代码 + sqlmodel + 文档据实 → 跑回归全绿 | 干净可信的基线，工作树验证通过 |
| **D2** | TTS ①②：前端开关透传 + 后端 `_handle` 接 audio 下发；真实链路确认输出采样率 | 后端能把 TTS 音频发到前端 |
| **D3** | TTS ③：`useTtsPlayback` 播放队列 + 同步 + 静音；端到端联调 | **语音播报可演示** |
| **D4** | §2.1 主 WS 鉴权 + §2.2 纠偏幂等 + 补测试 | 安全/正确性追问有底气 |
| **D5** | §3.2 虚拟滚动（或 §3.1 真双向时钟，二选一看精力） | 长会话/同步体验提升 |
| **D6** | 机动：未完项收尾 + README/汇报材料据实更新 + 多语种接线（若有余力） | 文档与代码一致 |
| **D7** | **全量回归 + Demo 彩排 + 录屏兜底**（fixture 与真实链路各一遍） | 现场零翻车 |

> 若进度紧张，**砍 D5/D6 选做项，保 D1–D4 + D7**：清理可信基线 + TTS 旗舰 + 安全正确性 + 彩排，已足够撑起一场高质量汇报。

---

## 7. 验证与 Demo 彩排策略
- **每项改完即回归**：`cd backend && PYTHONPATH=. python3 -m pytest` + `ruff check`；`cd frontend && node_modules/.bin/vue-tsc --noEmit` + `vitest run` + `npm run build`。基线为 pytest 36 / vue-tsc 0 / vitest 28（上次记录），新增功能应配套新增用例。
- **Demo 双保险**：fixture 路径（无网络/零配额，最稳）跑通"字幕逐句→纠偏高亮→**语音播报**→报告导出"；真实链路另跑一遍并**录屏**，现场网络不稳时回放。
- **TTS 专项验收**：开/关语音的行为对比、静音、mock 模式不报错。

---

## 8. 风险登记册

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| TTS 输出采样率/格式未知致爆音 | 中 | D2 先用真实链路抓一帧确认再写播放 |
| 改鉴权破坏现有 demo 连接 | 中 | 加环境开关，demo 默认关；改完先跑 fixture |
| 真双向时钟回退"贴近真实"观感 | 中 | 放 D5 且可随时回退；不行就只讲路线图 |
| 7 天排不完 | 低 | 选做项可砍，保 D1–D4+D7 |
| 删上传死代码漏改 `App.test.ts` 致测试红 | 低 | 改动集已列全 4 处引用，回归兜底 |

---

## 9. 验收标准汇总（逐项）
- **TTS**：真实链路有语音、可静音、关闭零回归、mock 不报错、回归全绿。
- **WS 鉴权**：无/错 token 被拒，前端带 token，新增拒绝用例通过。
- **纠偏幂等**：重叠窗口同句只产一条修正、无振荡，新增用例通过。
- **死代码/依赖清理**：全仓 grep `upload_video|upload_audio|uploadSessionMedia|sqlmodel` 仅剩有意保留处；回归全绿。
- **文档据实**：README/docs 与代码一致；TTS 实现后「语音」措辞如实保留。
- **虚拟滚动**：千句压力下更新/滚动稳定。

---

*— 本报告为只读分析与实施蓝图，未改动任何代码。配套：《项目改进审计报告_BabelFlux_2026-06-15.md》《项目汇报审计报告_BabelFlux_2026-06-15.md》。*
