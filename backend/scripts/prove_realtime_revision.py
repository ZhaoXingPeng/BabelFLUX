"""真实 qwen-flash 实时纠偏能力证明（非 mock）。

构造一个「前句术语译错、后句上下文揭示」的跨句场景，调用真实模型，
验证 RealtimeReviser 能在该纠时产出 revision_event。
"""
import asyncio

from app.core.config import settings
from app.services.providers.dashscope import DashScopeClient, DashScopeConfig
from app.services.revision import RealtimeReviser
from app.services.session_store import SegmentRecord


async def main() -> None:
    client = DashScopeClient(DashScopeConfig.from_settings(settings))
    reviser = RealtimeReviser(
        client=client,
        model=settings.realtime_revision_model,
        source_language="en",
        target_language="zh",
        domain="技术",
        window=4,
        max_per_minute=60,
        min_confidence=0.62,
    )

    # 场景：seg1 把 ML 的 "Transformer" 误译成「变压器」；seg2 给出自注意力/词元语境，
    # 揭示这是机器学习架构 Transformer，应纠正 seg1。seg2 为最新句不可改。
    segs = [
        SegmentRecord(
            segment_id="seg-1", index=0, start_ms=0, end_ms=3000,
            source_text="The transformer is the core of our architecture.",
            translation_text="变压器是我们架构的核心。",
            status="final",
        ),
        SegmentRecord(
            segment_id="seg-2", index=1, start_ms=3000, end_ms=6000,
            source_text="It processes tokens through a self-attention mechanism.",
            translation_text="它通过自注意力机制处理词元。",
            status="final",
        ),
    ]

    print(f"[model] {settings.realtime_revision_model}  enabled={reviser.enabled}")
    revisions = await reviser.review(segs)
    print(f"[revisions] count={len(revisions)}")
    for r in revisions:
        print(f"  segmentId={r['segmentId']} conf={r['confidence']}")
        print(f"    before: {r['beforeText']}")
        print(f"    after : {r['afterText']}")
        print(f"    reason: {r['reason']}")
    if not revisions:
        print("  （本次未产出纠偏）")


if __name__ == "__main__":
    asyncio.run(main())
