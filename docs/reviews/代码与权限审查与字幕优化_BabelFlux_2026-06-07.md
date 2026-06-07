# BabelFlux 代码/架构审查 + Windows 音频权限审查 + 字幕展示优化

> 日期：2026-06-07 · 基线：`main`（!47，工作树干净）
> 范围：①字幕展示柔和度样式优化（不降低同传效率）②前后端+桌面端代码逻辑与功能架构审查 ③Windows 悬浮窗音频权限与流程
> 验证手段说明：本审查在 Linux 环境完成，可验证 **前端 vue-tsc / vitest / vite build、后端 pytest / ruff**；**无法编译/运行 Rust(Tauri/Windows) 与真实 DashScope 链路**，故涉及 Rust/真实链路的修复以「待落地建议（附确切 diff）」形式给出，未盲推不可验证改动。

---

## 一、字幕展示柔和度优化（任务①，本 PR 已落地）

**结论："顿/不柔和"的两个根因都在展示层，与同传时序/时延/pipeline 完全无关；本次只动渲染与滚动，未触碰任何产出时序，故同传效率不降反而前端主线程开销下降（间接利于实时吞吐）。**

### 根因 1：StreamLine 整行重挂载（最主要）
`StreamLine.vue` 旧实现 `text.split(/\s+/)` 按空格分词。中文没有空格 → **整句译文是单个 token**，`:key` 含 token 文本；每次 partial 文本增长 → key 变 → Vue 销毁并重建该 `<span>` → CSS `streamToken`（位移+透明度）入场动画对**整行**重放 = 每次 partial 更新都闪一下。

**修复**：已定稿/已校正句直接渲染纯文本节点（其入场由卡片级 GSAP 负责，无需逐字动画）；仅「识别中」的当前句做逐单元入场，且改为 **CJK 按字、拉丁文按词、空白单独成块 + 索引作为 key** —— 已显示的单元原地复用（不重挂载、不重放），只有新增的尾部单元淡入。新增 `StreamLine.test.ts` 锁定该行为。

### 根因 2：useStickyFollow 滚动补间抖动
`useStickyFollow.ts` 的 follow 签名含 `translation` 文本，每个 partial 字符都触发 `gsap.to(scrollTo, {overwrite:"auto"})` → 0.42s 补间被反复打断重启 → 滚动永不稳定地抖。

**修复**：滚动补间「合并去抖」——记录上次目标位，目标位移 < 28px（当前句逐字增长的微小漂移）时跳过，让进行中的滚动平滑走完；累计超阈值或切到新句（大跳跃）才发起新补间 → 平滑分步跟随，不再逐字抖动。仍尊重 `prefers-reduced-motion`（直接定位）。

### 附带：悬浮字幕（FloatingCaption / 桌面 overlay）整句硬切
`FloatingCaption.vue` 用纯 `{{ }}` 渲染，切句时硬切。**修复**：仅在 `segmentId` 变化（换句）时做一次轻量交叉淡入；句内逐字增长不触发，保持原地平滑更新；尊重 reduce-motion。

> 关于「继续提升同传效率」：真正的端到端时延优化集中在后端实时链路（已有 `perf: reduce realtime interpretation latency` 在 main）。继续压低需在真实 DashScope 链路上做时延 spike 验证，属高风险、不可在本机验证，本 PR 不动以免回退既有效率；可作为后续独立工作项。本 PR 的展示层优化顺带减少了主线程重排/补间风暴，对前端「跟得上实时流」是正向的。

---

## 二、代码与架构审查（任务②）

**总评：架构分层清晰、职责单一，完成度高。** `events.py` 作为前后端契约单一事实源（camelCase 别名，前端 `types/events.ts` 严格对齐，无契约漂移）；provider 把 DashScope 私有协议归一化为 `NormalizedEvent` 再由 `pipeline` 编排，解耦得当；源用 `item_id`/译文用 `response_id` 的 FIFO 绑定专门对抗「译文滞后跨句」真实问题且有回归覆盖；报告 LLM 降级（`isinstance` 防御 + 纯实时译文兜底）与断连→REST/磁盘兜底考虑周到；资源清理（`aclosing`/`_drain`/ffmpeg `terminate`/AudioContext `close`/Tauri `onUnmounted`）到位，未见明显 task 泄漏或 queue 死锁。**作为比赛/演示项目，质量明显高于平均。**

