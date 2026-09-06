# 时间线聚合性能实验

## Situation（情境）

前端播放状态需要把源字幕和译文按 `segmentId` 合并。旧实现先用 `includes` 去重，再对每个 id 调用两次 `find`；当段数增长时，去重和查找都会重复扫描数组，时间复杂度为 O(n²)。

## Task（任务）

在不改变输出顺序、缺失侧处理和时间边界的前提下，将聚合过程降为 O(n)，并保留可重复的性能基线，避免“优化”只凭主观判断。

## Action（行动）

在 `frontend/src/stores/sessionTimeline.ts` 中使用一次 `Map<string, { source, translation }>` 聚合两侧数据，最后统一排序；重复 `segmentId` 保留各侧首次出现的记录。新增 `sessionTimeline.bench.ts` 和 `npm run bench:timeline`，基线实现与优化实现共用同一组输入。

## Result（结果）

实验命令：

```text
cd frontend
npm run bench:timeline -- --run
```

数据规模：2,000 个源段 + 2,000 个译文段，Node 22.17.0、Vitest 4.1.8。

| 实现 | 平均耗时 | 吞吐 |
| --- | ---: | ---: |
| `includes + find` 基线 | 13.9607 ms | 71.63 ops/s |
| `Map` 聚合 | 0.1837 ms | 5,443.73 ops/s |

优化实现约 **76.0 倍** 更快。功能验证同时通过前端 55 项测试和生产构建；剩余风险是实际会话段数远低于 benchmark 上限，线上收益需在长会话埋点后复核。

## PR 评论摘录

```text
实验：用 2,000 个源段和 2,000 个译文段，对比旧 includes/find 与 Map 聚合。
结果：平均 13.9607ms -> 0.1837ms，吞吐 71.63 -> 5,443.73 ops/s，约 76.0x。
结论：保留 Map 聚合；输出语义由 55 项前端测试和生产构建确认。
```
