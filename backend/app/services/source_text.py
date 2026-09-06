"""Pure source-text normalization helpers used by the interpretation pipeline."""

from __future__ import annotations


def normalize_source_word(word: str) -> str:
    """Normalize punctuation and common English contractions for overlap matching."""
    value = word.lower().strip(" \t\r\n.,;:!?\"'()[]{}")
    value = value.strip("\u2018\u2019")
    for suffix in ("n't", "n\u2019t"):
        if value.endswith(suffix) and len(value) > len(suffix):
            return f"{value[: -len(suffix)]}n"
    for suffix in (
        "'re",
        "\u2019re",
        "'ve",
        "\u2019ve",
        "'ll",
        "\u2019ll",
        "'d",
        "\u2019d",
        "'s",
        "\u2019s",
        "'m",
        "\u2019m",
        "'t",
        "\u2019t",
    ):
        if value.endswith(suffix) and len(value) > len(suffix):
            return value[: -len(suffix)]
    return value


def normalize_source_words(words: list[str]) -> list[str]:
    return [normalize_source_word(word) for word in words]


def collapse_adjacent_source_duplicates(words: list[str]) -> list[str]:
    result: list[str] = []
    for word in words:
        if result and normalize_source_word(result[-1]) == normalize_source_word(word):
            continue
        result.append(word)
    return result

