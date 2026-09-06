# 深度改进审查报告 · BabelFlux / 巴别流 同传

> 编制日期：2026-06-16 ｜ 代码版本：`origin/main` = `297c58f`（!52）
> 性质：在《项目改进审计报告（Top 10）》之上做的**逐文件细粒度审查**，覆盖此前未深读的全部模块。**全程只读，未修改任何代码。**
> 一句话：第一轮抓的是「架构级 Top 10」；本轮把没读到的文件读完，**新挖出 2 个高危安全面（REST 网关裸奔、SSRF）与一个"漂移的第二事实源"**，并补齐了一批中低危细节。

---

## 0. 本轮新读取的文件（第一轮未深读）

后端：`services/media.py`、`providers/dashscope/client.py`、`api/model_gateway.py`、`services/model_strategy.py`、`models/events.py`、`providers/mock.py`、`main.py`
桌面：`src/App.vue`（626 行）、`launcherBridge.ts`、`tauri.conf.json`
前端：`api/ws.ts`、`types/events.ts`、`components/workbench/FloatingCaption.vue`

---

## 1. 🔴 本轮最重要：两个"对外裸奔"的安全面（第一轮遗漏）

### SEC-1 🔴 REST 模型网关完全无鉴权 —— 一个开放的 LLM/ASR/TTS 代理
- **证据**：`api/model_gateway.py` 的 `/api/models/llm/generate`、`/asr/transcriptions`、`/tts/speech`、`/strategy/plan` 四个端点；`get_dashscope_client`（`model_gateway.py:27`）用**服务端 `.env` 里的 API key** 直连 DashScope；路由已挂载（`main.py:21`）。**全程无任何鉴权/限流。**
- **影响**：任何能访问后端的人，都能用**你的 key、你的配额**跑任意 LLM 生成 / ASR / TTS——比 WS 那处更危险（这是直接的、可脚本化的大模型代理，可被刷爆计费）。
- **建议方向**：加 API key / 登录态校验 + 速率限制；或在 demo 环境用环境开关默认关闭这些端点（仅 WS 主链路需要时内部调用）。
- **加分话术**：面试可主动讲"我们识别到 model_gateway 是开放代理，生产化首要补鉴权与限流"。

### SEC-2 🟠 在线直链 = ffmpeg SSRF 面
- **证据**：`url` 模式下，前端传入的 URL 经 `ws.py:250` → `pipeline.run_media(url)` → `media.py:_build_ffmpeg_args`（`media.py:70-88`）**直接交给 ffmpeg `-i`**；`_is_url`（`media.py:62`）放行 `http/https/rtmp/rtsp`，**无 host 白名单/内网拦截**。叠加 WS 主路径无鉴权（原审计 #1）。
- **影响**：攻击者可让服务器去拉**内网地址 / 云元数据（169.254.169.254）/ 内部服务**，构成 SSRF；ffmpeg 自身还支持更多协议，面更大。
- **缓解现状**：参数以列表传入（非 shell），**无经典命令注入**；但 SSRF 风险真实存在。
- **建议方向**：URL 协议+host 白名单、拒绝内网网段、可选出网代理隔离。

> 这两条加上原审计的 #1（主 WS 无鉴权），构成本项目**"演示可以、公网部署危险"**的完整安全画像——面试讲清楚边界即可，不必现场修。

---

## 2. 🟠 一致性：一个"漂移的第二事实源"

### CON-1 🟠 `model_strategy.py` 与真实实现已漂移，且其 provider 根本没接入
- **证据**：`/api/models/strategy/plan`（`model_gateway.py:77`）→ `build_strategy_plan`（`model_strategy.py:28`）返回的"策略计划"与真实运行链路**对不上**：
  - 纠偏窗口 `windowSegments=5`（`model_strategy.py:33`）vs 真实 `RealtimeReviser.window=4`（`revision.py:73`）；
  - 引用 `gummy_realtime` / `fun_asr` / `gummy-realtime-v1` 等 provider（`model_strategy.py:8-10,87-96`），但 `pipeline.py`/`ws.py` **只用 LiveTranslate，从不引用它们**（已 grep 确认）；
  - 领域文案 `DOMAIN_GUIDANCE`（`model_strategy.py:18-25`）与 `revision.py:DOMAIN_REVISION_FOCUS`（`:26-33`）**各写一份、措辞不同**。
- **影响**：strategy 端点输出的是"看起来很完整、实则没接线"的计划，被追问会暴露"宣称的多 provider 回退/策略"并不存在。
- **建议方向**：要么把 strategy 真正接进选型（让 windowSegments 等从单一配置驱动 revision/pipeline），要么明确标注为"设计蓝图/未接线"并下线该端点。

