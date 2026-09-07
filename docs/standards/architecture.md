# BabelFlux 工程与架构规范

本文是项目架构的约束基线。实现可以演进，但跨层边界、事件契约和验证要求必须保持可追踪。

## 分层

```text
Web/Desktop adapters
        |
API + WebSocket contract (app/api, models/events.py)
        |
Orchestration (services/pipeline.py)
        |
Domain services (session store, revision, report, media)
        |
Provider adapters (services/providers/*)
```

- `app/api` 只负责协议适配、认证和生命周期编排，不承载字幕算法。
- `models/events.py` 是前后端事件契约的单一事实源；新增字段必须同时更新前端类型和契约测试。
- `services/pipeline.py` 负责时序和状态机；纯文本转换、媒体解析、报告生成应放在独立模块。
- `services/model_selection.py` 负责把产品层模型档位解析为已验证 provider 支持的具体模型；禁止在 UI 或 API 层直接拼接 provider 参数。
- provider 只能通过稳定的领域接口向上提供能力，不能把第三方 SDK 类型泄漏到 API 或前端。
- `frontend` 和 `desktop` 共享协议类型语义，但不能直接依赖后端实现细节。
- `SessionRecord` 的段索引必须通过 `get_segment`/`remove_segment` 等领域接口访问；业务编排不得依赖 `_by_id` 等私有存储细节。

## 依赖方向

依赖只能向下流动：API -> services -> providers。禁止 provider 反向导入 API，禁止服务模块互相读取对方的私有状态。需要共享行为时，提取小型纯模块或明确的领域接口。

## 长文件拆分规则

文件超过 500 行或同时包含三类以上职责时，创建独立拆分 Issue。拆分顺序：

1. 先为现有行为补单元/契约测试。
2. 把无副作用函数提取到领域模块，保持原方法提供兼容代理，先不改变调用方。
3. 再移动状态机或 I/O 适配器，逐步减少代理。
4. 每一步都运行完整质量门禁，并在 PR 中记录前后行数、性能和行为差异。

当前拆分队列：

- `backend/app/services/pipeline.py`：source text normalization -> display alignment -> session orchestration（显示规划已移出，事件编排与会话状态仍在此处）。
- `frontend/src/stores/session.ts`：WebSocket transport -> session reducer -> report/history state（请求 payload 已移出，事件归并与报告状态仍待拆分）。
- `backend/app/api/ws.py`：连接生命周期 -> inbound command handling -> outbound event serialization。

已完成的纯逻辑边界（2026-09-07）：

- `backend/app/services/language_policy.py`：自动源语言推断、provider 初始语言提示、预检条件和语言对建议；由 `pipeline.py` 保留兼容代理。
- `backend/app/services/display_planner.py`：源/译文显示切分、数量对齐和时间边界规划；纯函数不读取会话或执行 I/O。
- `frontend/src/stores/sessionPayload.ts`：来源到 `inputMode` 映射、语言标签转换和 `CreateSessionPayload` 组装；store 保留兼容入口。
- `frontend/src/stores/sessionTimeline.ts` 的 `applyRevisionToSegments`：按 revision 不可变更新源/译文字幕数组；store 只负责写回响应式状态。
- `frontend/src/stores/outputLatency.ts`：以有界样本、segment 去重和中位数估计封装输出延迟跟踪；session store 只负责转发翻译事件和读取估计值。
- `backend/app/api/handoff_ws.py`：只读 handoff 事件回放、转发和订阅清理；主 `ws.py` 仅负责会话生命周期与输入命令编排。

上述拆分均不依赖 API、provider 或 WebSocket I/O，并配有直接单元测试。后续拆分必须先确认目标职责尚未被这些模块覆盖，再按本节顺序补测试、保留代理并记录验证结果。

## 事件契约

- 事件名称使用 `snake_case`，字段使用 `camelCase`。
- 服务端可选的 `audio_segment` 事件携带 `segmentId`、`audioBase64` 和 `sampleRate`；Web 与桌面适配器都必须在 `ttsEnabled` 会话中消费该 PCM 音频，并在会话结束时释放播放资源。
- handoff 事件订阅保持有界队列；发生溢出时优先淘汰最早的 `audio_segment`，字幕、修订和报告等控制面事件优先保留。
- 新字段默认可选并提供兼容值；删除或改语义必须增加契约版本或迁移策略。
- 服务端事件必须有前端解析测试；前端发送的命令必须有后端校验测试。
- 错误事件不得包含密钥、完整请求头、原始音频或用户隐私文本。

## 测试策略

- 纯函数：边界条件和性质测试优先，目标是快速、确定、无网络。
- 服务层：使用 fake provider 验证状态转移、降级和资源清理。
- API/WebSocket：验证状态码、事件顺序、字段兼容性和断线行为。
- UI：覆盖用户可见状态、键盘/鼠标交互和失败路径；媒体 fixture 使用仓库内固定样本。
- 真实模型、真实设备和长时媒体属于显式联调实验，不作为每次 PR 的必需门禁。

## 变更记录模板

架构调整至少记录：背景、约束、方案、替代方案、风险、迁移步骤、验证结果和回滚方式。小型调整可直接写入 PR；跨模块调整应新增 `docs/adr/NNNN-<topic>.md`。
