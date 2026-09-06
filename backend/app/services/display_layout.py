"""字幕显示片段的纯布局策略。

文本切分和事件发送仍由实时管线负责；本模块只根据已经切好的片段计算数量、
比例对齐和时间边界，不读取会话或执行 I/O。
"""

from __future__ import annotations

from app.services.display_text import contains_aligned_parts, word_count

PARTIAL_DISPLAY_SEGMENT_MS = 500
FINAL_DISPLAY_SEGMENT_MS = 2000
FINAL_DISPLAY_MAX_SEGMENT_MS = 9500


def display_split_count(source_parts: list[str], translation_parts: list[str]) -> int:
    source_count = len(source_parts)
    translation_count = len(translation_parts)
    if not source_count:
        return max(translation_count, 1)
    if not translation_count:
        return max(source_count, 1)
    source_chars = len(" ".join(source_parts))
    translation_chars = len("".join(translation_parts))
    readable_count = max(
        1,
        (source_chars + 139) // 140,
        (translation_chars + 79) // 80,
    )
    bounded_by_parts = max(min(source_count, translation_count), readable_count)
    return min(max(source_count, translation_count), bounded_by_parts)


def fit_parts_to_count(parts: list[str], count: int, *, separator: str) -> list[str]:
    if count <= 0 or len(parts) <= count:
        return parts
    groups: list[str] = []
    for index in range(count):
        start = (len(parts) * index) // count
        end = (len(parts) * (index + 1)) // count
        if end <= start:
            end = start + 1
        groups.append(separator.join(parts[start:end]).strip())
    return groups


def align_parts(
    parts: list[str],
    count: int,
    *,
    separator: str,
    previous: list[str] | None = None,
    preserve_existing: bool = False,
) -> list[str]:
    if count <= 0:
        return []
    if not parts:
        if preserve_existing and previous:
            return [*previous[:count], *( [""] * max(0, count - len(previous)) )]
        return [""] * count
    if len(parts) == count:
        return parts
    if len(parts) < count:
        if preserve_existing and previous:
            padded_previous = [*previous[:count], *( [""] * max(0, count - len(previous)) )]
            if len(parts) == 1 and parts[0]:
                existing_non_empty = [part for part in padded_previous if part]
                if contains_aligned_parts(parts[0], existing_non_empty):
                    return padded_previous[:count]
            return [*parts, *padded_previous[len(parts) : count]]
        return [*parts, *( [""] * (count - len(parts)) )]
    return fit_parts_to_count(parts, count, separator=separator)


def estimate_display_bounds(
    root_start_ms: int,
    root_end_ms: int,
    elapsed_ms: int,
    source_parts: list[str],
    translation_parts: list[str],
    *,
    final: bool,
) -> list[tuple[int, int]]:
    count = max(len(source_parts), len(translation_parts), 1)
    estimated_segment_ms = FINAL_DISPLAY_SEGMENT_MS if final else PARTIAL_DISPLAY_SEGMENT_MS
    end_ms = max(root_end_ms, elapsed_ms, root_start_ms + count * estimated_segment_ms)
    span = max(1, end_ms - root_start_ms)
    if final and span > FINAL_DISPLAY_MAX_SEGMENT_MS:
        bounds: list[tuple[int, int]] = []
        for index in range(count):
            start = root_start_ms + int(span * index / count)
            end = (
                end_ms
                if index == count - 1
                else root_start_ms + int(span * (index + 1) / count)
            )
            bounds.append((start, max(end, start)))
        return bounds

    weights = [
        max(
            word_count(source_parts[index]) if index < len(source_parts) else 0,
            len(translation_parts[index]) // 3 if index < len(translation_parts) else 0,
            1,
        )
        for index in range(count)
    ]
    total = sum(weights) or count
    bounds = []
    cursor = root_start_ms
    consumed = 0
    for index, weight in enumerate(weights):
        consumed += weight
        next_cursor = (
            end_ms
            if index == count - 1
            else root_start_ms + int(span * consumed / total)
        )
        bounds.append((cursor, max(next_cursor, cursor)))
        cursor = next_cursor
    return bounds