### 发现（按严重度；标注本 PR 处理情况）

- **🟠 "客户端时钟双向同步" 实为单向只读观测**（`pipeline.py` `_emit_client_clock_sync_if_due`/`update_client_clock`）：算出 `lag_ms` 只用于展示，无任何一方据此调速；丢帧机制下 `elapsed_ms`（按喂入字节累加）会与真实播放钟漂移，而字幕 `startMs` 依赖它 → 时间码可能漂。**建议**：要么明确「实时优先、放弃严格对齐」并在 UI 弱化 lagMs 语义；要么用 `_client_playback_ms` 校准 `elapsed_ms`。**【本 PR 不动】**：属时延/同步核心，改动有回退既有效率的风险且无法在本机用真实链路验证 → 列为后续独立工作项。
- **🟠 暂停期间采集帧持续丢弃**（`ws.py` `pause_session` 只设 `_pause_event`，接收循环仍塞满队列丢最旧帧）：主要影响纯采集源；上传媒体因前端 `element.pause()` 停止产帧而基本不受影响。**建议**：恢复时同步 `elapsed_ms` 基准。**【建议，未改】**
- **🟡 TTS 为「接收侧未实现」**：`model_strategy.py` 在 `tts_enabled` 时请求 `modalities:["text","audio"]` 并接 TTS provider，但 `pipeline._handle` 未处理 `kind=="audio"` 事件。**实测确认 `tts_enabled` 全链路默认 `False` 且前端从不置 true** → 当前**不产生计费、无坏功能**，只是端到端未接通。**建议**：保持默认 False，直到补齐音频事件下发+前端播放；若将来开启务必同时实现接收侧，避免空计费。**【确认为非活跃问题，未改】**
- **🟡 上传文件→后端 ffmpeg 解码链路为前端不可达死代码**：`session.ts` 把 `video-file`/`audio-file` 映射为 `media_element_audio`，永不产生 `upload_video`/`upload_audio`；但 `startConfiguredSession` 的 `uploadSessionMedia` 分支、`ws.py` 解码分支、`sessions.py /media` 端点仍在。**建议**：删除前端死分支或注释标注「当前未启用」，避免误读为两条活跃路径。**【建议，未改：删除需确认非有意兜底】**
- **🟡 实时纠偏并发重入可能覆盖已纠偏段**（`pipeline._apply_revision` 无 `seg.status != "revised"` / `before==now` 校验，多个 review task 并发无串行化）。**建议**：施加前校验，避免对已纠偏段二次覆盖。**【建议，未改】**
- **🔵 其它**：`session_store` 无 TTL/清理（长跑内存单增，演示可接受）；WS 主连接对无 token 连接直接 `get_or_create`（演示可接受，生产建议轻量鉴权）；`_loads_json` 的反引号围栏剥离偏脆（建议正则精确剥离）；`_normalize_source_language` 的 `None` 比较是死分支。

---

## 三、Windows 悬浮窗音频权限与流程（任务③）

**总判断：方向正确，核心实现合规。** 原生系统音频走 **WASAPI loopback 标准官方做法**（render 设备上开 capture，shared 模式，引擎自动重采样到 16k 单声道），**全程无需管理员/UAC、不触发隐私开关，符合 Win10 1803+ 最佳实践**。`audio_capture.rs` 的 COM 初始化（工作线程 `initialize_mta`/`deinitialize`）、事件驱动采集、错误经事件回前端并触发降级——整体正确。但页内（WebView2）媒体路径与 deep-link 注册有需收口处。

### 发现与处理

