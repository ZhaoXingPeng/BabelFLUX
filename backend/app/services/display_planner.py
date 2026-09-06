"""Pure planning for readable bilingual subtitle display segments.

The planner has no session or network dependencies. It turns the current source/
translation snapshots into aligned display parts and monotonic time bounds; the
realtime pipeline remains responsible for writing those parts and emitting events.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.display_layout import (
    FINAL_DISPLAY_MAX_SEGMENT_MS,
    align_parts,
    display_split_count,
    estimate_display_bounds,
    fit_parts_to_count,
)
from app.services.display_text import (
    join_separator,
    normalize_display_text,
    should_use_cjk_display,
    split_by_regex,
    word_count,
)

SOURCE_MAX_WORDS_PER_DISPLAY_SEGMENT = 18
SOURCE_MAX_CJK_CHARS_PER_DISPLAY_SEGMENT = 28
TARGET_MAX_CHARS_PER_DISPLAY_SEGMENT = 28
TARGET_MAX_WORDS_PER_DISPLAY_SEGMENT = 18


@dataclass(frozen=True)
class DisplayPlan:
    source_parts: list[str]
    translation_parts: list[str]
    count: int
    display_final: bool
    bounds: list[tuple[int, int]]


def build_display_plan(
    *,
    source_text: str,
    translation_text: str,
    source_language: str | None,
    target_language: str | None,
    source_final: bool,
    translation_final: bool,
    previous_count: int,
    previous_source_parts: list[str],
    previous_translation_parts: list[str],
    root_start_ms: int,
    root_end_ms: int,
    elapsed_ms: int,
) -> DisplayPlan | None:
    source_text = normalize_display_text(source_text, source_language)
    translation_text = normalize_display_text(translation_text, target_language)
    has_bilingual_text = bool(source_text and translation_text)
    source_split = (
        split_source_display(source_text, source_language)
        if has_bilingual_text
        else ([source_text] if source_text else [])
    )
    translation_split = (
        split_target_display(translation_text, target_language)
        if has_bilingual_text
        else ([translation_text] if translation_text else [])
    )

    keep_existing_split = previous_count > 1 and (
        len(source_split) > 1 or len(translation_split) > 1
    )
    if keep_existing_split:
        source_parts = source_split if source_split else ([source_text] if source_text else [])
        translation_parts = (
            translation_split
            if translation_split
            else ([translation_text] if translation_text else [])
        )
    else:
        source_parts = source_split
        translation_parts = translation_split
    if not source_parts and not translation_parts:
        return None

    current_count = display_split_count(source_parts, translation_parts)
    if source_final or translation_final:
        display_span_ms = root_end_ms - root_start_ms
        current_count = max(
            current_count,
            (display_span_ms + FINAL_DISPLAY_MAX_SEGMENT_MS - 1)
            // FINAL_DISPLAY_MAX_SEGMENT_MS,
        )
    source_parts = fit_source_parts_to_count(source_parts, current_count, source_language)
    translation_parts = fit_target_parts_to_count(
        translation_parts, current_count, target_language
    )
    count = max(previous_count, current_count)

    preserve_split = previous_count > 1 and (
        len(source_parts) < previous_count or len(translation_parts) < previous_count
    )
    source_display = align_parts(
        source_parts,
        count,
        separator=join_separator(source_parts),
        previous=previous_source_parts,
        preserve_existing=preserve_split,
    )
    translation_display = align_parts(
        translation_parts,
        count,
        separator=join_separator(translation_parts),
        previous=previous_translation_parts,
        preserve_existing=preserve_split,
    )
    source_display = [
        normalize_display_text(part, source_language) for part in source_display
    ]
    translation_display = [
        normalize_display_text(part, target_language) for part in translation_display
    ]
    display_final = (not source_parts or source_final) and (
        not translation_parts or translation_final
    )
    bounds = estimate_display_bounds(
        root_start_ms,
        root_end_ms,
        elapsed_ms,
        source_display,
        translation_display,
        final=display_final,
    )
    return DisplayPlan(
        source_parts=source_display,
        translation_parts=translation_display,
        count=count,
        display_final=display_final,
        bounds=bounds,
    )


def split_source_display(text: str, language: str | None = None) -> list[str]:
    value = normalize_display_text(text, language)
    if not value:
        return []
    if should_use_cjk_display(value, language):
        return split_cjk_display(value, SOURCE_MAX_CJK_CHARS_PER_DISPLAY_SEGMENT)
    return split_latin_display(value, SOURCE_MAX_WORDS_PER_DISPLAY_SEGMENT)


def split_latin_display(text: str, max_words: int) -> list[str]:
    value = re.sub(r"\s+", " ", text.strip())
    if not value:
        return []

    parts = split_source_sentences(value)
    target_count = target_source_part_count(value, max_words)
    while len(parts) < target_count or any(word_count(part) > max_words for part in parts):
        split_index, replacement = best_source_split(parts)
        if split_index < 0:
            break
        parts = [*parts[:split_index], *replacement, *parts[split_index + 1 :]]
    return parts


def split_source_sentences(text: str) -> list[str]:
    value = re.sub(r"\s+", " ", text.strip())
    if not value:
        return []
    return split_by_regex(value, r"(?<=[.!?])\s+")


def split_target_sentences(text: str) -> list[str]:
    value = normalize_display_text(text, "zh")
    if not value:
        return []
    return [
        part.strip()
        for part in re.findall(r"[^。！？!?]+[。！？!?]?", value)
        if part.strip()
    ]


def split_source_clauses(text: str) -> list[str]:
    first, second = find_natural_source_split(text)
    return [first, second] if first and second else [text]


def split_long_source_part(text: str) -> list[str]:
    words = text.split()
    if len(words) <= SOURCE_MAX_WORDS_PER_DISPLAY_SEGMENT:
        return [text]
    return [
        " ".join(words[index : index + SOURCE_MAX_WORDS_PER_DISPLAY_SEGMENT])
        for index in range(0, len(words), SOURCE_MAX_WORDS_PER_DISPLAY_SEGMENT)
    ]


def target_source_part_count(
    text: str, max_words: int = SOURCE_MAX_WORDS_PER_DISPLAY_SEGMENT
) -> int:
    return max(1, (word_count(text) + max_words - 1) // max_words)


def best_source_split(parts: list[str]) -> tuple[int, list[str]]:
    best_index = -1
    best_replacement: list[str] = []
    best_score: tuple[int, int] | None = None
    for index, part in enumerate(parts):
        replacement = split_source_clauses(part)
        if len(replacement) < 2:
            replacement = split_long_source_part(part)
        if len(replacement) < 2:
            continue
        score = (word_count(part), len(part))
        if best_score is None or score > best_score:
            best_index = index
            best_replacement = replacement
            best_score = score
    return best_index, best_replacement


def find_natural_source_split(text: str) -> tuple[str, str]:
    words = text.split()
    if len(words) <= SOURCE_MAX_WORDS_PER_DISPLAY_SEGMENT:
        return "", ""

    candidates: list[tuple[int, int, int, int]] = []
    pattern = re.compile(
        r"[,;:]\s+|\s+(?:and|as|because|but|for|if|or|so|then|to|which|while|who|whose|with)\s+",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        split_at = match.end() if match.group(0).strip() in {",", ";", ":"} else match.start()
        first = text[:split_at].strip()
        second = text[split_at:].strip()
        first_words = word_count(first)
        second_words = word_count(second)
        if first_words < 3 or second_words < 3:
            continue
        boundary = match.group(0).strip().lower()
        priority = 2 if boundary in {",", ";", ":"} else 1
        overflow_penalty = max(0, first_words - SOURCE_MAX_WORDS_PER_DISPLAY_SEGMENT) + max(
            0, second_words - SOURCE_MAX_WORDS_PER_DISPLAY_SEGMENT
        )
        balance_penalty = abs(first_words - second_words)
        candidates.append((priority, -overflow_penalty, -balance_penalty, split_at))

    if not candidates:
        return "", ""
    split_at = max(candidates)[3]
    return text[:split_at].strip(), text[split_at:].strip()


def split_target_display(text: str, language: str | None = None) -> list[str]:
    raw = normalize_display_text(text, language)
    if not raw:
        return []
    if not should_use_cjk_display(raw, language):
        return split_latin_display(raw, TARGET_MAX_WORDS_PER_DISPLAY_SEGMENT)
    return split_cjk_display(raw, TARGET_MAX_CHARS_PER_DISPLAY_SEGMENT)


def split_cjk_display(text: str, max_chars: int) -> list[str]:
    value = normalize_display_text(text, "zh")
    if not value:
        return []

    groups: list[str] = []
    for sentence in split_target_sentences(value):
        groups.extend(split_long_cjk_part(sentence, max_chars))
    return [part for part in groups if part]


def split_long_target_part(text: str) -> list[str]:
    return split_long_cjk_part(text, TARGET_MAX_CHARS_PER_DISPLAY_SEGMENT)


def split_long_cjk_part(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    current = ""
    clauses = re.findall(r"[^，,；;：:]+[，,；;：:]?", text)
    for clause in clauses:
        candidate = f"{current}{clause}" if current else clause
        if current and len(candidate) > max_chars:
            parts.append(current)
            current = clause
        else:
            current = candidate
    if current:
        parts.append(current)
    if len(parts) == 1 and len(parts[0]) > max_chars:
        value = parts[0]
        return [value[index : index + max_chars] for index in range(0, len(value), max_chars)]
    return parts


def fit_source_parts_to_count(
    parts: list[str], count: int, language: str | None = None
) -> list[str]:
    expanded = expand_source_parts_to_count(parts, count, language)
    return fit_parts_to_count(expanded, count, separator=join_separator(expanded))


def fit_target_parts_to_count(
    parts: list[str], count: int, language: str | None = None
) -> list[str]:
    expanded = expand_target_parts_to_count(parts, count, language)
    return fit_parts_to_count(expanded, count, separator=join_separator(expanded))


def expand_source_parts_to_count(
    parts: list[str], count: int, language: str | None = None
) -> list[str]:
    expanded = [part for part in parts if part]
    while len(expanded) < count:
        index = max(range(len(expanded)), key=lambda item: word_count(expanded[item]), default=-1)
        if index < 0:
            break
        if should_use_cjk_display(expanded[index], language):
            replacement = split_long_cjk_part(
                expanded[index], SOURCE_MAX_CJK_CHARS_PER_DISPLAY_SEGMENT
            )
            if len(replacement) < 2:
                replacement = split_target_part_evenly(expanded[index])
        else:
            replacement = split_source_clauses(expanded[index])
            if len(replacement) < 2:
                replacement = split_long_source_part(expanded[index])
            if len(replacement) < 2:
                replacement = split_source_part_evenly(expanded[index])
        if len(replacement) < 2:
            break
        expanded = [*expanded[:index], *replacement, *expanded[index + 1 :]]
    return expanded


def expand_target_parts_to_count(
    parts: list[str], count: int, language: str | None = None
) -> list[str]:
    expanded = [part for part in parts if part]
    while len(expanded) < count:
        index = max(range(len(expanded)), key=lambda item: len(expanded[item]), default=-1)
        if index < 0:
            break
        use_cjk = should_use_cjk_display(expanded[index], language)
        replacement = (
            split_long_target_part(expanded[index])
            if use_cjk
            else split_long_source_part(expanded[index])
        )
        if len(replacement) < 2:
            replacement = (
                split_target_part_evenly(expanded[index])
                if use_cjk
                else split_source_part_evenly(expanded[index])
            )
        if len(replacement) < 2:
            break
        expanded = [*expanded[:index], *replacement, *expanded[index + 1 :]]
    return expanded


def split_source_part_evenly(text: str) -> list[str]:
    words = text.split()
    if len(words) < 2:
        return [text]
    midpoint = len(words) // 2
    return [" ".join(words[:midpoint]), " ".join(words[midpoint:])]


def split_target_part_evenly(text: str) -> list[str]:
    value = text.strip()
    if len(value) < 2:
        return [text]
    midpoint = len(value) // 2
    return [value[:midpoint], value[midpoint:]]