### CON-2 🟡 领域文案 / TTS / WS base 三处重复或不一致
- 领域指导散落 3 处（`revision.py`、`report.py` 经 `domain_focus`、`model_strategy.py`）——应收敛为单一来源。
- TTS 有两条独立路径：REST `client.synthesize_speech`（完整、24kHz、`client.py:199`，仅被 gateway 用）vs LiveTranslate realtime 模态（接收侧缺，原审计 #4）。
- WS base 配置变量不统一：`api/ws.ts:3` 用 `VITE_BACKEND_WS_URL`（含 `/api`），`desktop/src/api/sessionBridge.ts:5` 用 `VITE_BACKEND_WS_ORIGIN`（不含）——易配错。

---

## 3. 🟡 正确性 / 并发

| ID | 严重度 | 问题 | 证据 | 影响 |
| --- | --- | --- | --- | --- |
| COR-1 | 🟠 | 纠偏并发重入无幂等（原 #3 复述，本轮再确认） | `pipeline.py:986` | 同句被重复改写/振荡 |
| COR-2 | 🟡 | 网关超时映射漏 httpx 超时 | `model_gateway.py:43` 只 catch `asyncio.TimeoutError`，但 HTTP 走 `httpx.Timeout`→抛 `httpx.TimeoutException` | LLM HTTP 超时返回 500 而非 504 |
| COR-3 | 🟡 | `result` 可能未绑定 | `model_gateway.py:64-67` `except` 调 `_raise_provider_http_error`（恒 raise）后用 `result` | 依赖"恒抛"才不崩，脆弱 |

---

## 4. 🟡 性能 / 资源

| ID | 严重度 | 问题 | 证据 | 影响 |
| --- | --- | --- | --- | --- |
| PERF-1 | 🟠 | 每次 LLM 调用新建 `httpx.AsyncClient` | `client.py:280-283`（默认无共享 client，pipeline/report 均如此构造） | 每次纠偏/报告都重建连接池+TLS 握手，无复用→额外延迟与开销 |
| PERF-2 | 🟡 | DashScope 调用无重试/退避 | `client._post_json` / WS 收发无 retry | 瞬时 429/5xx 直接失败（纠偏静默吞、报告降级） |
| PERF-3 | 🟡 | 长会话前端 O(n²)+无虚拟滚动（原 #7） | `session.ts:443/707` | 数百句后更新/渲染劣化 |
| PERF-4 | 🟡 | 系统音频每帧全量扫信号 | `App.vue:280 hasPcmSignal` 遍历每帧 640 样本 | 微小持续开销 |

---

## 5. 🟡 健壮性 / UX

| ID | 严重度 | 问题 | 证据 | 影响 |
| --- | --- | --- | --- | --- |
| UX-1 | 🟠 | 无 WS 重连，且 UI 谎称"重连" | `api/ws.ts:38` 无重连；`FloatingCaption.vue:130` status=missing 显示"重连"字样但无重连逻辑 | 瞬断即结束，但 UI 暗示在重连=误导 |
| UX-2 | 🟡 | 子组件直接 mutate props | `FloatingCaption.vue:49/53/57/61/85` 直接改 `props.form.*` | Vue 反模式，应 emit；当前靠 store 对象引用"碰巧"生效 |
| UX-3 | 🟡 | 桌面 handoff 仅显示单句、无历史 | `App.vue:applyEvent` 每次覆盖单个 `pair` | 与 Web 端字幕流体验不一致（悬浮窗设计取舍，宜说明） |
| UX-4 | 🟡 | deep-link 解析不够健壮 | `launcherBridge.ts:11` `new URL()` 无 try/catch；`:18` `displayMode` 未校验直接 cast | 畸形 deep link 抛错；displayMode 可被传入任意串 |

> 🟢 **澄清优点**：`FloatingCaption.vue:180/188` 用 `{{ }}` **文本插值**渲染模型返回文本，**非 `v-html`** → 无 XSS 注入面。

---

## 6. 🟡 死代码 / 整洁 / 品牌遗留

