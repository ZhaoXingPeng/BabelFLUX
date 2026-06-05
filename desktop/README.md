# Desktop Client

桌面客户端阶段用于承接 Web 无法完成的系统级能力：

1. 电脑全局悬浮字幕。
2. 系统音频或应用音频采集。
3. 置顶窗口、透明度、锁定、字号、热键和托盘。
4. 通过 `lingosync://floating/start` 从 Web 快速启动。

当前目录先作为客户端阶段入口，不在本 PR 中引入完整客户端工程。

## Phase Plan

1. PR22：客户端工程脚手架。
2. PR23：deep link 启动闭环。
3. PR24：全局悬浮字幕窗口 MVP。
4. PR25：系统音频采集原型。
5. PR26：客户端会话与后端协议打通。

详细规划见：

```text
docs/architecture/桌面客户端阶段规划_AI同声传译助手.txt
```
