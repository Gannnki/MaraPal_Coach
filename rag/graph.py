"""LangGraph orchestration for knowledge, race, and mixed questions."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, SecretStr

from .config import Settings
from .knowledge import answer_knowledge, load_documents, vector_store
from .races import FILTER_PROMPT, RaceFilters, connect, format_races, search
from .retrieval import build_retriever
from .style import AnswerDetail, AnswerStyle, answer_instructions


class QueryAnalysis(BaseModel):
    route: Literal["knowledge", "races", "mixed"]
    style: AnswerStyle
    detail: AnswerDetail


class GraphState(TypedDict, total=False):
    question: str
    route: str
    answer_style: str
    answer_detail: str
    knowledge_answer: str
    race_answer: str
    answer: str
    sources: list[dict[str, Any]]


ROUTER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """Analyze the query using exactly these fields.

Route:
- knowledge: running advice, science, health, training, nutrition, injury, or gear
- races: German event discovery only
- mixed: contains both knowledge and German event discovery

Style describes only the user's communication style:
- casual: conversational, colloquial, or informal wording
- academic: technical terminology, research framing, mechanisms, methodology,
  evidence quality, or formal analytical wording
- neutral: everything else; choose neutral when uncertain

Detail:
- brief: user explicitly asks for a short/simple answer
- detailed: user explicitly asks for depth, mechanisms, evidence, or a detailed explanation
- standard: everything else

Do not infer education, intelligence, age, or profession. Do not copy mistakes or slang.""",
        ),
        ("human", "{question}"),
    ]
)


def build_graph(
    settings: Settings | None = None, *, api_key: SecretStr | None = None,
    llm: Any = None, retriever: Any = None, race_connection: Any = None,
    retrieval_mode: str | None = None,
):
    settings = settings or Settings.from_env()
    llm = llm or ChatOpenAI(
        model=settings.chat_model, temperature=0, api_key=api_key
    )
    mode = retrieval_mode or settings.retrieval_mode
    retriever = retriever or build_retriever(
        mode, vector_store(settings, api_key=api_key),
        load_documents(settings.knowledge_path),
        k=settings.retrieval_k,
    )
    def route_query(state: GraphState) -> dict[str, str]:
        result = (ROUTER_PROMPT | llm.with_structured_output(QueryAnalysis)).invoke(
            {"question": state["question"]}
        )
        return {
            "route": result.route,
            "answer_style": result.style,
            "answer_detail": result.detail,
        }

    def knowledge_node(state: GraphState) -> dict[str, Any]:
        instruction = answer_instructions(
            state["answer_style"], state["answer_detail"]  # type: ignore[arg-type]
        )
        answer, sources = answer_knowledge(
            state["question"], retriever, llm, instruction
        )
        return {"knowledge_answer": answer, "sources": sources}

    def race_node(state: GraphState) -> dict[str, str]:
        filters = (FILTER_PROMPT | llm.with_structured_output(RaceFilters)).invoke(
            {"question": state["question"], "today": dt.date.today().isoformat()}
        )
        if race_connection is not None:
            races = search(race_connection, filters)
        else:
            # FastAPI executes synchronous endpoints in worker threads. A SQLite
            # connection must be created and used in the same thread, so open a
            # short-lived connection here rather than capturing one at startup.
            with connect(settings.race_db) as connection:
                races = search(connection, filters)
        return {"race_answer": format_races(races)}

    def finish(state: GraphState) -> dict[str, str]:
        parts = [state.get("knowledge_answer", ""), state.get("race_answer", "")]
        return {"answer": "\n\n".join(part for part in parts if part)}

    def next_nodes(state: GraphState):
        return {"knowledge": "knowledge", "races": "races", "mixed": "knowledge"}[state["route"]]

    def after_knowledge(state: GraphState):
        return "races" if state["route"] == "mixed" else "finish"

    builder = StateGraph(GraphState)
    
    builder.add_node("route", route_query)
    builder.add_node("knowledge", knowledge_node)
    builder.add_node("races", race_node)
    builder.add_node("finish", finish)

    builder.add_edge(START, "route")
    builder.add_conditional_edges("route", next_nodes)
    builder.add_conditional_edges("knowledge", after_knowledge)
    builder.add_edge("races", "finish")
    builder.add_edge("finish", END)

    return builder.compile()
