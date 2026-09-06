from app.services.display_layout import (
    align_parts,
    display_split_count,
    estimate_display_bounds,
    fit_parts_to_count,
)
from app.services.display_text import (
    contains_aligned_parts,
    join_separator,
    normalize_alignment_text,
    normalize_display_text,
    should_use_cjk_display,
    split_by_regex,
    word_count,
)


def test_display_language_policy_distinguishes_cjk_and_latin() -> None:
    assert should_use_cjk_display("你好世界", "zh")
    assert not should_use_cjk_display("Hello world", "en")
    assert not should_use_cjk_display("API 网关 service ready", "auto")


def test_normalize_display_text_removes_cjk_spacing_without_touching_latin() -> None:
    assert normalize_display_text("你 好 ， 世界。", "zh") == "你好，世界。"
    assert normalize_display_text("Hello  world", "en") == "Hello world"


def test_alignment_and_split_helpers_are_deterministic() -> None:
    assert join_separator(["你好", "世界"]) == ""
    assert join_separator(["Hello", "world"]) == " "
    assert word_count("one two three") == 3
    assert split_by_regex("one. two!", r"(?<=[.!])\s+") == ["one.", "two!"]
    assert normalize_alignment_text("你好， World!") == "你好world"
    assert contains_aligned_parts("第一句第二句", ["第一句", "第二句"])


def test_display_layout_aligns_mismatched_parts_by_ratio() -> None:
    source = ["one", "two", "three", "four"]
    translation = ["一", "二"]

    assert display_split_count(source, translation) == 2
    assert fit_parts_to_count(source, 2, separator=" ") == ["one two", "three four"]
    assert align_parts(translation, 2, separator="") == translation


def test_display_layout_does_not_mutate_inputs() -> None:
    parts = ["first", "second", "third"]
    previous = ["old first", "old second"]
    original_parts = parts.copy()
    original_previous = previous.copy()

    align_parts(parts, 2, separator=" ", previous=previous, preserve_existing=True)

    assert parts == original_parts
    assert previous == original_previous


def test_display_layout_bounds_are_monotonic_and_end_at_requested_time() -> None:
    bounds = estimate_display_bounds(
        1_000,
        12_000,
        12_000,
        ["short", "a much longer final phrase"],
        ["短", "更长的最终片段"],
        final=True,
    )

    assert bounds[-1][1] == 12_000
    assert all(start <= end for start, end in bounds)
    assert all(bounds[index][1] <= bounds[index + 1][0] for index in range(len(bounds) - 1))


def test_display_layout_handles_missing_side_and_non_positive_count() -> None:
    assert display_split_count([], ["译文"]) == 1
    assert display_split_count(["source"], []) == 1
    assert align_parts([], 2, separator=" ") == ["", ""]
    assert align_parts(["source"], 0, separator=" ") == []
    assert estimate_display_bounds(500, 500, 500, [], [], final=False) == [(500, 1000)]
