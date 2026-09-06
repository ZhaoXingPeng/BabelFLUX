"""自动语言识别与语言对调整策略。

这些函数只根据输入文本和当前语言配置返回决策，不读取会话状态，也不执行 I/O。
将它们从实时管线抽出后，可以独立验证边界，同时让管线继续负责时序和副作用。
"""

from __future__ import annotations

from app.services.display_text import (
    contains_cjk,
    contains_latin_word,
    is_latin_dominant,
    latin_word_count,
)

AUTO_LANGUAGE_TARGETS = frozenset({"zh", "en"})


def opposite_language(language: str) -> str:
    """Return the supported counterpart used by the automatic language flow."""

    return "zh" if language == "en" else "en"


def initial_provider_source_language(source_language: str, target_language: str) -> str:
    """Choose the provider hint before an auto source language is detected."""

    if source_language != "auto":
        return source_language
    if target_language in AUTO_LANGUAGE_TARGETS:
        return opposite_language(target_language)
    return "en"


def should_preflight_language(source_language: str, target_language: str) -> bool:
    return source_language == "auto" and target_language in AUTO_LANGUAGE_TARGETS


def infer_source_language(sample: str) -> str | None:
    """Infer English or Chinese only when the sample has enough signal."""

    latin_words = latin_word_count(sample)
    cjk_chars = sum(1 for char in sample if "\u4e00" <= char <= "\u9fff")
    if contains_cjk(sample) and contains_latin_word(sample):
        if is_latin_dominant(sample):
            return "en"
        if cjk_chars >= 3:
            return "zh"
        return None
    if cjk_chars >= 3:
        return "zh"
    if latin_words >= 3:
        return "en"
    return None


def suggest_language_pair(inferred_source: str, target_language: str) -> tuple[str, str]:
    """Keep source and target different for the supported auto-language pair."""

    target = target_language
    if target == inferred_source and inferred_source in AUTO_LANGUAGE_TARGETS:
        target = opposite_language(inferred_source)
    return inferred_source, target