- **🔴 WebView2 内麦克风/屏幕/标签页采集可能直接失败**：桌面 standalone 的 `microphone`/`screen_window`/`browser_audio` 走 WebView2 内的 `getUserMedia`/`getDisplayMedia`，而 Rust 侧未处理 WebView2 `PermissionRequested`，默认可能被拒；系统音频走原生 loopback 则正常。
  - **【本 PR 已部分缓解】**：`acquireStream` 现对权限被拒/无设备/被占用/用户取消给出**对症中文指引**（如「请在 Windows 设置→隐私→麦克风允许桌面应用访问」），不再统一吞成「采集启动失败」。新增 `useAudioCapture.test.ts` 覆盖。
  - **【待落地建议，需 Windows 验证】**：二选一——(A) 若在目标 WebView2 版本上确认这三项不可用，则在桌面端隐藏/禁用它们，仅保留「Windows 系统音频」(原生 loopback)；(B) 在 Rust 侧实现 WebView2 `PermissionRequested` 对 `Microphone` 授权。建议先在 Windows 实测 getUserMedia 是否弹窗/可用再决定，避免误删可用功能。
- **🟠 deep-link 在 Windows debug 构建不注册**：`main.rs` 原 cfg `all(target_os="windows", not(debug_assertions))` 使 `tauri dev` 期间不注册 `lingosync://` → 开发期无法验证「激活客户端」唤起。**【本 PR 已修】**：cfg 拓宽为 `any(target_os="linux", target_os="windows")`，debug 也注册（内部代码不变，零编译风险）。仍建议统一注册来源：优先插件 `register_all`，`register-release-deep-link.ps1` 仅作 fallback。
- **🟠 Tauri capability 漏声明前端实际调用的窗口权限**：前端 JS 调 `currentWindow.outerPosition()`/`scaleFactor()`，`capabilities/default.json` 未显式列 `core:window:allow-outer-position` / `allow-scale-factor`（`core:default` 多半已含，故当前能跑）。**【未改，列建议】**：本机无法编译验证标识符，为避免误写导致 Tauri 构建失败，未直接改；建议在 Windows 构建环境下追加（防御未来 `core:default` 收紧）：
  ```json
  "core:window:allow-outer-position",
  "core:window:allow-scale-factor",
  ```
- **🟡 `sourcePermission` 在 `createSession` 时写死 `"granted"`**（`desktop/src/App.vue`）：属乐观假设，未做权限探测。当前为后端元数据、无害；结合上面的失败提示缺失才成短板。已通过 acquireStream 的对症提示缓解体验；如需更严谨可在采集成功后再回填真实权限态。**【建议，未改】**
- **🔵 loopback 细节优化**：缓冲时长用 `min_period` 偏小，极低延迟下偶发 glitch，可改 `default_period` 或显式 ~20–40ms；`emit_chunk` 失败即 `?` 终止整条采集线程偏激进，可忽略单帧。**【建议，未改】**

---

## 四、本 PR 改动清单与验证

**已落地（均可验证）**
- `frontend/src/components/workbench/StreamLine.vue` — CJK 感知分词 + 仅 partial 行逐单元入场 + 已定稿纯文本
- `frontend/src/composables/useStickyFollow.ts` — 滚动补间合并去抖
- `frontend/src/components/workbench/FloatingCaption.vue` — 换句轻量交叉淡入
- `frontend/src/composables/useAudioCapture.ts` — `describeMediaError` 媒体权限错误对症提示
- `desktop/src-tauri/src/main.rs` — deep-link debug 构建也注册
- 新增测试：`StreamLine.test.ts`（4）、`useAudioCapture.test.ts`（5）

**验证结果**：前端 `vue-tsc --noEmit` exit 0；`vitest run` **28 passed**；`vite build` 成功（89 modules）。后端未改动，回归 `pytest` **36 passed**、`ruff` clean。

**未在本 PR 落地（附确切建议，需 Windows/真实链路验证后处理）**：客户端时钟同步收敛、暂停期帧丢弃、纠偏重入校验、上传死代码清理、TTS 接收侧实现、WebView2 权限处理或桌面源收窄、capability 追加、loopback 缓冲细节。详见上文各「建议」。
