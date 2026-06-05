"""实时纠偏（在线）。

同传过程中，随着后续上下文到达，前面已输出的译文可能需要修正。本模块提供
跨句轻量复核：当一句译文最终确定后，用低延迟模型（qwen-flash）回看最近几句，
判断是否存在可明确认定的错误（术语、人名/数字/否定、一词多义），仅在高置信度
时产出 revision_event，由前端高亮展示。

设计原则：
- 保守：默认不改。只修正会影响理解或术语一致性的明显错误。
- 限速：每分钟最多 N 次 LLM 复核，避免刷屏与高成本。
- 非阻塞：复核在后台任务运行，不阻塞主字幕流。
- 引擎内已注入热词（glossary corpus），故本模块聚焦跨句语义级修正。
"""

from __future__ import annotations

import json
import time
from collections import deque
from typing import Any

from app.services.providers.dashscope import DashScopeClient
from app.services.session_store import SegmentRecord

# 领域差异化的纠偏关注点（与会后完整纠偏共享同一套领域知识）
DOMAIN_REVISION_FOCUS = {
    "通用": "忠实保留原意；中文自然通顺；优先保证短句可读。",
    "技术": "保留 API、框架、模型、论文、产品名与缩写；不要把专有名词译成普通词。",
    "商务": "保留公司名、职位、货币、指标；数字与承诺类表述必须精确。",
    "教育": "概念解释准确；术语前后一致；避免过度口语化。",
    "医疗": "医学术语谨慎；剂量/数值/否定不得出错；不扩写诊断或治疗建议。",
    "法律": "法律术语准确；主体/义务/期限/否定不得含糊；不自行解释法条。",
}


def domain_focus(domain: str) -> str:
    return DOMAIN_REVISION_FOCUS.get(domain, DOMAIN_REVISION_FOCUS["通用"])


def build_realtime_revision_prompt(domain: str, source_language: str, target_language: str) -> str:
    return "\n".join(
        [
            "你是实时同声传译的「在线纠偏」模块，负责在传译进行中复核最近输出的译文。",
            f"领域：{domain}；源语言：{source_language}；目标语言：{target_language}。",
            f"领域关注点：{domain_focus(domain)}",
            "给你最近几句的「原文 + 当前译文」，其中最后一句是最新上下文。",
            "请判断**之前的句子**是否存在必须修正的错误（结合最新上下文）。",
            "硬性规则：",
            "1. 极度保守：若译文已可接受，返回空列表。绝不为了改而改、不做风格润色。",
            "2. 只修正：明显误译、术语不一致、人名/数字/单位/否定错误、一词多义选错义项。",
            "3. 修正必须给出完整替换后的整句译文（afterText），不要只给片段。",
            "4. 不得修改最后一句（它仍可能继续变化）。",
            "仅输出 JSON：{\"revisions\":[{\"segmentId\":\"...\",\"afterText\":\"完整修正译文\","
            "\"reason\":\"简短原因\",\"confidence\":0~1}]}。无需修正则 {\"revisions\":[]}。",
        ]
    )


class RealtimeReviser:
    def __init__(
        self,
        *,
        client: DashScopeClient | None,
        model: str,
        source_language: str,
        target_language: str,
        domain: str,
        window: int = 4,
        max_per_minute: int = 6,
        min_confidence: float = 0.62,
        enabled: bool = True,
    ) -> None:
        self.client = client
        self.model = model
        self.source_language = source_language
        self.target_language = target_language
        self.domain = domain
        self.window = window
        self.max_per_minute = max_per_minute
        self.min_confidence = min_confidence
        self.enabled = enabled and client is not None
        self._system_prompt = build_realtime_revision_prompt(
            domain, source_language, target_language
        )
        self._call_times: deque[float] = deque()

    def _rate_limited(self) -> bool:
        now = time.monotonic()
        while self._call_times and now - self._call_times[0] > 60:
            self._call_times.popleft()
        return len(self._call_times) >= self.max_per_minute

    async def review(self, recent: list[SegmentRecord]) -> list[dict[str, Any]]:
        """复核最近若干句，返回需要修正的列表（已过滤置信度/合法性）。"""
        if not self.enabled or self.client is None:
            return []
        # 至少要有「之前的句子」可改（窗口 >= 2）
        candidates = [s for s in recent if s.source_text and s.translation_text]
        if len(candidates) < 2:
            return []
        if self._rate_limited():
            return []

        window = candidates[-self.window :]
        revisable_ids = {s.segment_id for s in window[:-1]}  # 不含最后一句
        lines = []
        for seg in window:
            lines.append(
                f"[{seg.segment_id}] 原文: {seg.source_text}\n        译文: {seg.translation_text}"
            )
        user = "最近句子（最后一句为最新上下文，不可修改）：\n" + "\n".join(lines)

        self._call_times.append(time.monotonic())
        try:
            result = await self.client.generate(
                model=self.model,
                endpoint="text",
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": user},
                ],
                parameters={"result_format": "message", "temperature": 0.1},
            )
        except Exception:  # noqa: BLE001 - 纠偏失败不能影响主链路
            return []

        revisions = self._parse(result.content, revisable_ids, window)
        return revisions

    def _parse(
        self,
        content: str,
        revisable_ids: set[str],
        window: list[SegmentRecord],
    ) -> list[dict[str, Any]]:
        data = _loads_json(content)
        if not data:
            return []
        by_id = {s.segment_id: s for s in window}
        out: list[dict[str, Any]] = []
        for item in data.get("revisions", []):
            if not isinstance(item, dict):
                continue
            seg_id = item.get("segmentId")
            after = (item.get("afterText") or "").strip()
            confidence = float(item.get("confidence") or 0)
            if seg_id not in revisable_ids or not after:
                continue
            if confidence < self.min_confidence:
                continue
            before = by_id[seg_id].translation_text
            if after == before:
                continue
            out.append(
                {
                    "segmentId": seg_id,
                    "beforeText": before,
                    "afterText": after,
                    "reason": (item.get("reason") or "结合上下文修正").strip(),
                    "confidence": round(confidence, 2),
                }
            )
        return out


def _loads_json(content: str) -> dict[str, Any] | None:
    content = (content or "").strip()
    if not content:
        return None
    # 容错：剥离 ```json 围栏
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:]
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(content[start : end + 1])
    except (ValueError, TypeError):
        return None
