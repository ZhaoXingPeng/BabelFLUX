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
