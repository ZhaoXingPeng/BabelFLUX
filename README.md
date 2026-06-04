# AI Product Lab

本仓库用于 AI 产品项目的方案确认、需求拆解、开发迭代与评审资料沉淀。

当前候选议题：

1. AI 英语口语陪练
2. AI 同声传译助手
3. AI 小说转剧本工具

## 目录结构

```text
docs/
  project-plans/   三个候选议题的初步方案
  requirements/    原始项目要求与评审规范
  process/         开发、提交、PR 相关流程说明
```

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
feat/scenario-selection
docs/yaml-schema
chore/init-repo
```

## 推荐提交信息

```text
feat: 新增场景选择入口
fix: 修复字幕修正状态更新
docs: 补充 YAML Schema 设计说明
chore: 初始化项目结构
```

## 当前状态

当前阶段先完成仓库初始化和三个候选议题的初步方案沉淀。确认最终议题后，再按功能拆分 PR 持续开发。
