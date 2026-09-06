"""Pure text policy helpers for bilingual subtitle display and alignment."""

from __future__ import annotations

import re

CJK_LANGUAGE_PREFIXES = ("zh", "ja", "ko", "yue")


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def contains_latin_word(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)?", text))


def latin_word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)?", text))


def is_cjk_language(language: str | None) -> bool:
    if not language or language == "auto":
        return False
    return language.lower().startswith(CJK_LANGUAGE_PREFIXES)


def is_latin_dominant(text: str) -> bool:
    latin_words = latin_word_count(text)
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    return latin_words >= 3 and latin_words * 2 >= cjk_chars


def should_use_cjk_display(text: str, language: str | None = None) -> bool:
    if not contains_cjk(text):
        return False
    if is_cjk_language(language):
        return True
    if not language or language == "auto":
        return not is_latin_dominant(text)
    return False


def normalize_display_text(text: str, language: str | None = None) -> str:
    value = re.sub(r"\s+", " ", text.strip())
    if not value or not should_use_cjk_display(value, language):
        return value

    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)
    value = re.sub(r"\s+([，。！？；：、,.!?;:])", r"\1", value)
    value = re.sub(r"(?<=[，。！？；：、])\s+(?=[\u4e00-\u9fff])", "", value)
    value = re.sub(r"([（《“\"'(\[])\s+", r"\1", value)
    value = re.sub(r"\s+([））》”\"')\]])", r"\1", value)
    return value.strip()


def join_separator(parts: list[str]) -> str:
    text = " ".join(parts)
    return "" if contains_cjk(text) and not contains_latin_word(text) else " "


def split_by_regex(text: str, pattern: str) -> list[str]:
    return [part.strip() for part in re.split(pattern, text) if part.strip()]


def word_count(text: str) -> int:
    return len([word for word in text.split() if word])


def normalize_alignment_text(text: str) -> str:
    return re.sub(r"[\s.,;:!?，。；：！？\"'’“”()（）\[\]{}]", "", text).lower()


def contains_aligned_parts(candidate: str, parts: list[str]) -> bool:
    if len(parts) <= 1:
        return False
    normalized_candidate = normalize_alignment_text(candidate)
    return all(normalize_alignment_text(part) in normalized_candidate for part in parts)
