from app.services.source_text import (
    collapse_adjacent_source_duplicates,
    normalize_source_word,
    normalize_source_words,
)


def test_normalize_source_word_handles_punctuation_and_contractions() -> None:
    assert normalize_source_word("Don't") == "don"
    assert normalize_source_word("we're,") == "we"
    assert normalize_source_word("  Hello!  ") == "hello"


def test_normalize_source_words_preserves_order() -> None:
    assert normalize_source_words(["We", "ARE", "ready."]) == ["we", "are", "ready"]


def test_collapse_adjacent_source_duplicates_uses_normalized_values() -> None:
    assert collapse_adjacent_source_duplicates(["Hello", "hello,", "world"]) == [
        "Hello",
        "world",
    ]