| ID | 问题 | 证据 |
| --- | --- | --- |
| CLN-1 | 上传文件→后端 ffmpeg 全链路死代码（原 #5） | `session.ts:1236`、`sessions.py:124`、`ws.py:253` |
| CLN-2 | `probe_duration_seconds` 死代码（已确认无调用） | `media.py:91` |
| CLN-3 | `sqlmodel` 声明零使用（原 #10） | `pyproject.toml:14` |
| CLN-4 | 后端 mock 仅 4 事件单句——"mock 跑通全链路"偏弱，富 demo 实来自前端 fixture | `providers/mock.py:6-42` vs `fixtures/testVideo` |
| CLN-5 | 品牌遗留 lingosync：tauri `identifier=com.redamancyzxp.lingosync`、`localStorage lingosync.clientSeen`、deep-link scheme | `tauri.conf.json:5`、`session.ts:944` |

---

## 7. 🟠 测试覆盖矩阵

| 子系统 | 测试 | 评价 |
| --- | --- | --- |
| 后端 | 7 个文件（dashscope_provider / health / media_tools / model_gateway_api / model_strategy / pipeline / sessions） | 覆盖较好 |
| 前端 | 4 个文件（App / StreamLine / useAudioCapture / subtitleTimeline） | 覆盖关键流 |
| **桌面** | **0** | **App.vue（626 行）+ Rust（audio_capture/native_drag）全无测试** ← TEST-1 🟠 |
| 安全/并发 | 无针对性用例 | SSRF/鉴权/纠偏重入未被测试断言 ← TEST-2 🟡 |

---

## 8. 确认的工程优点（汇报可正面引用）
- 🟢 **事件契约单一事实源**：`models/events.py`（Pydantic by_alias）↔ 前端 `types/events.ts` ↔ `mock.py` 三者一致，无漂移。
- 🟢 **无 XSS**：字幕用文本插值渲染模型文本（`FloatingCaption.vue`）。
- 🟢 **媒体子进程清理完善**：`media.py:186-198` terminate→wait(3s)→kill，无僵尸进程；实时节奏对齐 `start+index*interval` 防漂移。
- 🟢 **桌面生命周期清理**：`App.vue:onUnmounted` 停采集 + 解绑 deep-link/快捷键监听；pointer-capture 拖拽。
- 🟢 **TTS REST 路径其实是完整可用的**（`client.synthesize_speech` 24kHz）——实现实时 TTS 时可复用其编解码经验。

---

## 9. 优先级建议（增量并入七日计划）

**应抬入"必做/应做"的本轮新增项：**
1. **SEC-1 REST 网关鉴权**（🔴）——与原 #1 WS 鉴权**一并做**（同一套 token/开关），D4 一天内顺手覆盖两处。
2. **SEC-2 SSRF host 白名单**（🟠）——`url` 模式加协议+内网拦截，约 0.3 人天。
3. **CON-1 strategy 漂移**（🟠）——最省力是**下线/标注** `/strategy/plan` 为"设计蓝图未接线"，避免被追问；彻底修需接线，工作量大，列路线图。
4. **PERF-1 复用 httpx client**（🟠）——给 `DashScopeClient` 注入共享 `AsyncClient`，对每句纠偏的延迟有实质收益，约 0.3 人天。

**其余（UX-1 重连/谎称、UX-2 prop mutation、CLN-2 死代码、TEST-1 桌面测试）** 列入"整洁与健壮"批次，随手清理即可。

> 与已有报告的关系：本报告**只新增细粒度发现**，原《项目改进审计报告》的 Top 10 与《功能实施与改进方案审计报告》的七日排期仍有效；建议把 SEC-1/SEC-2/CON-1/PERF-1 增补进七日计划的 D1（清理+鉴权）与 D4（安全/正确性）两天。

---

## 10. 审查覆盖总览（截至本轮）

| 模块 | 状态 |
| --- | --- |
| 后端 pipeline/revision/report/ws/realtime/sessions/handoff/session_events/session_store/config | ✅ 已深读 |
| 后端 media/client/model_gateway/model_strategy/models/mock/main | ✅ 本轮补全 |
| 前端 session.ts/useAudioCapture/StreamLine/useStickyFollow/client/ws/types/FloatingCaption | ✅ 已深读 |
| 桌面 main.rs/audio_capture.rs/App.vue/sessionBridge/nativeAudioCapture/launcherBridge/capabilities/tauri.conf | ✅ 已深读 |
| 前端其余展示组件（MediaPanel/SourcePreparation/SettingsDialog/SelectField/各 View） | ⚪ 未逐行（属纯展示，风险低，未纳入本轮细查） |

---

*— 深度审查完 · 本报告只读分析，未改动任何代码。配套：《项目改进审计报告_2026-06-15》《项目汇报审计报告_2026-06-15》《功能实施与改进方案审计报告_2026-06-16》。*
