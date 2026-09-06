from app.services.display_planner import (
    build_display_plan,
    split_source_display,
    split_target_display,
)


def test_split_helpers_keep_long_bilingual_text_readable() -> None:
    source = " ".join(f"word{index}" for index in range(40))
    translation = "这是一段很长的中文译文，用来验证显示规划会按可读长度拆分字幕。" * 3

    source_parts = split_source_display(source, "en")
    target_parts = split_target_display(translation, "zh")

    assert len(source_parts) > 1
    assert len(target_parts) > 1
    assert " ".join(source_parts).replace("  ", " ") == source


def test_build_display_plan_aligns_parts_and_bounds() -> None:
    plan = build_display_plan(
        source_text="",
        translation_text="",
        source_language="en",
        target_language="zh",
        source_final=True,
        translation_final=True,
        previous_count=1,
        previous_source_parts=[],
        previous_translation_parts=[],
        root_start_ms=0,
        root_end_ms=12_000,
        elapsed_ms=12_000,
    )

    assert plan is None


def test_build_display_plan_returns_monotonic_bounds_for_final_text() -> None:
    plan = build_display_plan(
        source_text="One short sentence.",
        translation_text="一条简短句子。",
        source_language="en",
        target_language="zh",
        source_final=True,
        translation_final=True,
        previous_count=1,
        previous_source_parts=[],
        previous_translation_parts=[],
        root_start_ms=2_000,
        root_end_ms=6_000,
        elapsed_ms=6_000,
    )

    assert plan is not None
    assert len(plan.source_parts) == len(plan.translation_parts) == plan.count
    assert len(plan.bounds) == plan.count
    assert plan.bounds[0][0] == 2_000
    assert all(start <= end for start, end in plan.bounds)
    assert all(
        plan.bounds[index][1] <= plan.bounds[index + 1][0]
        for index in range(len(plan.bounds) - 1)
    )


def test_build_display_plan_preserves_existing_split_count() -> None:
    plan = build_display_plan(
        source_text="Updated source.",
        translation_text="更新后的译文。",
        source_language="en",
        target_language="zh",
        source_final=False,
        translation_final=False,
        previous_count=2,
        previous_source_parts=["Existing source one.", "Existing source two."],
        previous_translation_parts=["已有译文一。", "已有译文二。"],
        root_start_ms=0,
        root_end_ms=0,
        elapsed_ms=500,
    )

    assert plan is not None
    assert plan.count == 2
    assert len(plan.source_parts) == len(plan.translation_parts) == 2
