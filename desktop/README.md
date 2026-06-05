# Desktop Client

桌面客户端阶段用于承接 Web 无法完成的系统级能力：

1. 电脑全局悬浮字幕。
2. 系统音频或应用音频采集。
3. 置顶窗口、透明度、锁定、字号、热键和托盘。
4. 通过 `lingosync://floating/start` 从 Web 快速启动。

当前目录已起 Vue + Tauri 2 悬浮字幕骨架，1.0 范围是“展示面”：

- Web 通过 `/api/sessions/{sessionId}/handoff` 获取短时单用 token。
- `lingosync://floating/start?...&token=h_*` 唤起桌面端。
- 桌面端用 token 调 `/api/sessions/handoff/claim` 兑换短时 WS token。
- 透明置顶 overlay 复用 `frontend/src/components/workbench/FloatingCaption.vue` 和 `frontend/src/styles/main.css`，避免样式分叉。
- 系统音频采集、托盘、多 overlay、自动更新不在 1.0 内。

## Run

```bash
cd desktop
npm install
npm run dev
npm run tauri dev
```

本地浏览器预览可使用：

```text
http://localhost:5175/?displayMode=bilingual
```

真实接管需要 Web 工作台生成的 deep link：

```text
lingosync://floating/start?sessionId=...&displayMode=bilingual&token=h_...
```

## Phase Plan

1. PR22：客户端工程脚手架。
2. PR23：deep link 启动闭环。
3. PR24：全局悬浮字幕窗口 MVP。
4. PR25：系统音频采集原型。
5. PR26：客户端会话与后端协议打通。

本轮实现对应 `docs/architecture/客户端悬浮框方案_v1.0.md` 的最小 1.0。

详细规划见：

```text
docs/architecture/桌面客户端阶段规划_AI同声传译助手.txt
```
