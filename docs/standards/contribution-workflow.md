# BabelFlux 提交与合并规范

本文档是仓库当前唯一生效的协作入口。所有 Issue、Pull Request、提交和评论默认使用中文；代码标识、命令和第三方协议名称保留原文。

## 1. 工作单元

- 先创建一个中文 Issue，再从最新 `main` 创建对应分支。
- 一个 Issue 只对应一个 PR；一个 PR 只解决一个可验收的问题。
- 大功能拆成可独立验证的小 PR，每个有意义的阶段及时提交，不积累到最后一次导入。
- PR 描述必须写 `Closes #<issue>`，并说明变更范围、风险、验证命令和回滚方式。

## 2. 分支与提交

### 标题命名

Issue 和 Pull Request 统一使用一行标题：`<gitemoji> <type>(<scope>): <中文动词短语>`。`type` 使用 `feat`、`fix`、`refactor`、`docs`、`perf`、`test`、`ci`、`chore` 或 `security`；`scope` 使用小写英文模块名，如 `web`、`backend`、`pipeline`、`ws`、`history`，没有明确模块时可以省略。标题主体以中文动词开头，禁止乱码、无意义英文和句末标点。

同一变更的 Issue 与 PR 共享相同的 gitemoji、type、scope 和中文标题主体。创建或编辑元数据后，必须检查 GitHub 页面实际 UTF-8 显示；标题模板示例：`🐛 fix(ws): 防止非法 media_clock 中断连接`。

分支使用 `feat/<topic>`、`fix/<topic>`、`refactor/<topic>`、`test/<topic>`、`docs/<topic>` 或 `chore/<topic>`。从 `main` 开始，提交前确认：

```bash
git status --short --branch
git fetch origin main
git diff --check
```

提交格式为 `<gitemoji> <type>(<scope>): <中文动词短句>`，例如：

```text
✨ feat(web): 增加报告历史筛选
🐛 fix(ws): 拒绝非法媒体时钟
♻️ refactor(pipeline): 拆分字幕显示策略
🧪 test(session): 覆盖断线恢复路径
📚 docs: 更新协作规范
```

摘要尽量不超过 72 个字符；正文记录背景、方案、验证和已知限制。一个提交应保持可运行、可审查、可回滚，避免把格式化或无关重构混入功能提交。

## 3. PR 评论与 STAR 记录

每个 PR 至少覆盖架构决策、实验过程和验证收尾三个有实质内容的中文事实节点；出现新的 CI 结果、审查意见、失败实验或回滚决策时应继续追加评论。评论数量不设人为上限，但每条都必须来自真实改动或可复现证据，不预设结果，不为了简历制造 PR。

涉及性能、稳定性或缺陷时使用以下结构：

```text
Situation（情境）：现象、数据规模、影响范围
Task（任务）：要解决的问题与验收标准
Action（行动）：数据结构、算法、设计模式或代码改动
Result（结果）：可复现的测试/基准、前后数据、剩余风险
```

没有实际测量时必须写“未测量”，不得使用“提升了 X%”等无依据表述。失败实验和采用替代方案的原因同样记录。

## 4. SSH、验证与合并

- Git 远端使用 SSH（例如 `git@github.com:ZhaoXingPeng/BabelFLUX.git`），禁止为提交或合并打开浏览器、弹框或把 token 写入仓库。
- GitHub API 只通过本机临时凭据调用；token 不打印、不写入日志、不放入 Issue/PR。
- 本地质量门禁通过后推送分支并创建 PR。当前门禁包括后端测试/Ruff、前端测试/构建和桌面端构建；CI 失败必须在 PR 评论中说明原因和修复计划。
- PR 审查完成后，在本地执行 `git fetch origin main`、`git checkout main`、`git merge --no-ff <branch>`，再通过 SSH 推送 `main`。
- API 核验 PR 已合并、Issue 已关闭且评论完整后，删除远端和本地功能分支，确认 `main` 与 `origin/main` 同步且工作区干净。

## 5. 回滚与安全

合并前保留可回滚的提交边界；回滚优先使用反向提交或恢复 PR，不改写共享分支历史。错误事件和日志不得包含密钥、token、Cookie、完整请求头、原始音频或用户隐私文本。

历史 Gitee/浏览器流程仅作为归档材料，不得作为当前操作指引。
