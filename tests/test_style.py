import pytest

from rag.style import answer_instructions


def test_style_and_detail_are_both_included():
    instruction = answer_instructions("casual", "detailed")
    assert "conversational" in instruction
    assert "thorough" in instruction


def test_unknown_style_is_rejected():
    with pytest.raises(KeyError):
        answer_instructions("poetic", "standard")  # type: ignore[arg-type]
