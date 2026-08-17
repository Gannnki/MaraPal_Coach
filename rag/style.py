"""Controlled answer-style instructions derived from the user's wording."""

from __future__ import annotations

from typing import Literal

AnswerStyle = Literal["casual", "neutral", "academic"]
AnswerDetail = Literal["brief", "standard", "detailed"]

STYLE_INSTRUCTIONS: dict[AnswerStyle, str] = {
    "casual": (
        "Use natural conversational language and lead with a direct answer. Prefer "
        "short sentences and explain unavoidable technical terms simply. Do not sound "
        "like a textbook, and do not imitate slang, mistakes, or emotional language."
    ),
    "neutral": (
        "Use clear, concise, professional language. Explain technical terms only when "
        "they materially help the answer."
    ),
    "academic": (
        "Use precise technical language. Distinguish mechanisms, findings, evidence "
        "strength, uncertainty, and relevant limitations. Do not add unsupported detail "
        "merely to sound academic."
    ),
}

DETAIL_INSTRUCTIONS: dict[AnswerDetail, str] = {
    "brief": "Keep the answer compact and include only the conclusion and essential caveats.",
    "standard": "Give enough explanation to support the conclusion without unnecessary detail.",
    "detailed": "Give a thorough explanation with relevant mechanisms, caveats, and practical implications.",
}


def answer_instructions(style: AnswerStyle, detail: AnswerDetail) -> str:
    return f"{STYLE_INSTRUCTIONS[style]} {DETAIL_INSTRUCTIONS[detail]}"
